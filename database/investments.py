from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from database.db import SessionLocal
from database.models import GroupMembership, InvestmentAccount, InvestmentSnapshot


MONEY_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class InvestmentAccountSummary:
    id: int
    institution: str
    account_name: str
    account_number_last7: str | None
    account_type: str | None
    is_active: bool
    current_value: Decimal
    last_updated: datetime | None
    user_id: str | None
    group_id: int | None

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


def normalize_account_number_last7(value: str | None) -> str | None:
    characters = re.sub(r"[^A-Za-z0-9]", "", value or "").upper()
    if not characters:
        return None
    return characters[-7:]


def _as_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    return datetime.combine(value, time.min)


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
                is_active=account.is_active,
                current_value=(latest.total_value if latest else Decimal("0.00")),
                last_updated=(latest.snapshot_datetime if latest else None),
                user_id=account.user_id,
                group_id=account.group_id,
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
    return {(value.year, value.month) for value in dates}


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
