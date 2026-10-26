from datetime import datetime
import os
import sqlite3

from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.paths import app_data_dir
from app.utils.constants import DEFAULT_CATEGORY_COLORS


DB_PATH = app_data_dir() / "finance.db"
SQLITE_APPLICATION_ID = 0x4C444752  # "LDGR"
LEDGERLY_SIGNATURE_TABLES = frozenset({
    "accounts",
    "categories",
    "transactions",
    "users",
})
SQL_ECHO = os.environ.get("LEDGERLY_SQL_ECHO", "").strip().casefold() in {
    "1", "true", "yes", "on",
}


class Base(DeclarativeBase):
    pass


class DatabaseSetupError(RuntimeError):
    """A database startup problem that is safe to show directly to a user."""


engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=SQL_ECHO,
)


@event.listens_for(engine, "connect")
def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    """Apply settings that are safe before a database has been validated."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def prepare_database(db_engine=engine) -> None:
    """Validate and initialize a database without exposing backend errors.

    Validation deliberately happens before WAL mode or migrations can write to
    the file. This matters when ``finance.db`` has been replaced manually: an
    incomplete copy, stale sidecar state, or an unrelated SQLite database must
    not be treated as an empty Ledgerly database.
    """
    try:
        _validate_database(db_engine)
        _enable_wal_mode(db_engine)
        init_db(db_engine)
        ensure_categories(db_engine)
        _mark_as_ledgerly_database(db_engine)
    except DatabaseSetupError:
        raise
    except (
        SQLAlchemyError,
        sqlite3.Error,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        raise DatabaseSetupError(_database_failure_message(error)) from error


def reset_database_connections(db_engine=engine) -> None:
    """Release pooled handles before retrying a manually replaced database."""
    db_engine.dispose()


def _validate_database(db_engine) -> None:
    if db_engine.dialect.name != "sqlite":
        return

    with db_engine.connect() as connection:
        integrity_rows = connection.exec_driver_sql(
            "PRAGMA quick_check(1)"
        ).scalars().all()
        if integrity_rows != ["ok"]:
            raise DatabaseSetupError(
                "The replacement database did not pass SQLite's integrity check. "
                "It may be damaged or may have been copied while Ledgerly was open. "
                "No setup changes were made. Restore a complete backup, then retry."
            )

        application_id = int(connection.exec_driver_sql(
            "PRAGMA application_id"
        ).scalar_one())
        table_names = set(inspect(connection).get_table_names())

    if application_id not in (0, SQLITE_APPLICATION_ID):
        raise DatabaseSetupError(
            "The replacement file belongs to a different application. "
            "Choose a Ledgerly database or an empty database file, then retry."
        )
    if table_names and not LEDGERLY_SIGNATURE_TABLES.issubset(table_names):
        raise DatabaseSetupError(
            "The replacement file is a valid SQLite database, but it is not a "
            "Ledgerly database. The file was left unchanged. Choose the correct "
            "finance.db file, then retry."
        )


def _enable_wal_mode(db_engine) -> None:
    """Enable WAL only after the selected database is known to be safe."""
    if db_engine.dialect.name != "sqlite":
        return
    with db_engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")


def _mark_as_ledgerly_database(db_engine) -> None:
    """Give new and legacy databases an identity for future safe switching."""
    if db_engine.dialect.name != "sqlite":
        return
    with db_engine.connect() as connection:
        connection.exec_driver_sql(
            f"PRAGMA application_id={SQLITE_APPLICATION_ID}"
        )


def _database_failure_message(error: BaseException) -> str:
    """Translate SQLite/SQLAlchemy details into concise recovery guidance."""
    detail = str(error).casefold()
    if "malformed" in detail or "not a database" in detail:
        return (
            "The replacement database is damaged, incomplete, or not a SQLite "
            "database. Ledgerly did not continue setup. Restore a complete "
            "Ledgerly backup, then retry."
        )
    if "locked" in detail or "busy" in detail:
        return (
            "The database is in use by another process. Close every other "
            "Ledgerly window and any database tools, then retry."
        )
    if "readonly" in detail or "read-only" in detail or "permission" in detail:
        return (
            "Ledgerly cannot write to the selected database. Check that the file "
            "and its folder are writable, then retry."
        )
    return (
        "Ledgerly could not safely prepare the selected database. Confirm that "
        "it is a complete Ledgerly finance.db file and that no other program is "
        "using it, then retry."
    )


def init_db(db_engine=engine):
    # Import models so SQLAlchemy registers them with Base.metadata.
    from app.models import models

    Base.metadata.create_all(bind=db_engine)
    _migrate_user_permissions(db_engine)
    _migrate_category_ownership(db_engine)
    _migrate_group_color(db_engine)
    _migrate_investment_account_number_last7(db_engine)
    _migrate_work_rrsp_fields(db_engine)
    _migrate_investment_snapshots(db_engine)
    _migrate_category_rule_account_scope(db_engine)
    _migrate_transaction_deduplication(db_engine)
    _migrate_category_budget_recurrence(db_engine)
    _migrate_goal_unique_indexes(db_engine)
    _migrate_performance_indexes(db_engine)


def _sqlite_columns(db_engine, table_name: str) -> set[str]:
    """Return a SQLite table's columns, or an empty set when it is absent."""
    inspector = inspect(db_engine)
    if table_name not in inspector.get_table_names():
        return set()
    if db_engine.dialect.name != "sqlite":
        raise RuntimeError("Ledgerly database upgrades currently support SQLite only.")
    return {column["name"] for column in inspector.get_columns(table_name)}


