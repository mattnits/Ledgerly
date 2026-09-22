from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select

from database.db import SessionLocal
from database.models import Account, Category, Transaction
from utils.constants import DASHBOARD_HIDDEN_CATEGORY_NAMES


INCOME_ACCOUNT_COLORS = (
    "#63dba0",
    "#35bdd0",
    "#9cc85b",
    "#5f7cff",
    "#4fd1a5",
    "#8ccf78",
)
SPENDING_ACCOUNT_COLORS = (
    "#f16f88",
    "#e05b68",
    "#f2a84b",
    "#cf78dc",
    "#ef7aa8",
    "#bd6a80",
    "#a66bff",
    "#e8895c",
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
    income_total: Decimal
    spending_total: Decimal
    investing_total: Decimal
    previous_income: Decimal | None
    previous_spending: Decimal | None
    income_series: tuple[ChartSeries, ...]
    spending_series: tuple[ChartSeries, ...]
    cash_flow_income: tuple[Decimal, ...]
    cash_flow_spending: tuple[Decimal, ...]
    category_spending: tuple[CategorySpending, ...]
    recent_transactions: tuple[RecentTransaction, ...]


@dataclass(frozen=True)
class _TransactionData:
    transaction_date: date
    description: str
    amount: Decimal
    account_id: int
    account_name: str
    category_name: str | None
    category_color: str | None


def _month_before(month: tuple[int, int]) -> tuple[int, int]:
    year, month_number = month
    return (
        year - (month_number == 1),
        (month_number - 2) % 12 + 1,
    )


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


def _is_income(item: _TransactionData) -> bool:
    category = (item.category_name or "").strip().casefold()
    return category == "income" or (category == "e-transfer" and item.amount > 0)


def _percentage_base(
    transactions: list[_TransactionData],
    month: tuple[int, int],
) -> tuple[Decimal, Decimal]:
    income = sum(
        (
            item.amount
            for item in transactions
            if (item.transaction_date.year, item.transaction_date.month) == month
            and _is_income(item)
        ),
        Decimal(),
    )
    spending = sum(
        (
            -item.amount
            for item in transactions
            if (item.transaction_date.year, item.transaction_date.month) == month
            and not _is_income(item)
        ),
        Decimal(),
    )
    return income, spending


def get_dashboard_data(
    user_id: str | None,
    period: str,
    selected_month: tuple[int, int],
    session_factory=SessionLocal,
) -> DashboardData:
    if period not in ("monthly", "all"):
        raise ValueError(f"Unsupported dashboard period: {period}")

    rows = []
    if user_id is not None:
        with session_factory() as session:
            rows = session.execute(
                select(
                    Transaction.transaction_date,
                    Transaction.description,
                    Transaction.amount,
                    Account.id,
                    Account.name,
                    Category.name,
                    Category.color,
                )
                .join(Account, Transaction.account_id == Account.id)
                .outerjoin(Category, Transaction.category_id == Category.id)
                .where(Account.user_id == user_id)
                .where(or_(
                    Category.name.is_(None),
                    ~func.lower(Category.name).in_(DASHBOARD_HIDDEN_CATEGORY_NAMES),
                ))
                .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
            ).all()

    transactions = [_TransactionData(*row) for row in rows]
    today = date.today()

    if period == "monthly":
        timeline = _month_sequence((selected_month[0], 1), selected_month)
        selected = [
            item
            for item in transactions
            if (item.transaction_date.year, item.transaction_date.month) == selected_month
        ]
        previous_month = _month_before(selected_month)
        previous_income, previous_spending = _percentage_base(
            transactions, previous_month
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

    for item in transactions:
        month = (item.transaction_date.year, item.transaction_date.month)
        index = timeline_index.get(month)
        if index is None:
            continue

        if _is_income(item):
            name, values = income_accounts.setdefault(
                item.account_id,
                (item.account_name, [Decimal() for _ in timeline]),
            )
            values[index] += item.amount
            cash_flow_income[index] += item.amount

        else:
            name, values = spending_accounts.setdefault(
                item.account_id,
                (item.account_name, [Decimal() for _ in timeline]),
            )
            amount = -item.amount
            values[index] += amount
            cash_flow_spending[index] += amount

    def make_series(
        grouped: dict[int, tuple[str, list[Decimal]]],
        colors: tuple[str, ...],
    ) -> tuple[ChartSeries, ...]:
        return tuple(
            ChartSeries(name, colors[index % len(colors)], tuple(values))
            for index, (_, (name, values)) in enumerate(
                sorted(grouped.items(), key=lambda item: (item[1][0].casefold(), item[0]))
            )
            if any(values)
        )

    income_total = sum(
        (
            item.amount
            for item in selected
            if _is_income(item)
        ),
        Decimal(),
    )
    spending_total = sum(
        (
            -item.amount
            for item in selected
            if not _is_income(item)
        ),
        Decimal(),
    )
    investing_total = sum(
        (
            abs(item.amount)
            for item in selected
            if item.amount < 0
            and item.category_name
            and item.category_name.strip().casefold() == "investing"
        ),
        Decimal(),
    )

    category_totals: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for item in selected:
        if _is_income(item):
            continue
        category_totals[
            (
                item.category_name or "Uncategorized",
                item.category_color or "#718096",
            )
        ] -= item.amount

    category_spending = tuple(
        CategorySpending(name, color, amount)
        for (name, color), amount in sorted(
            category_totals.items(),
            key=lambda item: (-item[1], item[0][0].casefold()),
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
        income_total=income_total,
        spending_total=spending_total,
        investing_total=investing_total,
        previous_income=previous_income,
        previous_spending=previous_spending,
        income_series=make_series(income_accounts, INCOME_ACCOUNT_COLORS),
        spending_series=make_series(spending_accounts, SPENDING_ACCOUNT_COLORS),
        cash_flow_income=tuple(cash_flow_income),
        cash_flow_spending=tuple(cash_flow_spending),
        category_spending=category_spending,
        recent_transactions=recent,
    )
