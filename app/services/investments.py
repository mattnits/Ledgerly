from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from app.core.db import SessionLocal
from app.models.models import (
    Account,
    Category,
    GroupMembership,
    InvestmentAccount,
    InvestmentSnapshot,
    Transaction,
)
from app.utils.constants import TransactionType


MONEY_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class InvestmentAccountSummary:
    id: int
    institution: str
    account_name: str
    account_number_last7: str | None
    account_type: str | None
    created_at: datetime
    is_active: bool
    current_value: Decimal
    last_updated: datetime | None
    user_id: str | None
    group_id: int | None
    is_work_related: bool
    auto_track_from_payroll: bool
    employee_contribution_percent: Decimal | None
    employer_matching_enabled: bool
    employer_match_percent: Decimal | None
    payroll_tracking_start_date: date | None

    @property
    def display_name(self) -> str:
        suffix = (
            f" ({self.account_number_last7})"
            if self.account_number_last7
            else ""
        )
        return f"{self.account_name} — {self.institution}{suffix}"


@dataclass(frozen=True)
class PortfolioPoint:
    snapshot_datetime: datetime
    total_value: Decimal


@dataclass(frozen=True)
class RecentInvestmentSnapshot:
    id: int
    investment_account_id: int
    account_name: str
    institution: str
    snapshot_datetime: datetime
    total_value: Decimal
    contribution_amount: Decimal | None


@dataclass(frozen=True)
class ContributionComparison:
    current: Decimal
    previous: Decimal


@dataclass(frozen=True)
class WorkRrspCalculation:
    deposited_salary: Decimal
    pre_rrsp_take_home: Decimal
    employee_contribution: Decimal
    employer_match: Decimal
    total_contribution: Decimal


@dataclass(frozen=True)
class WorkRrspSummary:
    salary_count: int = 0
    deposited_salary_total: Decimal = Decimal("0.00")
    pre_rrsp_take_home_total: Decimal = Decimal("0.00")
    employee_contribution: Decimal = Decimal("0.00")
    employer_match: Decimal = Decimal("0.00")
    total_contribution: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class WorkRrspMonthlyHistory:
    year: int
    month: int
    summary: WorkRrspSummary


@dataclass(frozen=True)
class InvestmentContributionSummary:
    manual: Decimal
    work_rrsp_employee: Decimal
    work_rrsp_employer: Decimal

    @property
    def total(self) -> Decimal:
        return self.manual + self.work_rrsp_employee + self.work_rrsp_employer


def _validate_owner(user_id: str | None, group_id: int | None) -> None:
    if (user_id is None) == (group_id is None):
        raise ValueError("Provide exactly one owner: user_id or group_id")


def _direct_owner_scope(user_id: str | None, group_id: int | None):
    _validate_owner(user_id, group_id)
    return (
        InvestmentAccount.user_id == user_id
        if user_id is not None
        else InvestmentAccount.group_id == group_id
    )


def _visible_account_scope(user_id: str | None, group_id: int | None):
    """Match the app's household rule: group-owned plus member-owned accounts."""
    _validate_owner(user_id, group_id)
    if user_id is not None:
        return InvestmentAccount.user_id == user_id
    member_ids: Select = select(GroupMembership.user_id).where(
        GroupMembership.group_id == group_id
    )
    return or_(
        InvestmentAccount.group_id == group_id,
        InvestmentAccount.user_id.in_(member_ids),
    )


def _money(value: Decimal | str | int | float, field_name: str) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid monetary amount") from exc
    if not amount.is_finite():
        raise ValueError(f"{field_name} must be a finite monetary amount")
    return amount


