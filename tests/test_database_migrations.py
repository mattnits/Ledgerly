import unittest
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
    select,
)

from app.core.db import init_db


class DatabaseMigrationTest(unittest.TestCase):
    def test_legacy_long_term_goals_gain_finish_period_without_data_loss(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TABLE long_term_savings_goals (
                    id INTEGER PRIMARY KEY,
                    user_id VARCHAR(36),
                    group_id INTEGER,
                    name VARCHAR(120) NOT NULL,
                    target_amount NUMERIC(14, 2) NOT NULL,
                    current_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
                    target_date DATE,
                    notes VARCHAR(1000),
                    is_archived BOOLEAN NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO long_term_savings_goals (
                    id, user_id, name, target_amount, current_amount,
                    is_archived, created_at, updated_at
                ) VALUES (
                    1, 'owner', 'Emergency Fund', 10000, 2500,
                    0, '2026-01-01', '2026-01-01'
                )
            """)

        init_db(engine)
        columns = {
            column["name"]
            for column in inspect(engine).get_columns("long_term_savings_goals")
        }
        with engine.connect() as connection:
            row = connection.exec_driver_sql(
                "SELECT name, current_amount, starting_amount, "
                "finished_year, finished_month "
                "FROM long_term_savings_goals WHERE id = 1"
            ).one()

        self.assertIn("starting_amount", columns)
        self.assertIn("finished_year", columns)
        self.assertIn("finished_month", columns)
        self.assertIn("savings_goal_updates", inspect(engine).get_table_names())
        self.assertEqual(row[0], "Emergency Fund")
        self.assertEqual(row[1], 2500)
        self.assertEqual(row[2], 2500)
        self.assertIsNone(row[3])
        self.assertIsNone(row[4])
        engine.dispose()

    def test_legacy_category_budgets_become_recurring(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TABLE monthly_category_budgets (
                    id INTEGER PRIMARY KEY,
                    user_id VARCHAR(36),
                    group_id INTEGER,
                    category_id INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    month INTEGER NOT NULL,
                    target_amount NUMERIC(12, 2) NOT NULL
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO monthly_category_budgets (
                    id, user_id, category_id, year, month, target_amount
                ) VALUES (1, 'owner', 10, 2026, 7, 125)
            """)

        init_db(engine)

        columns = {
            column["name"]
            for column in inspect(engine).get_columns(
                "monthly_category_budgets"
            )
        }
        with engine.connect() as connection:
            applies_to_future = connection.exec_driver_sql(
                "SELECT applies_to_future FROM monthly_category_budgets "
                "WHERE id = 1"
            ).scalar_one()
        self.assertIn("applies_to_future", columns)
        self.assertEqual(applies_to_future, 1)
        engine.dispose()

    def test_manual_rrsp_table_is_added_without_losing_legacy_account_data(self):
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
            Column("is_work_related", Boolean, nullable=False, default=False),
            Column("auto_track_from_payroll", Boolean, nullable=False, default=False),
            Column("employee_contribution_percent", Integer),
            Column("employer_matching_enabled", Boolean, nullable=False, default=False),
            Column("employer_match_percent", Integer),
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
                created_at=datetime(2026, 1, 1),
                is_active=True,
                is_work_related=True,
                auto_track_from_payroll=True,
                employer_matching_enabled=True,
                employer_match_percent=50,
            ))

        init_db(engine)
        init_db(engine)

        migrated = Table("investment_accounts", MetaData(), autoload_with=engine)
        columns = {
            column["name"]
            for column in inspect(engine).get_columns("investment_accounts")
        }
        indexes = {
            index["name"]
            for index in inspect(engine).get_indexes("investment_accounts")
        }
        with engine.connect() as connection:
            row = connection.execute(select(migrated)).mappings().one()

        self.assertNotIn("payroll_tracking_start_date", columns)
        self.assertEqual(row["account_name"], "Existing RRSP")
        self.assertTrue(row["auto_track_from_payroll"])
        self.assertTrue(row["employer_matching_enabled"])
        self.assertEqual(row["employer_match_percent"], 50)
        self.assertIn("work_rrsp_contributions", inspect(engine).get_table_names())
        self.assertIn("ix_investment_accounts_user_id", indexes)
        self.assertIn("ix_investment_accounts_group_id", indexes)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
