from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, delete, or_, select

from app.core.db import SessionLocal
from app.services.finance_services import monthly_financial_summary
from app.services.investments import get_owner_work_rrsp_summary
from app.models.models import (
    Category,
    LongTermSavingsGoal,
    MonthlyCategoryBudget,
    SavingsGoal,
    Transaction,
)
from app.services.profiles import direct_owner_scope, validate_owner, visible_account_scope
from app.utils.constants import TransactionType


@dataclass(frozen=True)
class MonthlySavingsBreakdown:
    income: Decimal
    spending: Decimal
    work_rrsp_employee: Decimal
    work_rrsp_employer: Decimal
    net_savings: Decimal
    target: Decimal | None


@dataclass(frozen=True)
class CategoryBudgetProgress:
    category_id: int
    category_name: str
    category_color: str
    spent: Decimal
    target: Decimal

    @property
    def remaining(self) -> Decimal:
        return self.target - self.spent

    @property
    def percent(self) -> Decimal:
        if self.target <= 0:
            return Decimal()
        return self.spent / self.target * Decimal(100)


@dataclass(frozen=True)
class SavingsGoalRecord:
    id: int
    name: str
    target_amount: Decimal
    current_amount: Decimal
    target_date: date | None
    notes: str | None

    @property
    def percent(self) -> Decimal:
        if self.target_amount <= 0:
            return Decimal()
        return self.current_amount / self.target_amount * Decimal(100)


def _owner_kwargs(user_id: str | None, group_id: int | None) -> dict:
    validate_owner(user_id, group_id)
    return {"user_id": user_id, "group_id": group_id}


