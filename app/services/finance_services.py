from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Iterable

from sqlalchemy import Select, and_, case, func, or_, select

from app.core.db import SessionLocal
from app.models.models import (
    Account,
    Category,
    GroupMembership,
    InvestmentAccount,
    InvestmentSnapshot,
    MonthlyCategoryBudget,
    SavingsGoal,
    SavingsSnapshot,
    Transaction,
)
from app.services.profiles import visible_owner_scope
from app.utils.constants import TransactionType


@dataclass(frozen=True)
class MonthlyFinancialSummary:
    regular_income: Decimal
    other_income: Decimal
    e_transfer_received: Decimal
    e_transfer_sent: Decimal
    e_transfer_net: Decimal
    e_transfer_income_adjustment: Decimal
    gross_expense_spending: Decimal
    reimbursements: Decimal
    e_transfer_spending_adjustment: Decimal
    total_income: Decimal
    total_spending: Decimal

    @property
    def additional_income(self) -> Decimal:
        return self.other_income

    @property
    def gross_spending(self) -> Decimal:
        return self.gross_expense_spending

    @property
    def net_spending(self) -> Decimal:
        return self.total_spending

    @property
    def categorized_spending(self) -> Decimal:
        return self.gross_expense_spending - self.reimbursements


@dataclass(frozen=True)
class BudgetProgress:
    category_id: int
    category_name: str
    spent: Decimal
    target: Decimal


@dataclass(frozen=True)
class SavingsProgress:
    target: Decimal | None
    actual: Decimal


def _validate_owner(user_id: str | None, group_id: int | None) -> None:
    if (user_id is None) == (group_id is None):
        raise ValueError("Provide exactly one owner: user_id or group_id")


def _account_scope(user_id: str | None, group_id: int | None):
    _validate_owner(user_id, group_id)
    if user_id is not None:
        return Account.user_id == user_id
    member_ids: Select = select(GroupMembership.user_id).where(
        GroupMembership.group_id == group_id
    )
    return or_(Account.group_id == group_id, Account.user_id.in_(member_ids))


def _owner_scope(model, user_id: str | None, group_id: int | None):
    _validate_owner(user_id, group_id)
    return model.user_id == user_id if user_id is not None else model.group_id == group_id


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    if month < 1 or month > 12:
        raise ValueError("month must be between 1 and 12")
    return date(year, month, 1), date(year + (month == 12), month % 12 + 1, 1)


def summarize_transaction_rows(
    rows: Iterable[tuple[Decimal, TransactionType, str | None]],
) -> MonthlyFinancialSummary:
    rows = tuple(rows)
    regular = sum(
        (amount for amount, transaction_type, category in rows
         if transaction_type == TransactionType.INCOME and category == "Salary"),
        Decimal(),
    )
    other = sum(
        (amount for amount, transaction_type, category in rows
         if transaction_type == TransactionType.INCOME and category == "Other Income"),
        Decimal(),
    )
    e_transfer_received = sum(
        (amount for amount, transaction_type, _ in rows
         if transaction_type == TransactionType.E_TRANSFER and amount > 0),
        Decimal(),
    )
    e_transfer_sent = sum(
        (-amount for amount, transaction_type, _ in rows
         if transaction_type == TransactionType.E_TRANSFER and amount < 0),
        Decimal(),
    )
    e_transfer_net = e_transfer_received - e_transfer_sent
    e_transfer_income_adjustment = max(e_transfer_net, Decimal())
    gross = sum(
        (abs(amount) for amount, transaction_type, _ in rows
         if transaction_type == TransactionType.EXPENSE),
        Decimal(),
    )
    refunds = sum(
        (amount for amount, transaction_type, _ in rows
         if transaction_type == TransactionType.REFUND_REIMBURSEMENT),
        Decimal(),
    )
    e_transfer_spending_adjustment = max(-e_transfer_net, Decimal())
    return MonthlyFinancialSummary(
        regular_income=regular,
        other_income=other,
        e_transfer_received=e_transfer_received,
        e_transfer_sent=e_transfer_sent,
        e_transfer_net=e_transfer_net,
        e_transfer_income_adjustment=e_transfer_income_adjustment,
        gross_expense_spending=gross,
        reimbursements=refunds,
        e_transfer_spending_adjustment=e_transfer_spending_adjustment,
        total_income=regular + other + e_transfer_income_adjustment,
        total_spending=gross - refunds + e_transfer_spending_adjustment,
    )


