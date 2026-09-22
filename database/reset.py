from sqlalchemy import delete

from database.db import SessionLocal
from database.models import Account, Import, Transaction


def reset_financial_data(session_factory=SessionLocal) -> None:
    """Clear imported financial data for all users in one transaction."""
    with session_factory.begin() as session:
        session.execute(delete(Transaction))
        session.execute(delete(Import))
        session.execute(delete(Account))