def _migrate_user_permissions(db_engine) -> None:
    """Add the Admin flag and deterministically seed one legacy Admin."""
    columns = _sqlite_columns(db_engine, "users")
    if not columns:
        return
    with db_engine.begin() as connection:
        if "is_admin" not in columns:
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"
            ))
        admin_count = connection.scalar(text(
            "SELECT COUNT(*) FROM users WHERE is_admin = 1"
        ))
        user_count = connection.scalar(text("SELECT COUNT(*) FROM users"))
        if user_count and not admin_count:
            first_id = connection.scalar(text(
                "SELECT id FROM users ORDER BY created_at, id LIMIT 1"
            ))
            connection.execute(
                text("UPDATE users SET is_admin = 1 WHERE id = :user_id"),
                {"user_id": first_id},
            )


def _migrate_category_ownership(db_engine) -> None:
    """Classify defaults as system categories without guessing legacy ownership."""
    columns = _sqlite_columns(db_engine, "categories")
    if not columns:
        return
    with db_engine.begin() as connection:
        if "created_by_user_id" not in columns:
            connection.execute(text(
                "ALTER TABLE categories ADD COLUMN created_by_user_id VARCHAR(36)"
            ))
        if "is_system" not in columns:
            connection.execute(text(
                "ALTER TABLE categories "
                "ADD COLUMN is_system BOOLEAN NOT NULL DEFAULT 0"
            ))
        connection.execute(text(
            "UPDATE categories SET is_system = 1, created_by_user_id = NULL "
            "WHERE is_default = 1"
        ))


def _migrate_group_color(db_engine) -> None:
    """Add profile colours to existing groups without rebuilding any tables."""
    columns = _sqlite_columns(db_engine, "groups")
    if not columns or "color" in columns:
        return
    with db_engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE groups ADD COLUMN color VARCHAR(7) "
            "NOT NULL DEFAULT '#3397f5'"
        ))


def _migrate_investment_account_number_last7(db_engine) -> None:
    """Preserve old last-four account values in the current last-seven field."""
    columns = _sqlite_columns(db_engine, "investment_accounts")
    if not columns or "account_number_last7" in columns:
        return
    if "account_number_last4" not in columns:
        raise RuntimeError(
            "The investment_accounts table has an unsupported account-number schema."
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
    """Add current settings while retaining ignored legacy payroll columns."""
    columns = _sqlite_columns(db_engine, "investment_accounts")
    if not columns:
        return
    additions = (
        ("is_work_related", "BOOLEAN NOT NULL DEFAULT 0"),
        ("employer_matching_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
        ("employer_match_percent", "NUMERIC(7, 4)"),
    )
    with db_engine.begin() as connection:
        for name, definition in additions:
            if name not in columns:
                connection.execute(text(
                    f"ALTER TABLE investment_accounts ADD COLUMN {name} {definition}"
                ))


def _migrate_investment_snapshots(db_engine) -> None:
    """Normalize the legacy snapshot layout without dropping financial data."""
    columns = _sqlite_columns(db_engine, "investment_snapshots")
    if not columns:
        return
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

    from app.models.models import InvestmentAccount, InvestmentSnapshot

    with db_engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE investment_snapshots RENAME TO investment_snapshots_legacy"
        ))
        InvestmentAccount.__table__.create(bind=connection, checkfirst=True)
        InvestmentSnapshot.__table__.create(bind=connection)
        rows = connection.execute(text("""
            SELECT id, user_id, group_id, account_name, snapshot_date,
                   monthly_contribution, portfolio_value
            FROM investment_snapshots_legacy
            ORDER BY id
        """)).mappings().all()

        account_ids: dict[tuple[str | None, int | None, str], int] = {}
        for row in rows:
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
    """Upgrade rules created before per-account classification was introduced."""
    columns = _sqlite_columns(db_engine, "category_rules")
    if not columns or "account_id" in columns:
        return

    from app.models.models import CategoryRule

    with db_engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE category_rules RENAME TO category_rules_legacy"
        ))
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


def _migrate_transaction_deduplication(db_engine) -> None:
    """Add nullable transaction identity fields without rewriting existing rows."""
    columns = _sqlite_columns(db_engine, "transactions")
    if not columns:
        return
    with db_engine.begin() as connection:
        if "source_transaction_id" not in columns:
            connection.execute(text(
                "ALTER TABLE transactions "
                "ADD COLUMN source_transaction_id VARCHAR(255)"
            ))
        if "dedupe_fingerprint" not in columns:
            connection.execute(text(
                "ALTER TABLE transactions "
                "ADD COLUMN dedupe_fingerprint VARCHAR(64)"
            ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "ux_transactions_active_account_source_id "
            "ON transactions (account_id, source_transaction_id) "
            "WHERE source_transaction_id IS NOT NULL AND is_deleted = 0"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_transactions_dedupe_fingerprint "
            "ON transactions (dedupe_fingerprint)"
        ))


