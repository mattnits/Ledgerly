from datetime import datetime
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
    _migrate_investment_account_number_last7(db_engine)
    _migrate_work_rrsp_fields(db_engine)
    _migrate_investment_snapshots(db_engine)
    _migrate_category_rule_account_scope(db_engine)


def _migrate_investment_account_number_last7(db_engine) -> None:
    """Add the seven-character account field while preserving old last-four values."""
    inspector = inspect(db_engine)
    if "investment_accounts" not in inspector.get_table_names():
        return
    columns = {
        column["name"]
        for column in inspector.get_columns("investment_accounts")
    }
    if "account_number_last7" in columns:
        return
    if "account_number_last4" not in columns:
        raise RuntimeError(
            "The investment_accounts table has an unsupported account-number schema."
        )
    if db_engine.dialect.name != "sqlite":
        raise RuntimeError(
            "The investment account-number migration currently supports SQLite only."
        )
    with db_engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE investment_accounts "
            "ADD COLUMN account_number_last7 VARCHAR(7)"
        ))
        connection.execute(text(
            "UPDATE investment_accounts "
            "SET account_number_last7 = account_number_last4 "
            "WHERE account_number_last4 IS NOT NULL"
        ))


def _migrate_work_rrsp_fields(db_engine) -> None:
    """Add opt-in work RRSP settings without changing existing accounts."""
    inspector = inspect(db_engine)
    if "investment_accounts" not in inspector.get_table_names():
        return
    if db_engine.dialect.name != "sqlite":
        raise RuntimeError(
            "The work RRSP migration currently supports SQLite only."
        )
    existing = {
        column["name"]
        for column in inspector.get_columns("investment_accounts")
    }
    additions = (
        ("is_work_related", "BOOLEAN NOT NULL DEFAULT 0"),
        ("auto_track_from_payroll", "BOOLEAN NOT NULL DEFAULT 0"),
        ("employee_contribution_percent", "NUMERIC(7, 4)"),
        ("employer_matching_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
        ("employer_match_percent", "NUMERIC(7, 4)"),
    )
    with db_engine.begin() as connection:
        for name, definition in additions:
            if name not in existing:
                connection.execute(text(
                    f"ALTER TABLE investment_accounts ADD COLUMN {name} {definition}"
                ))


def _migrate_investment_snapshots(db_engine) -> None:
    """Normalize legacy owner/account-name snapshots without dropping data."""
    inspector = inspect(db_engine)
    if "investment_snapshots" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("investment_snapshots")
    }
    current_columns = {
        "investment_account_id",
        "snapshot_datetime",
        "total_value",
        "contribution_amount",
        "created_at",
    }
    if current_columns.issubset(columns):
        return

    legacy_columns = {
        "id",
        "user_id",
        "group_id",
        "account_name",
        "snapshot_date",
        "monthly_contribution",
        "portfolio_value",
    }
    if not legacy_columns.issubset(columns):
        raise RuntimeError(
            "The investment_snapshots table has an unsupported schema. "
            "Back up the database and migrate it manually."
        )
    if db_engine.dialect.name != "sqlite":
        raise RuntimeError(
            "The investment snapshot migration currently supports SQLite only."
        )

    from database.models import InvestmentAccount, InvestmentSnapshot

    with db_engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE investment_snapshots RENAME TO investment_snapshots_legacy")
        )
        InvestmentAccount.__table__.create(bind=connection, checkfirst=True)
        InvestmentSnapshot.__table__.create(bind=connection)

        legacy_rows = connection.execute(text("""
            SELECT id, user_id, group_id, account_name, snapshot_date,
                   monthly_contribution, portfolio_value
            FROM investment_snapshots_legacy
            ORDER BY id
        """)).mappings().all()

        account_ids: dict[tuple[str | None, int | None, str], int] = {}
        for row in legacy_rows:
            key = (row["user_id"], row["group_id"], row["account_name"])
            if key not in account_ids:
                existing_id = connection.scalar(
                    select(InvestmentAccount.id).where(
                        InvestmentAccount.user_id == row["user_id"],
                        InvestmentAccount.group_id == row["group_id"],
                        InvestmentAccount.account_name == row["account_name"],
                    )
                )
                if existing_id is None:
                    result = connection.execute(
                        InvestmentAccount.__table__.insert().values(
                            user_id=row["user_id"],
                            group_id=row["group_id"],
                            institution="Imported legacy data",
                            account_name=row["account_name"],
                            account_number_last7=None,
                            account_type=None,
                            is_active=True,
                        )
                    )
                    existing_id = result.inserted_primary_key[0]
                account_ids[key] = existing_id

            connection.execute(
                InvestmentSnapshot.__table__.insert().values(
                    id=row["id"],
                    investment_account_id=account_ids[key],
                    snapshot_datetime=datetime.fromisoformat(str(row["snapshot_date"])),
                    total_value=row["portfolio_value"],
                    contribution_amount=row["monthly_contribution"],
                )
            )

        connection.execute(text("DROP TABLE investment_snapshots_legacy"))


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
