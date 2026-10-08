from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.services.category_rules import needs_review_expression, normalize_description
from app.models.models import Account, Category, Group, Transaction, User
from app.services.profiles import validate_owner, visible_account_scope
from app.utils.constants import (
    CATEGORY_FREE_TRANSACTION_TYPES,
    ClassificationSource,
    TransactionType,
)


_UNCHANGED = object()


@dataclass(frozen=True)
class TransactionQueryParams:
    """Immutable snapshot of the Transactions page's query controls."""

    user_id: str | None
    period_filter: str = "monthly"
    date_range_filter: str = "this_month"
    selected_month: tuple[int, int] = (date.today().year, date.today().month)
    account_filter: int | str = "all"
    category_filter: int | str | None = "all"
    transaction_type_filter: TransactionType | str = "all"
    needs_review_filter: bool = False
    search: str = ""
    sort_column: int = 0
    sort_descending: bool = True
    offset: int = 0
    limit: int = 200
    group_id: int | None = None


@dataclass(frozen=True)
class TransactionRowData:
    id: int
    transaction_date: date
    description: str
    amount: Decimal
    transaction_type: TransactionType | None
    imported_at: datetime
    category_id: int | None
    account_name: str
    institution: str
    is_deleted: bool


@dataclass(frozen=True)
class TransactionQueryResult:
    rows: tuple[TransactionRowData, ...]
    total_count: int
    filtered_count: int
    accounts: tuple[tuple[int, str, str], ...]
    categories: tuple[tuple[int, str, str], ...]
    available_months: frozenset[tuple[int, int]]


def fetch_transactions(
    params: TransactionQueryParams,
    session_factory: Callable[[], Session] = SessionLocal,
) -> TransactionQueryResult:
    """Fetch one page as detached plain data using a worker-owned session."""

    validate_owner(params.user_id, params.group_id)
    account_scope = visible_account_scope(params.user_id, params.group_id)
    with session_factory() as session:
        account_rows = session.execute(
            select(
                Account.id,
                Account.name,
                Account.institution,
                User.name,
                Group.name,
            )
            .outerjoin(User, Account.user_id == User.id)
            .outerjoin(Group, Account.group_id == Group.id)
            .where(account_scope)
            .order_by(Account.name, Account.id)
        ).all()
        accounts = tuple(
            (
                account_id,
                (
                    f"{name} — {user_name or group_name}"
                    if params.group_id is not None and (user_name or group_name)
                    else name
                ),
                institution,
            )
            for account_id, name, institution, user_name, group_name in account_rows
        )
        categories = tuple(session.execute(
            select(Category.id, Category.name, Category.color).order_by(Category.name)
        ).all())
        month_values = session.scalars(
            select(func.strftime("%Y-%m", Transaction.transaction_date))
            .join(Account, Transaction.account_id == Account.id)
            .where(account_scope)
            .distinct()
        ).all()
        available_months = frozenset(
            (int(month[:4]), int(month[5:7]))
            for month in month_values
            if month
        )

        base = (
            select(
                Transaction.id,
                Transaction.transaction_date,
                Transaction.description,
                Transaction.amount,
                Transaction.transaction_type,
                Transaction.imported_at,
                Transaction.category_id,
                Account.name,
                Account.institution,
                Transaction.is_deleted,
            )
            .join(Account, Transaction.account_id == Account.id)
            .outerjoin(Category, Transaction.category_id == Category.id)
            .where(account_scope)
            .where(Transaction.is_deleted.is_(params.category_filter == "deleted"))
        )
        if params.period_filter == "monthly":
            effective_month = (
                params.selected_month
                if params.selected_month in available_months
                else max(available_months, default=params.selected_month)
            )
            year, month = effective_month
            first_day = date(year, month, 1)
            next_month = date(year + (month == 12), month % 12 + 1, 1)
            base = base.where(
                Transaction.transaction_date >= first_day,
                Transaction.transaction_date < next_month,
            )
        elif params.date_range_filter == "this_year":
            year = date.today().year
            base = base.where(
                Transaction.transaction_date >= date(year, 1, 1),
                Transaction.transaction_date < date(year + 1, 1, 1),
            )

        total_count = session.scalar(
            select(func.count()).select_from(base.order_by(None).subquery())
        ) or 0

        if params.account_filter != "all":
            base = base.where(Account.id == params.account_filter)
        if params.needs_review_filter:
            base = base.where(needs_review_expression())
        if params.category_filter not in ("all", "deleted"):
            base = base.where(Transaction.category_id == params.category_filter)
        if params.transaction_type_filter != "all":
            base = base.where(
                Transaction.transaction_type == params.transaction_type_filter
            )

        search = params.search.strip()
        if search:
            pattern = f"%{search}%"
            description_tokens = normalize_description(search).split()
            search_terms: list[Any] = [
                Transaction.description.ilike(pattern),
                Account.name.ilike(pattern),
                Category.name.ilike(pattern),
                cast(Transaction.transaction_type, String).ilike(pattern),
                cast(Transaction.transaction_date, String).ilike(pattern),
                cast(Transaction.amount, String).ilike(pattern),
            ]
            if description_tokens:
                search_terms.append(and_(*(
                    Transaction.description.ilike(f"%{token}%")
                    for token in description_tokens
                )))
            base = base.where(or_(*search_terms))

        filtered_count = session.scalar(
            select(func.count()).select_from(base.order_by(None).subquery())
        ) or 0
        sort_expressions = (
            Transaction.transaction_date,
            Transaction.description,
            Transaction.amount,
            Account.name,
            Transaction.transaction_type,
            func.coalesce(Category.name, "Uncategorized"),
            Transaction.imported_at,
        )
        expression = sort_expressions[params.sort_column]
        ordering = expression.desc() if params.sort_descending else expression.asc()
        records = session.execute(
            base.order_by(ordering, Transaction.id.desc())
            .limit(params.limit)
            .offset(params.offset)
        ).all()

        rows = tuple(TransactionRowData(*record) for record in records)

    return TransactionQueryResult(
        rows=rows,
        total_count=total_count,
        filtered_count=filtered_count,
        accounts=accounts,
        categories=categories,
        available_months=available_months,
    )


