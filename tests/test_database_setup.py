import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect

from app.core.db import (
    DatabaseSetupError,
    SQLITE_APPLICATION_ID,
    _database_failure_message,
    prepare_database,
)


class DatabaseSetupTest(unittest.TestCase):
    def test_corrupt_replacement_is_rejected_without_being_modified(self):
        database = Path(__file__).parent / "fixtures" / "not_a_database.txt"
        original = database.read_bytes()
        db_engine = create_engine(f"sqlite:///{database.as_posix()}")

        with self.assertRaises(DatabaseSetupError) as raised:
            prepare_database(db_engine)

        db_engine.dispose()
        self.assertEqual(database.read_bytes(), original)
        self.assertIn("damaged", str(raised.exception))
        self.assertNotIn("sqlalchemy", str(raised.exception).casefold())

    def test_unrelated_sqlite_database_is_left_unchanged(self):
        db_engine = create_engine("sqlite://")
        with db_engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE unrelated_data (id INTEGER PRIMARY KEY)"
            )

        with self.assertRaises(DatabaseSetupError) as raised:
            prepare_database(db_engine)

        self.assertIn("not a Ledgerly database", str(raised.exception))
        self.assertEqual(inspect(db_engine).get_table_names(), ["unrelated_data"])
        db_engine.dispose()

    def test_empty_replacement_is_initialized_and_identified(self):
        db_engine = create_engine("sqlite://")

        prepare_database(db_engine)

        table_names = set(inspect(db_engine).get_table_names())
        with db_engine.connect() as connection:
            application_id = connection.exec_driver_sql(
                "PRAGMA application_id"
            ).scalar_one()
        self.assertTrue({"users", "accounts", "transactions"} <= table_names)
        self.assertEqual(application_id, SQLITE_APPLICATION_ID)
        db_engine.dispose()

    def test_malformed_backend_error_is_replaced_with_safe_guidance(self):
        message = _database_failure_message(
            RuntimeError("database disk image is malformed; secret backend detail")
        )

        self.assertIn("damaged", message)
        self.assertNotIn("secret backend detail", message)


if __name__ == "__main__":
    unittest.main()
