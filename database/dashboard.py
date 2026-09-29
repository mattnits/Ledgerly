from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from database.db import SessionLocal
from database.finance_services import (
    BudgetProgress,
    MonthlyFinancialSummary,
    combine_financial_summaries,
    summarize_transaction_rows,
)
from database.models import (
    Account,
    Category,
    InvestmentSnapshot,
    MonthlyCategoryBudget,
    SavingsGoal,
    SavingsSnapshot,
    Transaction,
)
from utils.constants import TransactionType


INCOME_ACCOUNT_COLORS = (
    "#63dba0", "#35bdd0", "#9cc85b", "#5f7cff", "#4fd1a5", "#8ccf78",
)
SPENDING_ACCOUNT_COLORS = (
    "#f16f88", "#e05b68", "#f2a84b", "#cf78dc",
    "#ef7aa8", "#bd6a80", "#a66bff", "#e8895c",
)


@dataclass(frozen=True)
class ChartSeries:
    name: str
    color: str
    values: tuple[Decimal, ...]


@dataclass(frozen=True)
class CategorySpending:
    name: str
    color: str
    amount: Decimal


@dataclass(frozen=True)
class AccountSpending:
    name: str
    amount: Decimal


@dataclass(frozen=True)
class RecentTransaction:
    description: str
    account_name: str
    transaction_date: date
    amount: Decimal
    category_color: str


@dataclass(frozen=True)
class DashboardData:
    period_label: str
    month_labels: tuple[str, ...]
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
    account_spending: tuple[AccountSpending, ...]
    investing_total: Decimal
    savings_goal: Decimal | None
    savings_actual: Decimal
    savings_balance: Decimal | None
    budget_progress: tuple[BudgetProgress, ...]
    portfolio_value: Decimal
    previous_portfolio_value: Decimal | None
    investment_month_labels: tuple[str, ...]
    investment_value_series: tuple[Decimal, ...]
    previous_income: Decimal | None
    previous_spending: Decimal | None
    income_series: tuple[ChartSeries, ...]
    spending_series: tuple[ChartSeries, ...]
    cash_flow_income: tuple[Decimal, ...]
    cash_flow_spending: tuple[Decimal, ...]
    category_spending: tuple[CategorySpending, ...]
    recent_transactions: tuple[RecentTransaction, ...]

    @property
    def additional_income(self) -> Decimal:
        return self.other_income

    @property
    def income_total(self) -> Decimal:
        return self.total_income

    @property
    def gross_spending(self) -> Decimal:
        return self.gross_expense_spending

    @property
    def spending_total(self) -> Decimal:
        return self.total_spending


@dataclass(frozen=True)
class _TransactionData:
    transaction_date: date
    description: str
    amount: Decimal
    transaction_type: TransactionType
    account_id: int
    account_name: str
    category_id: int | None
    category_name: str | None
    category_color: str | None


def _month_before(month: tuple[int, int]) -> tuple[int, int]:
    year, month_number = month
    return year - (month_number == 1), (month_number - 2) % 12 + 1


def _month_sequence(
    first: tuple[int, int],
    last: tuple[int, int],
) -> list[tuple[int, int]]:
    result = []
    year, month = first
    while (year, month) <= last:
        result.append((year, month))
        year, month = year + (month == 12), month % 12 + 1
    return result


def _income_source(item: _TransactionData) -> str | None:
    if item.transaction_type != TransactionType.INCOME:
        return None
    name = (item.category_name or "").strip().casefold()
    if name == "salary":
        return "salary"
    if name == "other income":
        return "other"
    return None


def _period_totals(
    transactions: list[_TransactionData],
    month: tuple[int, int],
) -> tuple[Decimal, Decimal]:
    selected = [
        item for item in transactions
        if (item.transaction_date.year, item.transaction_date.month) == month
    ]
    summary = _summarize(selected)
    return summary.total_income, summary.total_spending


def _summarize(transactions: list[_TransactionData]) -> MonthlyFinancialSummary:
    return summarize_transaction_rows(
        (item.amount, item.transaction_type, item.category_name)
        for item in transactions
    )


