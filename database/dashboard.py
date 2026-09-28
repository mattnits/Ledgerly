from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from database.db import SessionLocal
from database.finance_services import (
    MonthlyFinancialSummary,
    combine_financial_summaries,
    summarize_transaction_rows,
)
from database.models import Account, Category, InvestmentSnapshot, Transaction
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
    investing_total: Decimal
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
    investment_rows: list[tuple[date, Decimal]] = []
    if user_id is not None:
        with session_factory() as session:
            rows = session.execute(
                select(
                    Transaction.transaction_date,
                    Transaction.description,
                    Transaction.amount,
                    Transaction.transaction_type,
                    Account.id,
                    Account.name,
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
                    InvestmentSnapshot.monthly_contribution,
                ).where(InvestmentSnapshot.user_id == user_id)
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
        investment_rows = [
            row for row in investment_rows
            if (row[0].year, row[0].month) == selected_month
        ]
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

    summary = _summarize(selected) if period == "monthly" else _summarize_by_month(selected)

    category_totals: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for item in selected:
        if item.category_name is None:
            continue
        key = (item.category_name, item.category_color or "#718096")
        if item.transaction_type == TransactionType.EXPENSE:
            category_totals[key] += abs(item.amount)
        elif item.transaction_type == TransactionType.REFUND_REIMBURSEMENT:
            category_totals[key] -= item.amount

    category_spending = tuple(
        CategorySpending(name, color, amount)
        for (name, color), amount in sorted(
            category_totals.items(),
            key=lambda value: (-value[1], value[0][0].casefold()),
        )
        if amount > 0
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
        investing_total=sum((row[1] for row in investment_rows), Decimal()),
        previous_income=previous_income,
        previous_spending=previous_spending,
        income_series=make_series(income_accounts, INCOME_ACCOUNT_COLORS),
        spending_series=make_series(spending_accounts, SPENDING_ACCOUNT_COLORS),
        cash_flow_income=tuple(cash_flow_income),
        cash_flow_spending=tuple(cash_flow_spending),
        category_spending=category_spending,
        recent_transactions=recent,
    )
