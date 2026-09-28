from sqlalchemy import func, select

from database.db import SessionLocal
from database.models import Account, Transaction


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