def _percent(
    value: Decimal | str | int | float | None,
    field_name: str,
    *,
    below_100: bool = False,
) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        percent = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid percentage") from exc
    if not percent.is_finite() or percent < 0:
        raise ValueError(f"{field_name} must be zero or greater")
    if below_100 and percent >= 100:
        raise ValueError(f"{field_name} must be less than 100")
    return percent.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def calculate_work_rrsp_for_salary(
    deposited_salary: Decimal | str | int | float,
    employee_rate: Decimal | str | int | float,
    employer_match_rate: Decimal | str | int | float = Decimal("0"),
) -> WorkRrspCalculation:
    """Reverse an after-RRSP salary deposit and calculate its match."""
    deposited = _money(deposited_salary, "Deposited salary")
    if deposited < 0:
        raise ValueError("Deposited salary cannot be negative")
    employee_percent = _percent(
        employee_rate, "Employee contribution", below_100=True
    ) or Decimal()
    match_percent = _percent(employer_match_rate, "Employer match") or Decimal()
    rate = employee_percent / Decimal("100")
    pre_rrsp = (deposited / (Decimal("1") - rate)).quantize(
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )
    employee = (pre_rrsp - deposited).quantize(
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )
    employer = (employee * match_percent / Decimal("100")).quantize(
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )
    return WorkRrspCalculation(
        deposited,
        pre_rrsp,
        employee,
        employer,
        employee + employer,
    )


def normalize_account_number_last7(value: str | None) -> str | None:
    characters = re.sub(r"[^A-Za-z0-9]", "", value or "").upper()
    if not characters:
        return None
    return characters[-7:]


def _as_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    return datetime.combine(value, time.min)


def _as_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def _date_range(
    start_date: date | datetime | None,
    end_date: date | datetime | None,
) -> tuple[datetime | None, datetime | None]:
    start = _as_datetime(start_date) if start_date is not None else None
    if end_date is None:
        end = None
    elif isinstance(end_date, datetime):
        end = end_date
    else:
        end = datetime.combine(end_date + timedelta(days=1), time.min)
    return start, end


def get_investment_accounts(
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    include_inactive: bool = False,
    session_factory=SessionLocal,
) -> tuple[InvestmentAccount, ...]:
    conditions = [_visible_account_scope(user_id, group_id)]
    if not include_inactive:
        conditions.append(InvestmentAccount.is_active.is_(True))
    with session_factory() as session:
        accounts = session.scalars(
            select(InvestmentAccount)
            .where(*conditions)
            .order_by(
                InvestmentAccount.account_name,
                InvestmentAccount.institution,
                InvestmentAccount.id,
            )
        ).all()
        for account in accounts:
            session.expunge(account)
    return tuple(accounts)