def _migrate_category_budget_recurrence(db_engine) -> None:
    """Preserve legacy carry-forward behavior while allowing month-only budgets."""
    columns = _sqlite_columns(db_engine, "monthly_category_budgets")
    if not columns or "applies_to_future" in columns:
        return
    with db_engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE monthly_category_budgets "
            "ADD COLUMN applies_to_future BOOLEAN NOT NULL DEFAULT 1"
        ))


def _migrate_goal_unique_indexes(db_engine) -> None:
    """Make nullable-owner uniqueness effective in SQLite."""
    table_names = set(inspect(db_engine).get_table_names())
    statements: list[str] = []
    if "savings_goals" in table_names:
        statements.extend((
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_user_savings_goal_month_nonnull "
            "ON savings_goals (user_id, year, month) WHERE user_id IS NOT NULL",
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_group_savings_goal_month_nonnull "
            "ON savings_goals (group_id, year, month) WHERE group_id IS NOT NULL",
        ))
    if "monthly_category_budgets" in table_names:
        statements.extend((
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_user_category_budget_month_nonnull "
            "ON monthly_category_budgets (user_id, category_id, year, month) "
            "WHERE user_id IS NOT NULL",
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_group_category_budget_month_nonnull "
            "ON monthly_category_budgets (group_id, category_id, year, month) "
            "WHERE group_id IS NOT NULL",
        ))
    with db_engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _migrate_performance_indexes(db_engine) -> None:
    """Add indexes used by profile-scoped date-range queries."""
    if db_engine.dialect.name != "sqlite":
        return
    tables = set(inspect(db_engine).get_table_names())
    statements = []
    if "accounts" in tables:
        statements.extend((
            "CREATE INDEX IF NOT EXISTS ix_accounts_user_id "
            "ON accounts (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_accounts_group_id "
            "ON accounts (group_id)",
        ))
    if "transactions" in tables:
        statements.append(
            "CREATE INDEX IF NOT EXISTS ix_transactions_account_deleted_date "
            "ON transactions (account_id, is_deleted, transaction_date)"
        )
    if "group_memberships" in tables:
        statements.append(
            "CREATE INDEX IF NOT EXISTS ix_group_memberships_group_id "
            "ON group_memberships (group_id)"
        )
    if "investment_accounts" in tables:
        statements.extend((
            "CREATE INDEX IF NOT EXISTS ix_investment_accounts_user_id "
            "ON investment_accounts (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_investment_accounts_group_id "
            "ON investment_accounts (group_id)",
        ))
    with db_engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def ensure_categories(db_engine=engine) -> None:
    from app.models.models import Category

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
                existing[name].is_system = True
                existing[name].created_by_user_id = None
            else:
                session.add(Category(
                    name=name, color=color, is_default=True, is_system=True,
                    created_by_user_id=None,
                ))


def user_exists() -> bool:
    from app.models.models import User

    with SessionLocal() as session:
        return session.scalar(
            select(User.id).limit(1)
        ) is not None


def get_users() -> list[dict[str, str]]:
    from app.models.models import User

    with SessionLocal() as session:
        users = session.scalars(
            select(User).order_by(User.created_at, User.id)
        ).all()

        return [
            {
                "id": user.id,
                "name": user.name,
                "color": user.color,
                "is_admin": user.is_admin,
            }
            for user in users
        ]


def get_profiles(
    session_factory=SessionLocal,
    current_user_id: str | None = None,
) -> list[dict]:
    """Return switcher-ready user and group profiles with typed keys."""
    from sqlalchemy import func
    from app.models.models import Group, GroupMembership, User

    with session_factory() as session:
        users = session.scalars(select(User).order_by(User.created_at, User.id)).all()
        group_query = (
            select(Group, func.count(GroupMembership.id))
            .outerjoin(GroupMembership)
            .group_by(Group.id)
            .order_by(Group.created_at, Group.id)
        )
        if current_user_id is not None:
            current = session.get(User, current_user_id)
            if current is not None and not current.is_admin:
                group_query = group_query.where(Group.id.in_(
                    select(GroupMembership.group_id).where(
                        GroupMembership.user_id == current_user_id
                    )
                ))
        groups = session.execute(group_query).all()
        return [
            {
                "key": f"user:{user.id}",
                "type": "user",
                "id": user.id,
                "name": user.name,
                "color": user.color,
                "subtitle": "Personal",
                "is_admin": user.is_admin,
            }
            for user in users
        ] + [
            {
                "key": f"group:{group.id}",
                "type": "group",
                "id": group.id,
                "name": group.name,
                "color": group.color,
                "member_count": member_count,
                "subtitle": f"Group • {member_count} member{'s' if member_count != 1 else ''}",
            }
            for group, member_count in groups
        ]