def _summarize_by_month(
    transactions: list[_TransactionData],
) -> MonthlyFinancialSummary:
    grouped: defaultdict[tuple[int, int], list[_TransactionData]] = defaultdict(list)
    for item in transactions:
        grouped[(item.transaction_date.year, item.transaction_date.month)].append(item)
    return combine_financial_summaries(_summarize(items) for items in grouped.values())


def get_dashboard_data(
    user_id: str | None,
    period: str,
    selected_month: tuple[int, int],
    session_factory=SessionLocal,
) -> DashboardData:
    if period not in ("monthly", "all"):
        raise ValueError(f"Unsupported dashboard period: {period}")

    rows = []
    account_rows: list[tuple[int, str]] = []
    investment_rows: list[tuple[date, str, Decimal, Decimal]] = []
    savings_goal_rows: list[tuple[int, int, Decimal]] = []
    savings_rows: list[tuple[date, Decimal, Decimal | None]] = []
    budget_rows: list[tuple[int, str, int, int, Decimal]] = []
    if user_id is not None:
        with session_factory() as session:
            account_rows = list(session.execute(
                select(Account.id, Account.name)
                .where(Account.user_id == user_id)
                .order_by(Account.id)
            ).all())
            rows = session.execute(
                select(
                    Transaction.transaction_date,
                    Transaction.description,
                    Transaction.amount,
                    Transaction.transaction_type,
                    Account.id,
                    Account.name,
                    Category.id,
                    Category.name,
                    Category.color,
                )
                .join(Account, Transaction.account_id == Account.id)
                .outerjoin(Category, Transaction.category_id == Category.id)
                .where(
                    Account.user_id == user_id,
                    Transaction.is_deleted.is_(False),
                )
                .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
            ).all()
            investment_rows = list(session.execute(
                select(
                    InvestmentSnapshot.snapshot_date,
                    InvestmentSnapshot.account_name,
                    InvestmentSnapshot.monthly_contribution,
                    InvestmentSnapshot.portfolio_value,
                ).where(InvestmentSnapshot.user_id == user_id)
            ).all())
            savings_goal_rows = list(session.execute(
                select(
                    SavingsGoal.year,
                    SavingsGoal.month,
                    SavingsGoal.target_amount,
                ).where(SavingsGoal.user_id == user_id)
            ).all())
            savings_rows = list(session.execute(
                select(
                    SavingsSnapshot.snapshot_date,
                    SavingsSnapshot.amount_saved_this_month,
                    SavingsSnapshot.total_savings_balance,
                )
                .where(SavingsSnapshot.user_id == user_id)
                .order_by(SavingsSnapshot.snapshot_date)
            ).all())
            budget_rows = list(session.execute(
                select(
                    MonthlyCategoryBudget.category_id,
                    Category.name,
                    MonthlyCategoryBudget.year,
                    MonthlyCategoryBudget.month,
                    MonthlyCategoryBudget.target_amount,
                )
                .join(Category, MonthlyCategoryBudget.category_id == Category.id)
                .where(MonthlyCategoryBudget.user_id == user_id)
                .order_by(Category.name)
            ).all())

    transactions = [_TransactionData(*row) for row in rows]
    today = date.today()

    if period == "monthly":
        timeline = _month_sequence((selected_month[0], 1), selected_month)
        selected = [
            item for item in transactions
            if (item.transaction_date.year, item.transaction_date.month) == selected_month
        ]
        previous_income, previous_spending = _period_totals(
            transactions, _month_before(selected_month)
        )
        period_label = date(*selected_month, 1).strftime("%B %Y")
    else:
        transaction_months = [
            (item.transaction_date.year, item.transaction_date.month)
            for item in transactions
        ]
        current_month = (today.year, today.month)
        timeline = _month_sequence(
            min(transaction_months, default=current_month),
            max(transaction_months, default=current_month),
        )
        selected = transactions
        previous_income = previous_spending = None
        period_label = "All time"

    one_year = len({year for year, _ in timeline}) == 1
    month_labels = tuple(
        date(year, month, 1).strftime("%b" if one_year else "%b %y")
        for year, month in timeline
    )
    timeline_index = {month: index for index, month in enumerate(timeline)}

    income_accounts: dict[int, tuple[str, list[Decimal]]] = {}
    spending_accounts: dict[int, tuple[str, list[Decimal]]] = {}
    cash_flow_income = [Decimal() for _ in timeline]
    cash_flow_spending = [Decimal() for _ in timeline]
    e_transfer_by_month: defaultdict[tuple[int, int], Decimal] = defaultdict(Decimal)

    for item in transactions:
        index = timeline_index.get((item.transaction_date.year, item.transaction_date.month))
        if index is None:
            continue
        if item.transaction_type == TransactionType.E_TRANSFER:
            e_transfer_by_month[
                (item.transaction_date.year, item.transaction_date.month)
            ] += item.amount
        elif _income_source(item) is not None:
            _, values = income_accounts.setdefault(
                item.account_id,
                (item.account_name, [Decimal() for _ in timeline]),
            )
            values[index] += item.amount
            cash_flow_income[index] += item.amount
        elif item.transaction_type in (
            TransactionType.EXPENSE,
            TransactionType.REFUND_REIMBURSEMENT,
        ):
            _, values = spending_accounts.setdefault(
                item.account_id,
                (item.account_name, [Decimal() for _ in timeline]),
            )
            amount = (
                abs(item.amount)
                if item.transaction_type == TransactionType.EXPENSE
                else -item.amount
            )
            values[index] += amount
            cash_flow_spending[index] += amount

    e_transfer_income_values = [Decimal() for _ in timeline]
    e_transfer_spending_values = [Decimal() for _ in timeline]
    for month, net in e_transfer_by_month.items():
        index = timeline_index[month]
        if net > 0:
            e_transfer_income_values[index] = net
            cash_flow_income[index] += net
        elif net < 0:
            e_transfer_spending_values[index] = -net
            cash_flow_spending[index] += -net
    if any(e_transfer_income_values):
        income_accounts[-1] = ("Net E-Transfers", e_transfer_income_values)
    if any(e_transfer_spending_values):
        spending_accounts[-1] = ("Net E-Transfers", e_transfer_spending_values)

    def make_series(
        grouped: dict[int, tuple[str, list[Decimal]]],
        colors: tuple[str, ...],
    ) -> tuple[ChartSeries, ...]:
        return tuple(
            ChartSeries(name, colors[index % len(colors)], tuple(values))
            for index, (_, (name, values)) in enumerate(
                sorted(grouped.items(), key=lambda value: (value[1][0].casefold(), value[0]))
            )
            if any(values)
        )

    summary = (
        _summarize(selected)
        if period == "monthly"
        else _summarize_by_month(selected)
    )

    gross_spending_by_account: defaultdict[int, Decimal] = defaultdict(Decimal)
    for item in selected:
        if item.transaction_type == TransactionType.EXPENSE:
            gross_spending_by_account[item.account_id] += abs(item.amount)
    account_spending = tuple(
        AccountSpending(
            account_name,
            gross_spending_by_account.get(account_id, Decimal()),
        )
        for account_id, account_name in account_rows
    )

    category_totals: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    category_totals_by_id: defaultdict[int, Decimal] = defaultdict(Decimal)
    for item in selected:
        if item.category_name is None:
            continue
        key = (item.category_name, item.category_color or "#718096")
        if item.transaction_type == TransactionType.EXPENSE:
            category_totals[key] += abs(item.amount)
            if item.category_id is not None:
                category_totals_by_id[item.category_id] += abs(item.amount)
        elif item.transaction_type == TransactionType.REFUND_REIMBURSEMENT:
            category_totals[key] -= item.amount
            if item.category_id is not None:
                category_totals_by_id[item.category_id] -= item.amount

    category_spending = tuple(
        CategorySpending(name, color, amount)
        for (name, color), amount in sorted(
            category_totals.items(),
            key=lambda value: (-value[1], value[0][0].casefold()),
        )
        if amount > 0
    )

    selected_budget_rows = [
        row for row in budget_rows
        if period == "all" or (row[2], row[3]) == selected_month
    ]
    budget_targets: dict[int, tuple[str, Decimal]] = {}
    for category_id, name, _, _, target in selected_budget_rows:
        previous_name, previous_target = budget_targets.get(
            category_id, (name, Decimal())
        )
        budget_targets[category_id] = (previous_name, previous_target + target)
    budget_progress = tuple(
        BudgetProgress(
            category_id,
            name,
            max(category_totals_by_id.get(category_id, Decimal()), Decimal()),
            target,
        )
        for category_id, (name, target) in sorted(
            budget_targets.items(), key=lambda item: item[1][0].casefold()
        )
    )

    selected_goal_rows = [
        row for row in savings_goal_rows
        if period == "all" or (row[0], row[1]) == selected_month
    ]
    savings_goal = (
        sum((row[2] for row in selected_goal_rows), Decimal())
        if selected_goal_rows
        else None
    )
    selected_savings_rows = [
        row for row in savings_rows
        if period == "all" or (row[0].year, row[0].month) == selected_month
    ]
    savings_actual = sum((row[1] for row in selected_savings_rows), Decimal())
    balance_rows = [row for row in selected_savings_rows if row[2] is not None]
    savings_balance = balance_rows[-1][2] if balance_rows else None

    selected_investments = [
        row for row in investment_rows
        if period == "all" or (row[0].year, row[0].month) == selected_month
    ]
    investing_total = sum((row[2] for row in selected_investments), Decimal())
    snapshot_months = sorted(
        {(row[0].year, row[0].month) for row in investment_rows}
    )

    def portfolio_as_of(month: tuple[int, int]) -> Decimal:
        latest_by_account: dict[str, tuple[date, Decimal]] = {}
        for snapshot_date, account_name, _, value in investment_rows:
            if (snapshot_date.year, snapshot_date.month) > month:
                continue
            previous = latest_by_account.get(account_name)
            if previous is None or snapshot_date > previous[0]:
                latest_by_account[account_name] = (snapshot_date, value)
        return sum((value for _, value in latest_by_account.values()), Decimal())

    portfolio_month = (
        selected_month
        if period == "monthly"
        else (snapshot_months[-1] if snapshot_months else None)
    )
    portfolio_value = (
        portfolio_as_of(portfolio_month) if portfolio_month else Decimal()
    )
    previous_portfolio_value = None
    if portfolio_month:
        previous_month = _month_before(portfolio_month)
        if any(
            (row[0].year, row[0].month) <= previous_month
            for row in investment_rows
        ):
            previous_portfolio_value = portfolio_as_of(previous_month)

    visible_investment_months = [
        month for month in snapshot_months
        if period == "all" or month <= selected_month
    ][-12:]
    investment_month_labels = tuple(
        date(year, month, 1).strftime(
            "%b"
            if len({y for y, _ in visible_investment_months}) == 1
            else "%b %y"
        )
        for year, month in visible_investment_months
    )
    investment_value_series = tuple(
        portfolio_as_of(month) for month in visible_investment_months
    )

    recent = tuple(
        RecentTransaction(
            item.description,
            item.account_name,
            item.transaction_date,
            item.amount,
            item.category_color or "#718096",
        )
        for item in selected[:5]
    )

    return DashboardData(
        period_label=period_label,
        month_labels=month_labels,
        regular_income=summary.regular_income,
        other_income=summary.other_income,
        e_transfer_received=summary.e_transfer_received,
        e_transfer_sent=summary.e_transfer_sent,
        e_transfer_net=summary.e_transfer_net,
        e_transfer_income_adjustment=summary.e_transfer_income_adjustment,
        gross_expense_spending=summary.gross_expense_spending,
        reimbursements=summary.reimbursements,
        e_transfer_spending_adjustment=summary.e_transfer_spending_adjustment,
        total_income=summary.total_income,
        total_spending=summary.total_spending,
        account_spending=account_spending,
        investing_total=investing_total,
        savings_goal=savings_goal,
        savings_actual=savings_actual,
        savings_balance=savings_balance,
        budget_progress=budget_progress,
        portfolio_value=portfolio_value,
        previous_portfolio_value=previous_portfolio_value,
        investment_month_labels=investment_month_labels,
        investment_value_series=investment_value_series,
        previous_income=previous_income,
        previous_spending=previous_spending,
        income_series=make_series(income_accounts, INCOME_ACCOUNT_COLORS),
        spending_series=make_series(spending_accounts, SPENDING_ACCOUNT_COLORS),
        cash_flow_income=tuple(cash_flow_income),
        cash_flow_spending=tuple(cash_flow_spending),
        category_spending=category_spending,
        recent_transactions=recent,
    )
