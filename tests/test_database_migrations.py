import unittest

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
    select,
)

from database.db import init_db


class DatabaseMigrationTest(unittest.TestCase):
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