def get_work_rrsp_accounts(
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> tuple[InvestmentAccount, ...]:
    return tuple(
        account
        for account in get_investment_accounts(
            user_id=user_id,
            group_id=group_id,
            session_factory=session_factory,
        )
        if account.is_work_related
        and (account.account_type or "").strip().casefold() == "rrsp"
    )


def _work_rrsp_account(account, session_factory=SessionLocal):
    if isinstance(account, int):
        with session_factory() as session:
            loaded = session.get(InvestmentAccount, account)
            if loaded is None:
                raise ValueError("Investment account was not found")
            session.expunge(loaded)
        return loaded
    return account


def _salary_rows_for_work_rrsp(
    account,
    *,
    start: date | None = None,
    end: date | None = None,
    session_factory=SessionLocal,
) -> tuple[tuple[date, Decimal], ...]:
    account = _work_rrsp_account(account, session_factory)
    if (
        not account.is_work_related
        or not account.auto_track_from_payroll
        or account.user_id is None
    ):
        return ()
    conditions = [
        Account.user_id == account.user_id,
        Transaction.is_deleted.is_(False),
        Transaction.transaction_type == TransactionType.INCOME,
        func.lower(func.trim(Category.name)) == "salary",
        Transaction.amount > 0,
        Transaction.transaction_date >= (
            account.payroll_tracking_start_date or account.created_at.date()
        ),
    ]
    if start is not None:
        conditions.append(Transaction.transaction_date >= start)
    if end is not None:
        conditions.append(Transaction.transaction_date < end)
    with session_factory() as session:
        rows = session.execute(
            select(Transaction.transaction_date, Transaction.amount)
            .join(Account, Transaction.account_id == Account.id)
            .join(Category, Transaction.category_id == Category.id)
            .where(*conditions)
            .order_by(Transaction.transaction_date, Transaction.id)
        ).all()
    return tuple((row.transaction_date, row.amount) for row in rows)


def _summarize_work_rrsp_rows(account, rows) -> WorkRrspSummary:
    employee_rate = account.employee_contribution_percent or Decimal()
    match_rate = (
        account.employer_match_percent or Decimal()
        if account.employer_matching_enabled
        else Decimal()
    )
    calculations = [
        calculate_work_rrsp_for_salary(amount, employee_rate, match_rate)
        for _, amount in rows
    ]
    return WorkRrspSummary(
        salary_count=len(calculations),
        deposited_salary_total=sum(
            (item.deposited_salary for item in calculations), Decimal("0.00")
        ),
        pre_rrsp_take_home_total=sum(
            (item.pre_rrsp_take_home for item in calculations), Decimal("0.00")
        ),
        employee_contribution=sum(
            (item.employee_contribution for item in calculations), Decimal("0.00")
        ),
        employer_match=sum(
            (item.employer_match for item in calculations), Decimal("0.00")
        ),
        total_contribution=sum(
            (item.total_contribution for item in calculations), Decimal("0.00")
        ),
    )


def get_monthly_work_rrsp_summary(
    investment_account,
    year: int,
    month: int,
    *,
    session_factory=SessionLocal,
) -> WorkRrspSummary:
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    account = _work_rrsp_account(investment_account, session_factory)
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    return _summarize_work_rrsp_rows(
        account,
        _salary_rows_for_work_rrsp(
            account, start=start, end=end, session_factory=session_factory
        ),
    )


def get_all_time_work_rrsp_summary(
    investment_account,
    *,
    session_factory=SessionLocal,
) -> WorkRrspSummary:
    account = _work_rrsp_account(investment_account, session_factory)
    return _summarize_work_rrsp_rows(
        account,
        _salary_rows_for_work_rrsp(account, session_factory=session_factory),
    )


def get_work_rrsp_monthly_history(
    investment_account,
    *,
    session_factory=SessionLocal,
) -> tuple[WorkRrspMonthlyHistory, ...]:
    account = _work_rrsp_account(investment_account, session_factory)
    grouped: dict[tuple[int, int], list[tuple[date, Decimal]]] = {}
    for transaction_date, amount in _salary_rows_for_work_rrsp(
        account, session_factory=session_factory
    ):
        grouped.setdefault(
            (transaction_date.year, transaction_date.month), []
        ).append((transaction_date, amount))
    return tuple(
        WorkRrspMonthlyHistory(
            year,
            month,
            _summarize_work_rrsp_rows(account, rows),
        )
        for (year, month), rows in sorted(grouped.items(), reverse=True)
    )


def _combine_work_rrsp_summaries(
    summaries: tuple[WorkRrspSummary, ...],
) -> WorkRrspSummary:
    return WorkRrspSummary(
        salary_count=sum(item.salary_count for item in summaries),
        deposited_salary_total=sum(
            (item.deposited_salary_total for item in summaries), Decimal("0.00")
        ),
        pre_rrsp_take_home_total=sum(
            (item.pre_rrsp_take_home_total for item in summaries), Decimal("0.00")
        ),
        employee_contribution=sum(
            (item.employee_contribution for item in summaries), Decimal("0.00")
        ),
        employer_match=sum(
            (item.employer_match for item in summaries), Decimal("0.00")
        ),
        total_contribution=sum(
            (item.total_contribution for item in summaries), Decimal("0.00")
        ),
    )


def get_owner_work_rrsp_summary(
    year: int,
    month: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> WorkRrspSummary:
    accounts = get_work_rrsp_accounts(
        user_id=user_id,
        group_id=group_id,
        session_factory=session_factory,
    )
    return _combine_work_rrsp_summaries(tuple(
        get_monthly_work_rrsp_summary(
            account, year, month, session_factory=session_factory
        )
        for account in accounts
    ))


def get_monthly_contribution_summary(
    year: int,
    month: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> InvestmentContributionSummary:
    work = get_owner_work_rrsp_summary(
        year,
        month,
        user_id=user_id,
        group_id=group_id,
        session_factory=session_factory,
    )
    return InvestmentContributionSummary(
        manual=_get_manual_monthly_contributions(
            year,
            month,
            user_id=user_id,
            group_id=group_id,
            session_factory=session_factory,
        ),
        work_rrsp_employee=work.employee_contribution,
        work_rrsp_employer=work.employer_match,
    )


def get_total_contribution_summary(
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> InvestmentContributionSummary:
    accounts = get_work_rrsp_accounts(
        user_id=user_id,
        group_id=group_id,
        session_factory=session_factory,
    )
    work = _combine_work_rrsp_summaries(tuple(
        get_all_time_work_rrsp_summary(account, session_factory=session_factory)
        for account in accounts
    ))
    return InvestmentContributionSummary(
        manual=_get_manual_total_contributions(
            user_id=user_id,
            group_id=group_id,
            session_factory=session_factory,
        ),
        work_rrsp_employee=work.employee_contribution,
        work_rrsp_employer=work.employer_match,
    )


def get_latest_snapshot(
    account_id: int,
    *,
    session_factory=SessionLocal,
) -> InvestmentSnapshot | None:
    with session_factory() as session:
        snapshot = session.scalar(
            select(InvestmentSnapshot)
            .where(InvestmentSnapshot.investment_account_id == account_id)
            .order_by(
                InvestmentSnapshot.snapshot_datetime.desc(),
                InvestmentSnapshot.id.desc(),
            )
            .limit(1)
        )
        if snapshot is not None:
            session.expunge(snapshot)
        return snapshot


def get_account_current_value(
    account_id: int,
    *,
    session_factory=SessionLocal,
) -> Decimal:
    snapshot = get_latest_snapshot(account_id, session_factory=session_factory)
    return snapshot.total_value if snapshot is not None else Decimal("0.00")


def get_account_summaries(
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    include_inactive: bool = False,
    session_factory=SessionLocal,
) -> tuple[InvestmentAccountSummary, ...]:
    conditions = [_visible_account_scope(user_id, group_id)]
    if not include_inactive:
        conditions.append(InvestmentAccount.is_active.is_(True))
    with session_factory() as session:
        accounts = session.scalars(
            select(InvestmentAccount)
            .options(selectinload(InvestmentAccount.snapshots))
            .where(*conditions)
            .order_by(
                InvestmentAccount.account_name,
                InvestmentAccount.institution,
                InvestmentAccount.id,
            )
        ).all()
        result = []
        for account in accounts:
            latest = max(
                account.snapshots,
                key=lambda item: (item.snapshot_datetime, item.id),
                default=None,
            )
            result.append(InvestmentAccountSummary(
                id=account.id,
                institution=account.institution,
                account_name=account.account_name,
                account_number_last7=account.account_number_last7,
                account_type=account.account_type,
                created_at=account.created_at,
                is_active=account.is_active,
                current_value=(latest.total_value if latest else Decimal("0.00")),
                last_updated=(latest.snapshot_datetime if latest else None),
                user_id=account.user_id,
                group_id=account.group_id,
                is_work_related=account.is_work_related,
                auto_track_from_payroll=account.auto_track_from_payroll,
                employee_contribution_percent=account.employee_contribution_percent,
                employer_matching_enabled=account.employer_matching_enabled,
                employer_match_percent=account.employer_match_percent,
                payroll_tracking_start_date=account.payroll_tracking_start_date,
            ))
    return tuple(result)


def get_total_portfolio_value(
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> Decimal:
    return sum(
        (
            account.current_value
            for account in get_account_summaries(
                user_id=user_id,
                group_id=group_id,
                session_factory=session_factory,
            )
        ),
        Decimal("0.00"),
    )


def get_portfolio_history(
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    start_date: date | datetime | None = None,
    end_date: date | datetime | None = None,
    session_factory=SessionLocal,
) -> tuple[PortfolioPoint, ...]:
    start, end = _date_range(start_date, end_date)
    conditions = [
        _visible_account_scope(user_id, group_id),
        InvestmentAccount.is_active.is_(True),
    ]
    if end is not None:
        conditions.append(InvestmentSnapshot.snapshot_datetime < end)

    with session_factory() as session:
        rows = session.execute(
            select(
                InvestmentSnapshot.investment_account_id,
                InvestmentSnapshot.snapshot_datetime,
                InvestmentSnapshot.total_value,
                InvestmentSnapshot.id,
            )
            .join(
                InvestmentAccount,
                InvestmentSnapshot.investment_account_id == InvestmentAccount.id,
            )
            .where(*conditions)
            .order_by(
                InvestmentSnapshot.snapshot_datetime,
                InvestmentSnapshot.id,
            )
        ).all()

    latest_values: dict[int, Decimal] = {}
    points: list[PortfolioPoint] = []
    index = 0
    while index < len(rows):
        snapshot_datetime = rows[index].snapshot_datetime
        while index < len(rows) and rows[index].snapshot_datetime == snapshot_datetime:
            row = rows[index]
            latest_values[row.investment_account_id] = row.total_value
            index += 1
        if start is None or snapshot_datetime >= start:
            points.append(PortfolioPoint(
                snapshot_datetime,
                sum(latest_values.values(), Decimal("0.00")),
            ))
    return tuple(points)


def get_monthly_contributions(
    year: int,
    month: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> Decimal:
    return get_monthly_contribution_summary(
        year,
        month,
        user_id=user_id,
        group_id=group_id,
        session_factory=session_factory,
    ).total


def _get_manual_monthly_contributions(
    year: int,
    month: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> Decimal:
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    start = datetime(year, month, 1)
    end = datetime(year + (month == 12), month % 12 + 1, 1)
    with session_factory() as session:
        values = session.scalars(
            select(InvestmentSnapshot.contribution_amount)
            .join(InvestmentAccount)
            .where(
                _visible_account_scope(user_id, group_id),
                InvestmentSnapshot.snapshot_datetime >= start,
                InvestmentSnapshot.snapshot_datetime < end,
                InvestmentSnapshot.contribution_amount.is_not(None),
            )
        ).all()
    return sum(values, Decimal("0.00"))


def get_monthly_contribution_comparison(
    year: int,
    month: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> ContributionComparison:
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    previous_year = year - (month == 1)
    previous_month = (month - 2) % 12 + 1
    return ContributionComparison(
        current=get_monthly_contributions(
            year,
            month,
            user_id=user_id,
            group_id=group_id,
            session_factory=session_factory,
        ),
        previous=get_monthly_contributions(
            previous_year,
            previous_month,
            user_id=user_id,
            group_id=group_id,
            session_factory=session_factory,
        ),
    )


def get_total_contributions(
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> Decimal:
    return get_total_contribution_summary(
        user_id=user_id,
        group_id=group_id,
        session_factory=session_factory,
    ).total


def _get_manual_total_contributions(
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> Decimal:
    with session_factory() as session:
        values = session.scalars(
            select(InvestmentSnapshot.contribution_amount)
            .join(InvestmentAccount)
            .where(
                _visible_account_scope(user_id, group_id),
                InvestmentSnapshot.contribution_amount.is_not(None),
            )
        ).all()
    return sum(values, Decimal("0.00"))


def get_recent_snapshots(
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    limit: int = 5,
    start_date: date | datetime | None = None,
    end_date: date | datetime | None = None,
    session_factory=SessionLocal,
) -> tuple[RecentInvestmentSnapshot, ...]:
    start, end = _date_range(start_date, end_date)
    conditions = [_visible_account_scope(user_id, group_id)]
    if start is not None:
        conditions.append(InvestmentSnapshot.snapshot_datetime >= start)
    if end is not None:
        conditions.append(InvestmentSnapshot.snapshot_datetime < end)
    with session_factory() as session:
        rows = session.execute(
            select(
                InvestmentSnapshot.id,
                InvestmentSnapshot.investment_account_id,
                InvestmentAccount.account_name,
                InvestmentAccount.institution,
                InvestmentSnapshot.snapshot_datetime,
                InvestmentSnapshot.total_value,
                InvestmentSnapshot.contribution_amount,
            )
            .join(InvestmentAccount)
            .where(*conditions)
            .order_by(
                InvestmentSnapshot.snapshot_datetime.desc(),
                InvestmentSnapshot.id.desc(),
            )
            .limit(max(limit, 0))
        ).all()
    return tuple(RecentInvestmentSnapshot(*row) for row in rows)


def get_account_history(
    account_id: int,
    *,
    session_factory=SessionLocal,
) -> tuple[InvestmentSnapshot, ...]:
    with session_factory() as session:
        snapshots = session.scalars(
            select(InvestmentSnapshot)
            .where(InvestmentSnapshot.investment_account_id == account_id)
            .order_by(
                InvestmentSnapshot.snapshot_datetime,
                InvestmentSnapshot.id,
            )
        ).all()
        for snapshot in snapshots:
            session.expunge(snapshot)
    return tuple(snapshots)


def get_investment_months(
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> set[tuple[int, int]]:
    with session_factory() as session:
        dates = session.scalars(
            select(InvestmentSnapshot.snapshot_datetime)
            .join(InvestmentAccount)
            .where(_visible_account_scope(user_id, group_id))
        ).all()
    months = {(value.year, value.month) for value in dates}
    for account in get_work_rrsp_accounts(
        user_id=user_id,
        group_id=group_id,
        session_factory=session_factory,
    ):
        months.update(
            (item.year, item.month)
            for item in get_work_rrsp_monthly_history(
                account, session_factory=session_factory
            )
        )
    return months


def _validated_work_rrsp_settings(
    account_type: str | None,
    is_work_related: bool,
    auto_track_from_payroll: bool,
    employee_contribution_percent,
    employer_matching_enabled: bool,
    employer_match_percent,
    *,
    group_id: int | None,
) -> dict[str, object]:
    work_related = bool(is_work_related)
    if not work_related:
        return {
            "is_work_related": False,
            "auto_track_from_payroll": False,
            "employee_contribution_percent": None,
            "employer_matching_enabled": False,
            "employer_match_percent": None,
        }
    if (account_type or "").strip().casefold() != "rrsp":
        raise ValueError("Work-related tracking is only available for RRSP accounts")
    if group_id is not None:
        raise ValueError("A work RRSP must belong to a specific user")
    employee_percent = _percent(
        employee_contribution_percent,
        "Employee contribution",
        below_100=True,
    )
    if employee_percent is None:
        raise ValueError("Employee contribution percentage is required")
    matching = bool(employer_matching_enabled)
    match_percent = _percent(employer_match_percent, "Employer match")
    if matching and match_percent is None:
        raise ValueError("Employer match percentage is required")
    return {
        "is_work_related": True,
        "auto_track_from_payroll": bool(auto_track_from_payroll),
        "employee_contribution_percent": employee_percent,
        "employer_matching_enabled": matching,
        "employer_match_percent": match_percent if matching else None,
    }


def create_investment_account(
    institution: str,
    account_name: str,
    *,
    account_number: str | None = None,
    account_type: str | None = None,
    initial_value: Decimal | str | int | float | None = None,
    initial_date: date | datetime | None = None,
    user_id: str | None = None,
    group_id: int | None = None,
    is_work_related: bool = False,
    auto_track_from_payroll: bool = False,
    employee_contribution_percent: Decimal | str | int | float | None = None,
    employer_matching_enabled: bool = False,
    employer_match_percent: Decimal | str | int | float | None = None,
    session_factory=SessionLocal,
) -> int:
    _validate_owner(user_id, group_id)
    institution = institution.strip()
    account_name = account_name.strip()
    account_type = (account_type or "").strip() or None
    if not institution:
        raise ValueError("Institution is required")
    if not account_name:
        raise ValueError("Account name is required")
    last7 = normalize_account_number_last7(account_number)
    starting_value = (
        _money(initial_value, "Initial value")
        if initial_value is not None
        else None
    )
    if starting_value is not None and starting_value < 0:
        raise ValueError("Initial value cannot be negative")
    work_settings = _validated_work_rrsp_settings(
        account_type,
        is_work_related,
        auto_track_from_payroll,
        employee_contribution_percent,
        employer_matching_enabled,
        employer_match_percent,
        group_id=group_id,
    )
    tracking_start_date = _as_date(initial_date or date.today())

    with session_factory() as session, session.begin():
        candidates = session.scalars(
            select(InvestmentAccount).where(
                _direct_owner_scope(user_id, group_id),
                func.lower(InvestmentAccount.institution) == institution.casefold(),
                func.lower(InvestmentAccount.account_name) == account_name.casefold(),
            )
        ).all()
        if any(account.account_number_last7 == last7 for account in candidates):
            raise ValueError("This investment account already exists")

        account = InvestmentAccount(
            user_id=user_id,
            group_id=group_id,
            institution=institution,
            account_name=account_name,
            account_number_last7=last7,
            account_type=account_type,
            is_active=True,
            payroll_tracking_start_date=(
                tracking_start_date if work_settings["is_work_related"] else None
            ),
            **work_settings,
        )
        session.add(account)
        session.flush()
        account_id = account.id
        if starting_value is not None:
            session.add(InvestmentSnapshot(
                investment_account_id=account.id,
                snapshot_datetime=_as_datetime(initial_date or date.today()),
                total_value=starting_value,
                contribution_amount=None,
            ))
    return account_id


def update_investment_account(
    account_id: int,
    *,
    institution: str,
    account_name: str,
    account_number: str | None = None,
    account_type: str | None = None,
    is_work_related: bool = False,
    auto_track_from_payroll: bool = False,
    employee_contribution_percent: Decimal | str | int | float | None = None,
    employer_matching_enabled: bool = False,
    employer_match_percent: Decimal | str | int | float | None = None,
    session_factory=SessionLocal,
) -> None:
    institution = institution.strip()
    account_name = account_name.strip()
    if not institution or not account_name:
        raise ValueError("Institution and account name are required")
    last7 = normalize_account_number_last7(account_number)
    with session_factory() as session, session.begin():
        account = session.get(InvestmentAccount, account_id)
        if account is None:
            raise ValueError("Investment account was not found")
        candidates = session.scalars(
            select(InvestmentAccount).where(
                InvestmentAccount.id != account_id,
                InvestmentAccount.user_id == account.user_id,
                InvestmentAccount.group_id == account.group_id,
                func.lower(InvestmentAccount.institution) == institution.casefold(),
                func.lower(InvestmentAccount.account_name) == account_name.casefold(),
            )
        ).all()
        if any(candidate.account_number_last7 == last7 for candidate in candidates):
            raise ValueError("This investment account already exists")
        account.institution = institution
        account.account_name = account_name
        account.account_number_last7 = last7
        account.account_type = (account_type or "").strip() or None
        settings = _validated_work_rrsp_settings(
            account.account_type,
            is_work_related,
            auto_track_from_payroll,
            employee_contribution_percent,
            employer_matching_enabled,
            employer_match_percent,
            group_id=account.group_id,
        )
        for name, value in settings.items():
            setattr(account, name, value)


def set_investment_account_active(
    account_id: int,
    is_active: bool,
    *,
    session_factory=SessionLocal,
) -> None:
    with session_factory() as session, session.begin():
        account = session.get(InvestmentAccount, account_id)
        if account is None:
            raise ValueError("Investment account was not found")
        account.is_active = bool(is_active)


def delete_investment_account(
    account_id: int,
    *,
    session_factory=SessionLocal,
) -> None:
    """Permanently delete an investment account and all of its snapshots."""
    with session_factory() as session, session.begin():
        account = session.get(InvestmentAccount, account_id)
        if account is None:
            raise ValueError("Investment account was not found")
        session.delete(account)


def create_investment_snapshot(
    investment_account_id: int,
    snapshot_datetime: date | datetime,
    total_value: Decimal | str | int | float,
    contribution_amount: Decimal | str | int | float | None = None,
    *,
    session_factory=SessionLocal,
) -> int:
    total = _money(total_value, "Total value")
    if total < 0:
        raise ValueError("Total value cannot be negative")
    contribution = (
        _money(contribution_amount, "Contribution amount")
        if contribution_amount is not None
        else None
    )
    recorded_at = _as_datetime(snapshot_datetime)
    with session_factory() as session, session.begin():
        account = session.get(InvestmentAccount, investment_account_id)
        if account is None:
            raise ValueError("Investment account was not found")
        duplicate = session.scalar(
            select(InvestmentSnapshot.id).where(
                InvestmentSnapshot.investment_account_id == investment_account_id,
                InvestmentSnapshot.snapshot_datetime == recorded_at,
            )
        )
        if duplicate is not None:
            raise ValueError("An entry already exists for this account and date")
        snapshot = InvestmentSnapshot(
            investment_account_id=investment_account_id,
            snapshot_datetime=recorded_at,
            total_value=total,
            contribution_amount=contribution,
        )
        session.add(snapshot)
        session.flush()
        snapshot_id = snapshot.id
    return snapshot_id
