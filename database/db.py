from pathlib import Path

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from utils.constants import DEFAULT_CATEGORY_COLORS


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
    ensure_category_columns(db_engine)
    ensure_import_hash_column(db_engine)
    ensure_transaction_restore_column(db_engine)


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


def ensure_category_columns(db_engine=engine) -> None:
    inspector = inspect(db_engine)
    if not inspector.has_table("categories"):
        return

    existing = {column["name"] for column in inspector.get_columns("categories")}
    with db_engine.begin() as connection:
        if "color" not in existing:
            connection.exec_driver_sql(
                "ALTER TABLE categories ADD COLUMN color VARCHAR(7) NOT NULL DEFAULT '#64748b'"
            )
        if "is_default" not in existing:
            connection.exec_driver_sql(
                "ALTER TABLE categories ADD COLUMN is_default BOOLEAN NOT NULL DEFAULT 0"
            )


def ensure_import_hash_column(db_engine=engine) -> None:
    inspector = inspect(db_engine)
    if not inspector.has_table("imports"):
        return
    existing = {column["name"] for column in inspector.get_columns("imports")}
    if "content_hash" not in existing:
        with db_engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE imports ADD COLUMN content_hash VARCHAR(64)"
            )


def ensure_transaction_restore_column(db_engine=engine) -> None:
    inspector = inspect(db_engine)
    if not inspector.has_table("transactions"):
        return
    existing = {column["name"] for column in inspector.get_columns("transactions")}
    if "previous_category_id" not in existing:
        with db_engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE transactions ADD COLUMN previous_category_id INTEGER "
                "REFERENCES categories(id)"
            )


def ensure_categories(db_engine=engine) -> None:
    from database.models import Category

    Category.__table__.create(bind=db_engine, checkfirst=True)
    with Session(db_engine) as session, session.begin():
        existing = {
            category.name: category
            for category in session.scalars(
                select(Category).where(Category.name.in_(DEFAULT_CATEGORY_COLORS))
            )
        }
        for name, color in DEFAULT_CATEGORY_COLORS.items():
            if name in existing:
                existing[name].color = color
                existing[name].is_default = True
            else:
                session.add(Category(name=name, color=color, is_default=True))


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
