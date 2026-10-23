from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import aliased

from app.core.db import SessionLocal
from app.models.models import (
    GroupMembership,
    InvestmentAccount,
    InvestmentSnapshot,
    WorkRRSPContribution,
)


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
    employer_matching_enabled: bool
    employer_match_percent: Decimal | None

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
class WorkRrspSummary:
    contribution_count: int = 0
    employee_contribution: Decimal = Decimal("0.00")
    employer_match: Decimal = Decimal("0.00")
    total_contribution: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class WorkRrspContributionRecord:
    id: int
    investment_account_id: int
    contribution_date: date
    employee_contribution: Decimal
    employer_match: Decimal
    total_contribution: Decimal
    created_at: datetime
    updated_at: datetime


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


def calculate_employer_match(
    employee_contribution: Decimal | str | int | float,
    employer_match_rate: Decimal | str | int | float = Decimal("0"),
) -> Decimal:
    """Calculate a saved employer match from an actual paystub contribution."""
    employee = _money(employee_contribution, "Employee contribution")
    if employee < 0:
        raise ValueError("Employee contribution cannot be negative")
    match_percent = _percent(employer_match_rate, "Employer match") or Decimal()
    return (employee * match_percent / Decimal("100")).quantize(
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
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


def _is_work_rrsp(account) -> bool:
    return bool(
        account.is_work_related
        and (account.account_type or "").strip().casefold() == "rrsp"
    )


def _work_rrsp_summary_from_row(row) -> WorkRrspSummary:
    return WorkRrspSummary(
        contribution_count=int(row[0] or 0),
        employee_contribution=row[1] or Decimal("0.00"),
        employer_match=row[2] or Decimal("0.00"),
        total_contribution=row[3] or Decimal("0.00"),
    )


def _query_work_rrsp_summary(session, *conditions) -> WorkRrspSummary:
    row = session.execute(
        select(
            func.count(WorkRRSPContribution.id),
            func.sum(WorkRRSPContribution.employee_contribution),
            func.sum(WorkRRSPContribution.employer_match),
            func.sum(WorkRRSPContribution.total_contribution),
        ).where(*conditions)
    ).one()
    return _work_rrsp_summary_from_row(row)


def _require_work_rrsp_account(session, account_id: int) -> InvestmentAccount:
    account = session.get(InvestmentAccount, account_id)
    if account is None:
        raise ValueError("Investment account was not found")
    if not _is_work_rrsp(account):
        raise ValueError("Contributions can only be recorded for a Work RRSP")
    return account


def create_work_rrsp_contribution(
    investment_account_id: int,
    contribution_date: date | datetime,
    employee_contribution: Decimal | str | int | float,
    *,
    session_factory=SessionLocal,
) -> int:
    employee = _money(employee_contribution, "Employee contribution")
    if employee <= 0:
        raise ValueError("Employee contribution must be greater than zero")
    recorded_on = _as_date(contribution_date)
    with session_factory() as session, session.begin():
        account = _require_work_rrsp_account(session, investment_account_id)
        match = calculate_employer_match(
            employee,
            account.employer_match_percent or Decimal()
            if account.employer_matching_enabled
            else Decimal(),
        )
        contribution = WorkRRSPContribution(
            investment_account_id=account.id,
            contribution_date=recorded_on,
            year=recorded_on.year,
            month=recorded_on.month,
            employee_contribution=employee,
            employer_match=match,
            total_contribution=employee + match,
        )
        session.add(contribution)
        session.flush()
        return contribution.id


def update_work_rrsp_contribution(
    contribution_id: int,
    contribution_date: date | datetime,
    employee_contribution: Decimal | str | int | float,
    *,
    investment_account_id: int | None = None,
    session_factory=SessionLocal,
) -> None:
    employee = _money(employee_contribution, "Employee contribution")
    if employee <= 0:
        raise ValueError("Employee contribution must be greater than zero")
    recorded_on = _as_date(contribution_date)
    with session_factory() as session, session.begin():
        contribution = session.get(WorkRRSPContribution, contribution_id)
        if contribution is None:
            raise ValueError("RRSP contribution was not found")
        account_id = investment_account_id or contribution.investment_account_id
        account = _require_work_rrsp_account(session, account_id)
        match = calculate_employer_match(
            employee,
            account.employer_match_percent or Decimal()
            if account.employer_matching_enabled
            else Decimal(),
        )
        contribution.investment_account_id = account.id
        contribution.contribution_date = recorded_on
        contribution.year = recorded_on.year
        contribution.month = recorded_on.month
        contribution.employee_contribution = employee
        contribution.employer_match = match
        contribution.total_contribution = employee + match


def delete_work_rrsp_contribution(
    contribution_id: int,
    *,
    session_factory=SessionLocal,
) -> None:
    with session_factory() as session, session.begin():
        contribution = session.get(WorkRRSPContribution, contribution_id)
        if contribution is None:
            raise ValueError("RRSP contribution was not found")
        session.delete(contribution)


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
    if not _is_work_rrsp(account):
        return WorkRrspSummary()
    with session_factory() as session:
        return _query_work_rrsp_summary(
            session,
            WorkRRSPContribution.investment_account_id == account.id,
            WorkRRSPContribution.year == year,
            WorkRRSPContribution.month == month,
        )


def get_all_time_work_rrsp_summary(
    investment_account,
    *,
    session_factory=SessionLocal,
) -> WorkRrspSummary:
    account = _work_rrsp_account(investment_account, session_factory)
    if not _is_work_rrsp(account):
        return WorkRrspSummary()
    with session_factory() as session:
        return _query_work_rrsp_summary(
            session,
            WorkRRSPContribution.investment_account_id == account.id,
        )


def get_work_rrsp_contribution_history(
    investment_account,
    *,
    session_factory=SessionLocal,
) -> tuple[WorkRrspContributionRecord, ...]:
    account = _work_rrsp_account(investment_account, session_factory)
    if not _is_work_rrsp(account):
        return ()
    with session_factory() as session:
        rows = session.execute(
            select(
                WorkRRSPContribution.id,
                WorkRRSPContribution.investment_account_id,
                WorkRRSPContribution.contribution_date,
                WorkRRSPContribution.employee_contribution,
                WorkRRSPContribution.employer_match,
                WorkRRSPContribution.total_contribution,
                WorkRRSPContribution.created_at,
                WorkRRSPContribution.updated_at,
            )
            .where(WorkRRSPContribution.investment_account_id == account.id)
            .order_by(
                WorkRRSPContribution.contribution_date.desc(),
                WorkRRSPContribution.id.desc(),
            )
        ).all()
    return tuple(WorkRrspContributionRecord(*row) for row in rows)


def get_owner_work_rrsp_summary(
    year: int,
    month: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> WorkRrspSummary:
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    with session_factory() as session:
        return _query_work_rrsp_summary(
            session,
            _visible_account_scope(user_id, group_id),
            InvestmentAccount.is_active.is_(True),
            InvestmentAccount.is_work_related.is_(True),
            func.lower(func.trim(InvestmentAccount.account_type)) == "rrsp",
            WorkRRSPContribution.investment_account_id == InvestmentAccount.id,
            WorkRRSPContribution.year == year,
            WorkRRSPContribution.month == month,
        )


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
    with session_factory() as session:
        work = _query_work_rrsp_summary(
            session,
            _visible_account_scope(user_id, group_id),
            InvestmentAccount.is_active.is_(True),
            InvestmentAccount.is_work_related.is_(True),
            func.lower(func.trim(InvestmentAccount.account_type)) == "rrsp",
            WorkRRSPContribution.investment_account_id == InvestmentAccount.id,
        )
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
    latest_dates = (
        select(
            InvestmentSnapshot.investment_account_id.label("account_id"),
            func.max(InvestmentSnapshot.snapshot_datetime).label("latest_at"),
        )
        .group_by(InvestmentSnapshot.investment_account_id)
        .subquery()
    )
    latest_snapshot = aliased(InvestmentSnapshot)
    with session_factory() as session:
        rows = session.execute(
            select(
                InvestmentAccount.id,
                InvestmentAccount.institution,
                InvestmentAccount.account_name,
                InvestmentAccount.account_number_last7,
                InvestmentAccount.account_type,
                InvestmentAccount.created_at,
                InvestmentAccount.is_active,
                func.coalesce(latest_snapshot.total_value, Decimal("0.00")),
                latest_snapshot.snapshot_datetime,
                InvestmentAccount.user_id,
                InvestmentAccount.group_id,
                InvestmentAccount.is_work_related,
                InvestmentAccount.employer_matching_enabled,
                InvestmentAccount.employer_match_percent,
            )
            .outerjoin(
                latest_dates,
                latest_dates.c.account_id == InvestmentAccount.id,
            )
            .outerjoin(
                latest_snapshot,
                and_(
                    latest_snapshot.investment_account_id == InvestmentAccount.id,
                    latest_snapshot.snapshot_datetime == latest_dates.c.latest_at,
                ),
            )
            .where(*conditions)
            .order_by(
                InvestmentAccount.account_name,
                InvestmentAccount.institution,
                InvestmentAccount.id,
            )
        ).all()
    return tuple(InvestmentAccountSummary(*row) for row in rows)


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
    accounts = get_investment_accounts(
        user_id=user_id,
        group_id=group_id,
        session_factory=session_factory,
    )
    if not accounts:
        return ()

    conditions = [
        InvestmentSnapshot.investment_account_id.in_(
            tuple(account.id for account in accounts)
        )
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
            .where(*conditions)
            .order_by(
                InvestmentSnapshot.snapshot_datetime,
                InvestmentSnapshot.id,
            )
        ).all()

    account_events: list[tuple[datetime, int, Decimal]] = []
    account_events.extend(
        (row.snapshot_datetime, row.investment_account_id, row.total_value)
        for row in rows
    )
    account_events.sort(key=lambda event: (event[0], event[1]))

    latest_values: dict[int, Decimal] = {}
    points: list[PortfolioPoint] = []
    index = 0
    while index < len(account_events):
        snapshot_datetime = account_events[index][0]
        while (
            index < len(account_events)
            and account_events[index][0] == snapshot_datetime
        ):
            _event_datetime, account_id, total_value = account_events[index]
            latest_values[account_id] = total_value
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


def _get_manual_contributions_by_month(
    start: date,
    end: date,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> dict[tuple[int, int], Decimal]:
    start_datetime = datetime.combine(start, time.min)
    end_datetime = datetime.combine(end, time.min)
    snapshot_year = func.strftime("%Y", InvestmentSnapshot.snapshot_datetime)
    snapshot_month = func.strftime("%m", InvestmentSnapshot.snapshot_datetime)
    with session_factory() as session:
        rows = session.execute(
            select(
                snapshot_year,
                snapshot_month,
                func.sum(InvestmentSnapshot.contribution_amount),
            )
            .join(InvestmentAccount)
            .where(
                _visible_account_scope(user_id, group_id),
                InvestmentSnapshot.snapshot_datetime >= start_datetime,
                InvestmentSnapshot.snapshot_datetime < end_datetime,
                InvestmentSnapshot.contribution_amount.is_not(None),
            )
            .group_by(snapshot_year, snapshot_month)
        ).all()
    return {
        (int(year), int(month)): total
        for year, month, total in rows
    }


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
    previous_start = date(previous_year, previous_month, 1)
    current_end = date(year + (month == 12), month % 12 + 1, 1)
    manual_by_month = _get_manual_contributions_by_month(
        previous_start,
        current_end,
        user_id=user_id,
        group_id=group_id,
        session_factory=session_factory,
    )

    def total_for(month_key: tuple[int, int]) -> Decimal:
        work = get_owner_work_rrsp_summary(
            *month_key,
            user_id=user_id,
            group_id=group_id,
            session_factory=session_factory,
        )
        return (
            manual_by_month.get(month_key, Decimal())
            + work.employee_contribution
            + work.employer_match
        )

    return ContributionComparison(
        current=total_for((year, month)),
        previous=total_for((previous_year, previous_month)),
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
) -> tuple[InvestmentSnapshot | PortfolioPoint, ...]:
    with session_factory() as session:
        account = session.get(InvestmentAccount, account_id)
        if account is None:
            return ()
        session.expunge(account)
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
    snapshot_year = func.strftime("%Y", InvestmentSnapshot.snapshot_datetime)
    snapshot_month = func.strftime("%m", InvestmentSnapshot.snapshot_datetime)
    with session_factory() as session:
        snapshot_months = session.execute(
            select(snapshot_year, snapshot_month)
            .join(InvestmentAccount)
            .where(_visible_account_scope(user_id, group_id))
            .distinct()
        ).all()
    months = {
        (int(year), int(month))
        for year, month in snapshot_months
    }
    with session_factory() as session:
        contribution_months = session.execute(
            select(WorkRRSPContribution.year, WorkRRSPContribution.month)
            .join(InvestmentAccount)
            .where(
                _visible_account_scope(user_id, group_id),
                InvestmentAccount.is_active.is_(True),
                InvestmentAccount.is_work_related.is_(True),
            )
            .distinct()
        ).all()
    months.update((year, month) for year, month in contribution_months)
    return months


def _validated_work_rrsp_settings(
    account_type: str | None,
    is_work_related: bool,
    employer_matching_enabled: bool,
    employer_match_percent,
    *,
    group_id: int | None,
) -> dict[str, object]:
    work_related = bool(is_work_related)
    if not work_related:
        return {
            "is_work_related": False,
            "employer_matching_enabled": False,
            "employer_match_percent": None,
        }
    if (account_type or "").strip().casefold() != "rrsp":
        raise ValueError("Work-related tracking is only available for RRSP accounts")
    if group_id is not None:
        raise ValueError("A work RRSP must belong to a specific user")
    matching = bool(employer_matching_enabled)
    match_percent = _percent(employer_match_percent, "Employer match")
    if matching and match_percent is None:
        raise ValueError("Employer match percentage is required")
    return {
        "is_work_related": True,
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
        employer_matching_enabled,
        employer_match_percent,
        group_id=group_id,
    )
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
    """Permanently delete an account, its snapshots, and its RRSP contributions."""
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
