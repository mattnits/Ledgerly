from sqlalchemy import func, or_, select

from database.db import SessionLocal
from database.models import Account, Category, Transaction
from utils.constants import DASHBOARD_HIDDEN_CATEGORY_NAMES, DELETED_CATEGORY_NAME


def get_transaction_months(
    user_id: str | None,
    session_factory=SessionLocal,
    include_hidden_categories: bool = False,
) -> set[tuple[int, int]]:
    if user_id is None:
        return set()

    with session_factory() as session:
        query = (
            select(func.strftime("%Y-%m", Transaction.transaction_date))
            .join(Account, Transaction.account_id == Account.id)
            .outerjoin(Category, Transaction.category_id == Category.id)
            .where(Account.user_id == user_id)
            .distinct()
        )
        if not include_hidden_categories:
            query = query.where(or_(
                Category.name.is_(None),
                ~func.lower(Category.name).in_(DASHBOARD_HIDDEN_CATEGORY_NAMES),
            ))
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

        deleted_category_id = session.scalar(
            select(Category.id).where(Category.name == DELETED_CATEGORY_NAME)
        )
        if deleted_category_id is None:
            raise ValueError("Deleted category is not available")

        if deleted:
            if transaction.category_id == deleted_category_id:
                return
            transaction.previous_category_id = transaction.category_id
            transaction.category_id = deleted_category_id
        else:
            if transaction.category_id != deleted_category_id:
                return
            transaction.category_id = transaction.previous_category_id
            transaction.previous_category_id = None
