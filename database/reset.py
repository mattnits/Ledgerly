from sqlalchemy import delete

from database.db import SessionLocal
from database.models import Import, Transaction


def reset_financial_data(session_factory=SessionLocal) -> None:
    """Clear transactions and their import history without deleting setup data."""
    with session_factory.begin() as session:
        session.execute(delete(Transaction))
        session.execute(delete(Import))
