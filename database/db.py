from pathlib import Path

from sqlalchemy import create_engine, inspect, select, text
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
    _migrate_category_rule_account_scope(db_engine)


def _migrate_category_rule_account_scope(db_engine) -> None:
    """Upgrade pre-account-scope SQLite databases without losing rules."""
    inspector = inspect(db_engine)
    if "category_rules" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("category_rules")}
    if "account_id" in columns:
        return
    if db_engine.dialect.name != "sqlite":
        raise RuntimeError(
            "The category_rules table needs an account_id migration for this database."
        )

    from database.models import CategoryRule

    with db_engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE category_rules RENAME TO category_rules_legacy")
        )
        CategoryRule.__table__.create(bind=connection)
        connection.execute(text("""
            INSERT INTO category_rules (
                id, user_id, account_id, description_key, description_example,
                match_type, transaction_type, category_id, priority, is_active
            )
            SELECT
                id, user_id, NULL, description_key, description_example,
                match_type, transaction_type, category_id, priority, is_active
            FROM category_rules_legacy
        """))
        connection.execute(text("DROP TABLE category_rules_legacy"))


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
