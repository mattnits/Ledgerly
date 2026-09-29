from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.db import SessionLocal
from database.models import Account, Category, Transaction
from utils.constants import CATEGORY_FREE_TRANSACTION_TYPES, ClassificationSource


_UNCHANGED = object()


def get_transaction_months(
    user_id: str | None,
    session_factory=SessionLocal,
    include_deleted: bool = False,
) -> set[tuple[int, int]]:
    if user_id is None:
        return set()

    with session_factory() as session:
        query = (
            select(func.strftime("%Y-%m", Transaction.transaction_date))
            .join(Account, Transaction.account_id == Account.id)
            .where(Account.user_id == user_id)
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
    user_id: str,
    deleted: bool,
    session_factory=SessionLocal,
) -> None:
    with session_factory.begin() as session:
        transaction = session.get(Transaction, transaction_id)
        if transaction is None or transaction.account.user_id != user_id:
            raise ValueError("Transaction is no longer available")

        transaction.is_deleted = deleted


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
