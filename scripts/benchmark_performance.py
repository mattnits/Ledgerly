"""Repeatable local performance benchmark using an in-memory synthetic database.

This script never opens Ledgerly's configured database. It is intentionally small
enough for routine before/after checks while large enough to expose full-history
query and Python aggregation costs.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from statistics import median
from time import perf_counter

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models.models import (
    Account,
    Category,
    InvestmentAccount,
    InvestmentSnapshot,
    MonthlyCategoryBudget,
    SavingsGoal,
    Transaction,
    User,
)
from app.services.dashboard import get_dashboard_data
from app.services.goals import (
    get_category_budgets,
    get_monthly_savings_breakdown,
    get_savings_goals,
)
from app.services.investments import (
    get_account_summaries,
    get_investment_months,
    get_monthly_contribution_comparison,
    get_portfolio_history,
    get_recent_snapshots,
)
from app.services.transactions import TransactionQueryParams, fetch_transactions
from app.services.summary_cache import clear_summary_cache
from app.utils.constants import ClassificationSource, TransactionType


TARGET_MONTH = (2026, 8)
TRANSACTIONS_PER_MONTH = 800
MONTH_COUNT = 36


def _previous_month(year: int, month: int) -> tuple[int, int]:
    return year - (month == 1), (month - 2) % 12 + 1


def _month_sequence(end_year: int, end_month: int, count: int):
    year, month = end_year, end_month
    result = []
    for _ in range(count):
        result.append((year, month))
        year, month = _previous_month(year, month)
    return tuple(reversed(result))


def _build_database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions.begin() as session:
        user = User(id="benchmark-user", name="Benchmark", color="#3397f5")
        categories = (
            Category(name="Salary", color="#10b981"),
            Category(name="Other Income", color="#22c55e"),
            Category(name="Food", color="#f97316"),
            Category(name="Transport", color="#3b82f6"),
        )
        session.add_all((user, *categories))
        session.flush()
        accounts = tuple(
            Account(
                user_id=user.id,
                name=f"Account {index + 1}",
                institution="Benchmark Bank",
                account_type="debit" if index < 2 else "credit",
            )
            for index in range(4)
        )
        session.add_all(accounts)
        session.flush()
        investment = InvestmentAccount(
            user_id=user.id,
            institution="Benchmark Investments",
            account_name="Portfolio",
        )
        session.add(investment)
        session.flush()

        category_ids = {category.name: category.id for category in categories}
        account_ids = tuple(account.id for account in accounts)
        investment_id = investment.id

    transaction_rows = []
    snapshot_rows = []
    transaction_id = 1
    snapshot_id = 1
    for year, month in _month_sequence(*TARGET_MONTH, MONTH_COUNT):
        for index in range(TRANSACTIONS_PER_MONTH):
            pattern = index % 10
            if pattern == 0:
                transaction_type = TransactionType.INCOME
                category_id = category_ids["Salary"]
                amount = Decimal("1200.00")
            elif pattern == 1:
                transaction_type = TransactionType.INCOME
                category_id = category_ids["Other Income"]
                amount = Decimal("75.00")
            elif pattern == 2:
                transaction_type = TransactionType.E_TRANSFER
                category_id = None
                amount = Decimal("40.00")
            elif pattern == 3:
                transaction_type = TransactionType.E_TRANSFER
                category_id = None
                amount = Decimal("-25.00")
            elif pattern == 4:
                transaction_type = TransactionType.REFUND_REIMBURSEMENT
                category_id = category_ids["Food"]
                amount = Decimal("8.00")
            else:
                transaction_type = TransactionType.EXPENSE
                category_id = (
                    category_ids["Food"]
                    if index % 2
                    else category_ids["Transport"]
                )
                amount = Decimal("-12.50")
            transaction_rows.append({
                "id": transaction_id,
                "account_id": account_ids[index % len(account_ids)],
                "category_id": category_id,
                "transaction_type": transaction_type,
                "classification_source": ClassificationSource.DEFAULT.value,
                "is_deleted": False,
                "transaction_date": date(year, month, index % 28 + 1),
                "description": f"Synthetic transaction {transaction_id}",
                "amount": amount,
                "imported_at": datetime(year, month, index % 28 + 1),
            })
            transaction_id += 1
        snapshot_rows.append({
            "id": snapshot_id,
            "investment_account_id": investment_id,
            "snapshot_datetime": datetime(year, month, 28),
            "total_value": Decimal(snapshot_id * 1000),
            "contribution_amount": Decimal("250.00"),
            "created_at": datetime(year, month, 28),
        })
        snapshot_id += 1

    with engine.begin() as connection:
        connection.execute(Transaction.__table__.insert(), transaction_rows)
        connection.execute(InvestmentSnapshot.__table__.insert(), snapshot_rows)
        connection.execute(MonthlyCategoryBudget.__table__.insert(), {
            "user_id": "benchmark-user",
            "group_id": None,
            "category_id": category_ids["Food"],
            "year": 2025,
            "month": 1,
            "target_amount": Decimal("900.00"),
        })
        connection.execute(SavingsGoal.__table__.insert(), {
            "user_id": "benchmark-user",
            "group_id": None,
            "year": 2025,
            "month": 1,
            "target_amount": Decimal("1000.00"),
        })
    return engine, sessions


def _investment_reload(sessions) -> None:
    year, month = TARGET_MONTH
    accounts = get_account_summaries(
        user_id="benchmark-user", session_factory=sessions
    )
    get_investment_months(user_id="benchmark-user", session_factory=sessions)
    get_monthly_contribution_comparison(
        year, month, user_id="benchmark-user", session_factory=sessions
    )
    get_portfolio_history(
        user_id="benchmark-user",
        end_date=date(year, month, 28),
        session_factory=sessions,
    )
    get_recent_snapshots(
        user_id="benchmark-user",
        end_date=date(year, month, 28),
        session_factory=sessions,
    )
    if not accounts:
        raise AssertionError("benchmark investment account was not loaded")


def _goals_reload(sessions) -> None:
    year, month = TARGET_MONTH
    get_monthly_savings_breakdown(
        year, month, user_id="benchmark-user", session_factory=sessions
    )
    get_category_budgets(
        year, month, user_id="benchmark-user", session_factory=sessions
    )
    get_savings_goals(user_id="benchmark-user", session_factory=sessions)


def _measure(
    engine,
    operation: Callable[[], object],
    repeats: int = 5,
    *,
    before_each: Callable[[], None] | None = None,
):
    timings = []
    query_counts = []
    for _ in range(repeats):
        if before_each is not None:
            before_each()
        count = 0

        def before_cursor_execute(*_args):
            nonlocal count
            count += 1

        event.listen(engine, "before_cursor_execute", before_cursor_execute)
        started = perf_counter()
        operation()
        timings.append((perf_counter() - started) * 1000)
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
        query_counts.append(count)
    return median(timings), int(median(query_counts))


def main() -> None:
    engine, sessions = _build_database()
    params = TransactionQueryParams(
        user_id="benchmark-user",
        selected_month=TARGET_MONTH,
        date_range_filter="selected_month",
    )
    operations = (
        (
            "Dashboard month",
            lambda: get_dashboard_data(
                "benchmark-user", "monthly", TARGET_MONTH, sessions
            ),
        ),
        ("Transactions month", lambda: fetch_transactions(params, sessions)),
        ("Goals month", lambda: _goals_reload(sessions)),
        ("Investments month", lambda: _investment_reload(sessions)),
    )
    print(
        f"Synthetic database: {MONTH_COUNT * TRANSACTIONS_PER_MONTH:,} "
        "transactions, 36 monthly investment snapshots"
    )
    for label, operation in operations:
        clear_summary_cache()
        operation()  # Warm caches and imports before collecting samples.
        milliseconds, queries = _measure(
            engine,
            operation,
            before_each=(clear_summary_cache if label == "Dashboard month" else None),
        )
        print(f"{label}: {milliseconds:.2f} ms median, {queries} SQL statements")
    get_dashboard_data("benchmark-user", "monthly", TARGET_MONTH, sessions)
    cached_ms, cached_queries = _measure(
        engine,
        lambda: get_dashboard_data(
            "benchmark-user", "monthly", TARGET_MONTH, sessions
        ),
    )
    print(
        f"Dashboard cached month: {cached_ms:.2f} ms median, "
        f"{cached_queries} SQL statements"
    )
    engine.dispose()


if __name__ == "__main__":
    main()
