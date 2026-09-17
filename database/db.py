from pathlib import Path

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "finance.db"


class Base(DeclarativeBase):
    pass


engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=True,
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def init_db(db_engine=engine):
    # Import models so SQLAlchemy registers them with Base.metadata
    from database import models

    Base.metadata.create_all(bind=db_engine)
    ensure_account_balance_columns(db_engine)


def ensure_account_balance_columns(db_engine=engine) -> None:
    inspector = inspect(db_engine)
    if not inspector.has_table("accounts"):
        return

    existing = {column["name"] for column in inspector.get_columns("accounts")}
    with db_engine.begin() as connection:
        if "balance" not in existing:
            connection.exec_driver_sql(
                "ALTER TABLE accounts ADD COLUMN balance NUMERIC(12, 2)"
            )
        if "balance_as_of" not in existing:
            connection.exec_driver_sql(
                "ALTER TABLE accounts ADD COLUMN balance_as_of DATE"
            )


DEFAULT_CATEGORIES = (
    "Transport",
    "Food",
    "Groceries",
    "Shopping",
    "Entertainment",
    "Subscriptions",
    "Income",
    "Health & Fitness",
    "Bills & Utilities",
)


def ensure_categories(db_engine=engine) -> None:
    from database.models import Category

    Category.__table__.create(bind=db_engine, checkfirst=True)
    with Session(db_engine) as session, session.begin():
        existing = set(session.scalars(
            select(Category.name).where(Category.name.in_(DEFAULT_CATEGORIES))
        ))
        session.add_all(
            Category(name=name)
            for name in DEFAULT_CATEGORIES
            if name not in existing
        )


def user_exists() -> bool:
    from database.models import User

    with SessionLocal() as session:
        return session.scalar(
            select(User.id).limit(1)
        ) is not None


def get_users() -> list[dict[str, str]]:
    from database.models import User

    with SessionLocal() as session:
        users = session.scalars(
            select(User).order_by(User.created_at, User.id)
        ).all()

        return [
            {
                "id": user.id,
                "name": user.name,
                "color": user.color,
            }
            for user in users
        ]
