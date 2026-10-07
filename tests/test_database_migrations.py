import unittest
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Numeric,
    create_engine,
    inspect,
    select,
)

from database.db import init_db


class DatabaseMigrationTest(unittest.TestCase):
    def test_permissions_and_category_ownership_migrate_without_guessing(self):
        engine = create_engine("sqlite://")
        metadata = MetaData()
        users = Table(
            "users", metadata,
            Column("id", String(36), primary_key=True),
            Column("name", String(100), nullable=False),
            Column("profile_code_hash", String(255)),
            Column("color", String(7), nullable=False),
            Column("created_at", DateTime, nullable=False),
        )
        categories = Table(
            "categories", metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String(100), nullable=False, unique=True),
            Column("color", String(7), nullable=False),
            Column("is_default", Boolean, nullable=False),
        )
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(users.insert(), (
                {"id": "later", "name": "Later", "color": "#111111",
                 "created_at": datetime(2026, 2, 1)},
                {"id": "first", "name": "First", "color": "#222222",
                 "created_at": datetime(2026, 1, 1)},
            ))
            connection.execute(categories.insert(), (
                {"id": 1, "name": "Default", "color": "#111111",
                 "is_default": True},
                {"id": 2, "name": "Legacy Custom", "color": "#222222",
                 "is_default": False},
            ))

        init_db(engine)

        migrated_users = Table("users", MetaData(), autoload_with=engine)
        migrated_categories = Table("categories", MetaData(), autoload_with=engine)
        with engine.connect() as connection:
            user_rows = connection.execute(
                select(migrated_users).order_by(migrated_users.c.created_at)
            ).mappings().all()
            category_rows = connection.execute(
                select(migrated_categories).order_by(migrated_categories.c.id)
            ).mappings().all()
        self.assertTrue(user_rows[0]["is_admin"])
        self.assertFalse(user_rows[1]["is_admin"])
        self.assertTrue(category_rows[0]["is_system"])
        self.assertIsNone(category_rows[0]["created_by_user_id"])
        self.assertFalse(category_rows[1]["is_system"])
        self.assertIsNone(category_rows[1]["created_by_user_id"])
        engine.dispose()

    def test_work_rrsp_columns_are_added_with_safe_existing_account_defaults(self):
        engine = create_engine("sqlite://")
        metadata = MetaData()
        accounts = Table(
            "investment_accounts",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("user_id", String(36)),
            Column("group_id", Integer),
            Column("institution", String(100), nullable=False),
            Column("account_name", String(100), nullable=False),
            Column("account_number_last7", String(7)),
            Column("account_type", String(50)),
            Column("created_at", DateTime, nullable=False),
            Column("is_active", Boolean, nullable=False),
        )
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(accounts.insert().values(
                id=1,
                user_id="legacy-user",
                institution="Legacy institution",
                account_name="Existing RRSP",
                account_type="RRSP",
                created_at=datetime(2026, 1, 1),
                is_active=True,
            ))

        init_db(engine)

        migrated = Table("investment_accounts", MetaData(), autoload_with=engine)
        columns = {column["name"] for column in inspect(engine).get_columns(
            "investment_accounts"
        )}
        with engine.connect() as connection:
            row = connection.execute(select(migrated)).mappings().one()
        self.assertTrue({
            "is_work_related",
            "auto_track_from_payroll",
            "employee_contribution_percent",
            "employer_matching_enabled",
            "employer_match_percent",
        }.issubset(columns))
        self.assertFalse(row["is_work_related"])
        self.assertFalse(row["auto_track_from_payroll"])
        self.assertIsNone(row["employee_contribution_percent"])
        self.assertFalse(row["employer_matching_enabled"])
        self.assertIsNone(row["employer_match_percent"])
        engine.dispose()

    def test_last_four_account_values_are_preserved_in_last_seven_field(self):
        engine = create_engine("sqlite://")
        metadata = MetaData()
        accounts = Table(
            "investment_accounts",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("user_id", String(36)),
            Column("group_id", Integer),
            Column("institution", String(100), nullable=False),
            Column("account_name", String(100), nullable=False),
            Column("account_number_last4", String(4)),
            Column("account_type", String(50)),
            Column("created_at", DateTime, nullable=False),
            Column("is_active", Boolean, nullable=False),
        )
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(accounts.insert().values(
                id=1,
                user_id="legacy-user",
                institution="Legacy institution",
                account_name="TFSA",
                account_number_last4="4821",
                created_at=datetime(2026, 1, 1),
                is_active=True,
            ))

        init_db(engine)

        migrated = Table("investment_accounts", MetaData(), autoload_with=engine)
        with engine.connect() as connection:
            row = connection.execute(select(migrated)).mappings().one()
        self.assertEqual(row["account_number_last7"], "4821")
        engine.dispose()

    def test_legacy_investment_snapshots_are_normalized_without_data_loss(self):
        engine = create_engine("sqlite://")
        metadata = MetaData()
        legacy = Table(
            "investment_snapshots",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("user_id", String(36)),
            Column("group_id", Integer),
            Column("account_name", String(100), nullable=False),
            Column("snapshot_date", Date, nullable=False),
            Column("monthly_contribution", Numeric(12, 2), nullable=False),
            Column("portfolio_value", Numeric(14, 2), nullable=False),
        )
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(legacy.insert(), (
                {
                    "id": 4,
                    "user_id": "legacy-user",
                    "group_id": None,
                    "account_name": "TFSA",
                    "snapshot_date": date(2026, 8, 31),
                    "monthly_contribution": Decimal("100.00"),
                    "portfolio_value": Decimal("1000.00"),
                },
                {
                    "id": 5,
                    "user_id": "legacy-user",
                    "group_id": None,
                    "account_name": "TFSA",
                    "snapshot_date": date(2026, 9, 30),
                    "monthly_contribution": Decimal("200.00"),
                    "portfolio_value": Decimal("1250.00"),
                },
            ))

        init_db(engine)

        accounts = Table("investment_accounts", MetaData(), autoload_with=engine)
        snapshots = Table("investment_snapshots", MetaData(), autoload_with=engine)
        with engine.connect() as connection:
            account_rows = connection.execute(select(accounts)).mappings().all()
            snapshot_rows = connection.execute(
                select(snapshots).order_by(snapshots.c.id)
            ).mappings().all()
        self.assertEqual(len(account_rows), 1)
        self.assertEqual(account_rows[0]["account_name"], "TFSA")
        self.assertEqual([row["id"] for row in snapshot_rows], [4, 5])
        self.assertEqual(snapshot_rows[-1]["total_value"], Decimal("1250.00"))
        self.assertEqual(
            snapshot_rows[-1]["investment_account_id"], account_rows[0]["id"]
        )
        engine.dispose()

    def test_existing_rules_migrate_to_all_accounts(self):
        engine = create_engine("sqlite://")
        metadata = MetaData()
        legacy_rules = Table(
            "category_rules",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("user_id", String(36), nullable=False),
            Column("description_key", String(512), nullable=False),
            Column("description_example", String(255), nullable=False),
            Column("match_type", String(16), nullable=False),
            Column("transaction_type", String(32)),
            Column("category_id", Integer),
            Column("priority", Integer, nullable=False),
            Column("is_active", Boolean, nullable=False),
        )
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(legacy_rules.insert().values(
                id=1,
                user_id="legacy-user",
                description_key="coffee",
                description_example="COFFEE",
                match_type="CONTAINS",
                transaction_type="EXPENSE",
                category_id=None,
                priority=0,
                is_active=True,
            ))

        init_db(engine)

        columns = {
            column["name"]
            for column in inspect(engine).get_columns("category_rules")
        }
        migrated = Table("category_rules", MetaData(), autoload_with=engine)
        with engine.connect() as connection:
            row = connection.execute(select(migrated)).mappings().one()
        self.assertIn("account_id", columns)
        self.assertIsNone(row["account_id"])
        self.assertEqual(row["description_key"], "coffee")
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