def get_monthly_savings_goal(
    year: int,
    month: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> Decimal | None:
    """Return the most recent goal effective on or before the requested month."""
    validate_owner(user_id, group_id)
    if month not in range(1, 13):
        raise ValueError("Month must be between 1 and 12.")
    with session_factory() as session:
        return session.scalar(
            select(SavingsGoal.target_amount)
            .where(
                direct_owner_scope(SavingsGoal, user_id, group_id),
                or_(
                    SavingsGoal.year < year,
                    and_(SavingsGoal.year == year, SavingsGoal.month <= month),
                ),
            )
            .order_by(SavingsGoal.year.desc(), SavingsGoal.month.desc())
            .limit(1)
        )


def set_monthly_savings_goal(
    year: int,
    month: int,
    target_amount: Decimal,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> None:
    validate_owner(user_id, group_id)
    target_amount = Decimal(target_amount).quantize(Decimal("0.01"))
    if target_amount <= 0:
        raise ValueError("The monthly savings goal must be greater than zero.")
    if month not in range(1, 13):
        raise ValueError("Month must be between 1 and 12.")
    with session_factory.begin() as session:
        goal = session.scalar(select(SavingsGoal).where(
            direct_owner_scope(SavingsGoal, user_id, group_id),
            SavingsGoal.year == year,
            SavingsGoal.month == month,
        ))
        if goal is None:
            session.add(SavingsGoal(
                **_owner_kwargs(user_id, group_id),
                year=year,
                month=month,
                target_amount=target_amount,
            ))
        else:
            goal.target_amount = target_amount


def get_monthly_savings_breakdown(
    year: int,
    month: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> MonthlySavingsBreakdown:
    """Return the exact Goals formula; SavingsSnapshot is intentionally unused."""
    validate_owner(user_id, group_id)
    finances = monthly_financial_summary(
        year, month, user_id=user_id, group_id=group_id,
        session_factory=session_factory,
    )
    rrsp = get_owner_work_rrsp_summary(
        year, month, user_id=user_id, group_id=group_id,
        session_factory=session_factory,
    )
    # RRSP funds are invested/locked away rather than currently usable cash,
    # so they remain visible in the breakdown but do not advance this goal.
    net = finances.total_income - finances.total_spending
    return MonthlySavingsBreakdown(
        income=finances.total_income,
        spending=finances.total_spending,
        work_rrsp_employee=rrsp.employee_contribution,
        work_rrsp_employer=rrsp.employer_match,
        net_savings=net,
        target=get_monthly_savings_goal(
            year, month, user_id=user_id, group_id=group_id,
            session_factory=session_factory,
        ),
    )


def list_budget_categories(*, session_factory=SessionLocal) -> tuple[tuple[int, str, str], ...]:
    with session_factory() as session:
        rows = session.execute(
            select(Category.id, Category.name, Category.color)
            .order_by(Category.name)
        ).all()
    return tuple(rows)


def get_category_budgets(
    year: int,
    month: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> tuple[CategoryBudgetProgress, ...]:
    """Return each category's latest budget effective for the requested month."""
    validate_owner(user_id, group_id)
    if month not in range(1, 13):
        raise ValueError("Month must be between 1 and 12.")
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    with session_factory() as session:
        spending_rows = session.execute(
            select(Transaction.category_id, Transaction.amount)
            .join(Transaction.account)
            .where(
                visible_account_scope(user_id, group_id),
                Transaction.is_deleted.is_(False),
                Transaction.transaction_type == TransactionType.EXPENSE,
                Transaction.category_id.is_not(None),
                Transaction.transaction_date >= start,
                Transaction.transaction_date < end,
            )
        ).all()
        budget_rows = session.execute(
            select(
                MonthlyCategoryBudget.category_id,
                Category.name,
                Category.color,
                MonthlyCategoryBudget.target_amount,
            )
            .join(Category, MonthlyCategoryBudget.category_id == Category.id)
            .where(
                direct_owner_scope(MonthlyCategoryBudget, user_id, group_id),
                or_(
                    MonthlyCategoryBudget.year < year,
                    and_(
                        MonthlyCategoryBudget.year == year,
                        MonthlyCategoryBudget.month <= month,
                    ),
                ),
            )
            .order_by(
                MonthlyCategoryBudget.year.desc(),
                MonthlyCategoryBudget.month.desc(),
            )
        ).all()
    totals: dict[int, Decimal] = {}
    for category_id, amount in spending_rows:
        totals[category_id] = totals.get(category_id, Decimal()) + abs(amount)
    effective: dict[int, tuple[str, str, Decimal]] = {}
    for category_id, name, color, target in budget_rows:
        effective.setdefault(category_id, (name, color, target))
    return tuple(
        CategoryBudgetProgress(
            category_id,
            name,
            color,
            totals.get(category_id, Decimal()),
            target,
        )
        for category_id, (name, color, target) in sorted(
            effective.items(), key=lambda item: item[1][0].casefold()
        )
        if target > 0
    )


def create_or_update_category_budget(
    category_id: int,
    year: int,
    month: int,
    target_amount: Decimal,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> None:
    validate_owner(user_id, group_id)
    target_amount = Decimal(target_amount).quantize(Decimal("0.01"))
    if target_amount <= 0:
        raise ValueError("The category budget must be greater than zero.")
    if month not in range(1, 13):
        raise ValueError("Month must be between 1 and 12.")
    with session_factory.begin() as session:
        if session.get(Category, category_id) is None:
            raise ValueError("The selected category no longer exists.")
        budget = session.scalar(select(MonthlyCategoryBudget).where(
            direct_owner_scope(MonthlyCategoryBudget, user_id, group_id),
            MonthlyCategoryBudget.category_id == category_id,
            MonthlyCategoryBudget.year == year,
            MonthlyCategoryBudget.month == month,
        ))
        if budget is None:
            session.add(MonthlyCategoryBudget(
                **_owner_kwargs(user_id, group_id),
                category_id=category_id,
                year=year,
                month=month,
                target_amount=target_amount,
            ))
        else:
            budget.target_amount = target_amount


def delete_category_budget(
    category_id: int,
    year: int,
    month: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> None:
    """Stop a carried budget from this month onward without changing history."""
    validate_owner(user_id, group_id)
    if month not in range(1, 13):
        raise ValueError("Month must be between 1 and 12.")
    with session_factory.begin() as session:
        effective = session.scalar(
            select(MonthlyCategoryBudget)
            .where(
                direct_owner_scope(MonthlyCategoryBudget, user_id, group_id),
                MonthlyCategoryBudget.category_id == category_id,
                or_(
                    MonthlyCategoryBudget.year < year,
                    and_(
                        MonthlyCategoryBudget.year == year,
                        MonthlyCategoryBudget.month <= month,
                    ),
                ),
            )
            .order_by(
                MonthlyCategoryBudget.year.desc(),
                MonthlyCategoryBudget.month.desc(),
            )
            .limit(1)
        )
        if effective is None or effective.target_amount <= 0:
            return
        current = session.scalar(select(MonthlyCategoryBudget).where(
            direct_owner_scope(MonthlyCategoryBudget, user_id, group_id),
            MonthlyCategoryBudget.category_id == category_id,
            MonthlyCategoryBudget.year == year,
            MonthlyCategoryBudget.month == month,
        ))
        if current is None:
            session.add(MonthlyCategoryBudget(
                **_owner_kwargs(user_id, group_id),
                category_id=category_id,
                year=year,
                month=month,
                target_amount=Decimal("0.00"),
            ))
        else:
            current.target_amount = Decimal("0.00")


def get_savings_goals(
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    include_archived: bool = False,
    session_factory=SessionLocal,
) -> tuple[SavingsGoalRecord, ...]:
    validate_owner(user_id, group_id)
    filters = [direct_owner_scope(LongTermSavingsGoal, user_id, group_id)]
    if not include_archived:
        filters.append(LongTermSavingsGoal.is_archived.is_(False))
    with session_factory() as session:
        rows = session.scalars(
            select(LongTermSavingsGoal).where(*filters)
            .order_by(LongTermSavingsGoal.target_date.is_(None), LongTermSavingsGoal.target_date, LongTermSavingsGoal.name)
        ).all()
        return tuple(SavingsGoalRecord(
            item.id, item.name, item.target_amount, item.current_amount,
            item.target_date, item.notes,
        ) for item in rows)


def _validate_long_term_values(name: str, target_amount: Decimal, current_amount: Decimal) -> tuple[str, Decimal, Decimal]:
    name = name.strip()
    target_amount = Decimal(target_amount).quantize(Decimal("0.01"))
    current_amount = Decimal(current_amount).quantize(Decimal("0.01"))
    if not name:
        raise ValueError("Enter a goal name.")
    if len(name) > 120:
        raise ValueError("Goal names must be at most 120 characters.")
    if target_amount <= 0:
        raise ValueError("The target amount must be greater than zero.")
    if current_amount < 0:
        raise ValueError("The current amount cannot be negative.")
    return name, target_amount, current_amount


def create_savings_goal(
    name: str,
    target_amount: Decimal,
    current_amount: Decimal = Decimal(),
    target_date: date | None = None,
    notes: str | None = None,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> int:
    validate_owner(user_id, group_id)
    name, target_amount, current_amount = _validate_long_term_values(name, target_amount, current_amount)
    with session_factory.begin() as session:
        item = LongTermSavingsGoal(
            **_owner_kwargs(user_id, group_id), name=name,
            target_amount=target_amount, current_amount=current_amount,
            target_date=target_date, notes=(notes or "").strip() or None,
        )
        session.add(item)
        session.flush()
        return item.id


def update_savings_goal(
    goal_id: int,
    name: str,
    target_amount: Decimal,
    current_amount: Decimal,
    target_date: date | None = None,
    notes: str | None = None,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> None:
    validate_owner(user_id, group_id)
    name, target_amount, current_amount = _validate_long_term_values(name, target_amount, current_amount)
    with session_factory.begin() as session:
        item = session.scalar(select(LongTermSavingsGoal).where(
            LongTermSavingsGoal.id == goal_id,
            direct_owner_scope(LongTermSavingsGoal, user_id, group_id),
        ))
        if item is None:
            raise ValueError("The savings goal no longer exists.")
        item.name = name
        item.target_amount = target_amount
        item.current_amount = current_amount
        item.target_date = target_date
        item.notes = (notes or "").strip() or None


def archive_savings_goal(
    goal_id: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> None:
    validate_owner(user_id, group_id)
    with session_factory.begin() as session:
        item = session.scalar(select(LongTermSavingsGoal).where(
            LongTermSavingsGoal.id == goal_id,
            direct_owner_scope(LongTermSavingsGoal, user_id, group_id),
        ))
        if item is not None:
            item.is_archived = True


def delete_savings_goal(
    goal_id: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> None:
    validate_owner(user_id, group_id)
    with session_factory.begin() as session:
        session.execute(delete(LongTermSavingsGoal).where(
            LongTermSavingsGoal.id == goal_id,
            direct_owner_scope(LongTermSavingsGoal, user_id, group_id),
        ))