def get_transaction_months(
    user_id: str | None,
    session_factory=SessionLocal,
    include_deleted: bool = False,
    *,
    group_id: int | None = None,
) -> set[tuple[int, int]]:
    if user_id is None and group_id is None:
        return set()

    validate_owner(user_id, group_id)

    with session_factory() as session:
        query = (
            select(func.strftime("%Y-%m", Transaction.transaction_date))
            .join(Account, Transaction.account_id == Account.id)
            .where(visible_account_scope(user_id, group_id))
            .distinct()
        )
        if not include_deleted:
            query = query.where(Transaction.is_deleted.is_(False))
        months = session.scalars(query).all()

    return {
        (int(month[:4]), int(month[5:7]))
        for month in months
        if month
    }


def set_transaction_deleted(
    transaction_id: int,
    user_id: str | None,
    deleted: bool,
    session_factory=SessionLocal,
    *,
    group_id: int | None = None,
) -> None:
    validate_owner(user_id, group_id)
    with session_factory.begin() as session:
        transaction = session.scalar(
            select(Transaction)
            .join(Account)
            .where(
                Transaction.id == transaction_id,
                visible_account_scope(user_id, group_id),
            )
        )
        if transaction is None:
            raise ValueError("Transaction is no longer available")

        transaction.is_deleted = deleted


def get_visible_transaction(
    session: Session,
    transaction_id: int,
    *,
    user_id: str | None = None,
    group_id: int | None = None,
) -> Transaction | None:
    validate_owner(user_id, group_id)
    return session.scalar(
        select(Transaction)
        .join(Account)
        .where(
            Transaction.id == transaction_id,
            visible_account_scope(user_id, group_id),
        )
    )


def bulk_classify_transactions(
    session: Session,
    user_id: str,
    transaction_ids: Iterable[int],
    *,
    transaction_type=_UNCHANGED,
    category_id=_UNCHANGED,
) -> int:
    """Apply explicit user classification changes to only the selected rows.

    The caller owns the transaction, allowing the whole edit to commit or roll
    back atomically. Passing no value for a field preserves that field.
    """
    selected_ids = set(transaction_ids)
    if not selected_ids:
        return 0
    if transaction_type is _UNCHANGED and category_id is _UNCHANGED:
        raise ValueError("Choose a transaction type or category to update")
    if category_id is not _UNCHANGED and category_id is not None:
        if session.get(Category, category_id) is None:
            raise ValueError("Category is no longer available")

    transactions = session.scalars(
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            Transaction.id.in_(selected_ids),
            Transaction.is_deleted.is_(False),
        )
    ).all()
    updated = 0
    for transaction in transactions:
        changed = False
        if transaction_type is not _UNCHANGED:
            transaction.transaction_type = transaction_type
            changed = True
            if transaction_type in CATEGORY_FREE_TRANSACTION_TYPES:
                transaction.category_id = None
        if (
            category_id is not _UNCHANGED
            and transaction.transaction_type not in CATEGORY_FREE_TRANSACTION_TYPES
        ):
            transaction.category_id = category_id
            changed = True
        if changed:
            transaction.classification_source = ClassificationSource.MANUAL.value
            updated += 1
    return updated