def combine_financial_summaries(
    summaries: Iterable[MonthlyFinancialSummary],
) -> MonthlyFinancialSummary:
    summaries = tuple(summaries)
    field_names = (
        "regular_income",
        "other_income",
        "e_transfer_received",
        "e_transfer_sent",
        "e_transfer_net",
        "e_transfer_income_adjustment",
        "gross_expense_spending",
        "reimbursements",
        "e_transfer_spending_adjustment",
        "total_income",
        "total_spending",
    )
    return MonthlyFinancialSummary(**{
        name: sum((getattr(summary, name) for summary in summaries), Decimal())
        for name in field_names
    })


def monthly_financial_summary(
    year: int,
    month: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> MonthlyFinancialSummary:
    start, end = _month_bounds(year, month)
    signed_amount = case(
        (
            Transaction.transaction_type == TransactionType.EXPENSE,
            func.abs(Transaction.amount),
        ),
        else_=Transaction.amount,
    )
    sign_bucket = case(
        (Transaction.amount > 0, 1),
        (Transaction.amount < 0, -1),
        else_=0,
    )
    with session_factory() as session:
        rows = session.execute(
            select(
                func.sum(signed_amount),
                Transaction.transaction_type,
                Category.name,
                sign_bucket,
            )
            .join(Account, Transaction.account_id == Account.id)
            .outerjoin(Category, Transaction.category_id == Category.id)
            .where(
                _account_scope(user_id, group_id),
                Transaction.is_deleted.is_(False),
                Transaction.transaction_date >= start,
                Transaction.transaction_date < end,
            )
            .group_by(
                Transaction.transaction_type,
                Category.name,
                sign_bucket,
            )
        ).all()

    return summarize_transaction_rows(
        (amount, transaction_type, category)
        for amount, transaction_type, category, _sign in rows
    )


def category_spending_totals(
    year: int,
    month: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> dict[int, Decimal]:
    start, end = _month_bounds(year, month)
    spending_amount = case(
        (
            Transaction.transaction_type == TransactionType.EXPENSE,
            func.abs(Transaction.amount),
        ),
        else_=-Transaction.amount,
    )
    with session_factory() as session:
        rows = session.execute(
            select(
                Transaction.category_id,
                func.sum(spending_amount),
            )
            .join(Account, Transaction.account_id == Account.id)
            .where(
                _account_scope(user_id, group_id),
                Transaction.is_deleted.is_(False),
                Transaction.category_id.is_not(None),
                Transaction.transaction_date >= start,
                Transaction.transaction_date < end,
                Transaction.transaction_type.in_((
                    TransactionType.EXPENSE,
                    TransactionType.REFUND_REIMBURSEMENT,
                )),
            )
            .group_by(Transaction.category_id)
        ).all()

    return {category_id: amount for category_id, amount in rows}


def monthly_budget_progress(
    year: int,
    month: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> tuple[BudgetProgress, ...]:
    spending = category_spending_totals(
        year, month, user_id=user_id, group_id=group_id,
        session_factory=session_factory,
    )
    with session_factory() as session:
        rows = session.execute(
            select(
                MonthlyCategoryBudget.category_id,
                Category.name,
                MonthlyCategoryBudget.target_amount,
            )
            .join(Category, MonthlyCategoryBudget.category_id == Category.id)
            .where(
                _owner_scope(MonthlyCategoryBudget, user_id, group_id),
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
    effective: dict[int, tuple[str, Decimal]] = {}
    for category_id, name, target in rows:
        effective.setdefault(category_id, (name, target))
    return tuple(
        BudgetProgress(category_id, name, spending.get(category_id, Decimal()), target)
        for category_id, (name, target) in sorted(
            effective.items(), key=lambda item: item[1][0].casefold()
        )
        if target > 0
    )


def savings_goal_progress(
    year: int,
    month: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> SavingsProgress:
    start, end = _month_bounds(year, month)
    with session_factory() as session:
        target = session.scalar(
            select(SavingsGoal.target_amount)
            .where(
                _owner_scope(SavingsGoal, user_id, group_id),
                or_(
                    SavingsGoal.year < year,
                    and_(SavingsGoal.year == year, SavingsGoal.month <= month),
                ),
            )
            .order_by(SavingsGoal.year.desc(), SavingsGoal.month.desc())
            .limit(1)
        )
        actual = sum(session.scalars(
            select(SavingsSnapshot.amount_saved_this_month).where(
                visible_owner_scope(SavingsSnapshot, user_id, group_id),
                SavingsSnapshot.snapshot_date >= start,
                SavingsSnapshot.snapshot_date < end,
            )
        ), Decimal())
    return SavingsProgress(target, actual)


def investment_contribution_totals(
    year: int,
    month: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> Decimal:
    from app.services.investments import get_monthly_contributions

    return get_monthly_contributions(
        year,
        month,
        user_id=user_id,
        group_id=group_id,
        session_factory=session_factory,
    )


def investment_value_history(
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> tuple[tuple[date, str, Decimal], ...]:
    from app.services.investments import _visible_account_scope

    with session_factory() as session:
        rows = session.execute(
            select(
                InvestmentSnapshot.snapshot_datetime,
                InvestmentAccount.account_name,
                InvestmentSnapshot.total_value,
            )
            .join(InvestmentAccount)
            .where(_visible_account_scope(user_id, group_id))
            .order_by(
                InvestmentSnapshot.snapshot_datetime,
                InvestmentAccount.account_name,
            )
        ).all()
    return tuple((recorded_at.date(), name, value) for recorded_at, name, value in rows)


def set_savings_goal(
    year: int,
    month: int,
    target_amount: Decimal,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> None:
    _month_bounds(year, month)
    with session_factory.begin() as session:
        goal = session.scalar(select(SavingsGoal).where(
            _owner_scope(SavingsGoal, user_id, group_id),
            SavingsGoal.year == year,
            SavingsGoal.month == month,
        ))
        if goal is None:
            session.add(SavingsGoal(
                user_id=user_id,
                group_id=group_id,
                year=year,
                month=month,
                target_amount=target_amount,
            ))
        else:
            goal.target_amount = target_amount


def set_monthly_category_budget(
    category_id: int,
    year: int,
    month: int,
    target_amount: Decimal,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> None:
    _month_bounds(year, month)
    with session_factory.begin() as session:
        budget = session.scalar(select(MonthlyCategoryBudget).where(
            _owner_scope(MonthlyCategoryBudget, user_id, group_id),
            MonthlyCategoryBudget.category_id == category_id,
            MonthlyCategoryBudget.year == year,
            MonthlyCategoryBudget.month == month,
        ))
        if budget is None:
            session.add(MonthlyCategoryBudget(
                user_id=user_id,
                group_id=group_id,
                category_id=category_id,
                year=year,
                month=month,
                target_amount=target_amount,
            ))
        else:
            budget.target_amount = target_amount


def record_investment_snapshot(
    account_name: str,
    snapshot_date: date,
    monthly_contribution: Decimal,
    portfolio_value: Decimal,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> None:
    """Backward-compatible helper for the original account-name API."""
    account_name = account_name.strip()
    if not account_name:
        raise ValueError("account_name is required")
    _validate_owner(user_id, group_id)
    with session_factory() as session, session.begin():
        account = session.scalar(select(InvestmentAccount).where(
            _owner_scope(InvestmentAccount, user_id, group_id),
            InvestmentAccount.account_name == account_name,
        ))
        if account is None:
            account = InvestmentAccount(
                user_id=user_id,
                group_id=group_id,
                institution="Manual",
                account_name=account_name,
                account_number_last7=None,
                is_active=True,
            )
            session.add(account)
            session.flush()
        recorded_at = datetime.combine(snapshot_date, time.min)
        snapshot = session.scalar(select(InvestmentSnapshot).where(
            InvestmentSnapshot.investment_account_id == account.id,
            InvestmentSnapshot.snapshot_datetime == recorded_at,
        ))
        if snapshot is None:
            session.add(InvestmentSnapshot(
                investment_account_id=account.id,
                snapshot_datetime=recorded_at,
                contribution_amount=monthly_contribution,
                total_value=portfolio_value,
            ))
        else:
            snapshot.contribution_amount = monthly_contribution
            snapshot.total_value = portfolio_value


def record_savings_snapshot(
    snapshot_date: date,
    amount_saved_this_month: Decimal,
    total_savings_balance: Decimal | None = None,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
    session_factory=SessionLocal,
) -> None:
    with session_factory.begin() as session:
        snapshot = session.scalar(select(SavingsSnapshot).where(
            _owner_scope(SavingsSnapshot, user_id, group_id),
            SavingsSnapshot.snapshot_date == snapshot_date,
        ))
        if snapshot is None:
            session.add(SavingsSnapshot(
                user_id=user_id,
                group_id=group_id,
                snapshot_date=snapshot_date,
                amount_saved_this_month=amount_saved_this_month,
                total_savings_balance=total_savings_balance,
            ))
        else:
            snapshot.amount_saved_this_month = amount_saved_this_month
            snapshot.total_savings_balance = total_savings_balance
