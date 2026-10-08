import os
import unittest
import csv
from io import StringIO
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.parsers.generic_parser import (
    AMEX_COLUMNS,
    AMEX_SHORT_COLUMNS,
    GenericParser,
    detect_amex_format,
    normalize_amex_fieldnames,
)
from app.core.db import Base
from app.models.models import Account, Transaction, User
from app.ui.widgets.file_row import FileRow
from app.utils.constants import SUPPORTED_PARSE_TYPES


class AmexFormatTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_full_amex_columns_are_supported(self):
        self.assertEqual(detect_amex_format(list(AMEX_COLUMNS)), "full")

    def test_detailed_amex_export_header_is_supported(self):
        header = (
            "Date,Date Processed,Description,Amount,Foreign Spend Amount,"
            "Commission,Exchange Rate,Additional Information,Merchant,Address,"
            "City / Province,Postal Code,Country,Reference"
        )
        fieldnames = next(csv.reader(StringIO(header)))
        self.assertEqual(detect_amex_format(fieldnames), "full")

    def test_detailed_amex_headers_are_normalized_and_extensible(self):
        headers = [f" {name} " for name in AMEX_COLUMNS]
        headers.append("Card Member")
        self.assertEqual(detect_amex_format(headers), "full")
        self.assertEqual(
            normalize_amex_fieldnames(["&#x41;ddress"]),
            ["Address"],
        )

    def test_short_amex_columns_are_supported(self):
        self.assertEqual(
            tuple(AMEX_SHORT_COLUMNS),
            ("Date", "Date Processed", "Description", "Amount"),
        )
        self.assertEqual(detect_amex_format(list(AMEX_SHORT_COLUMNS)), "short")

    def test_import_dropdown_has_one_amex_option(self):
        row = FileRow("statement.csv")
        choices = [
            row.parse_type.itemText(index)
            for index in range(row.parse_type.count())
        ]
        self.assertEqual(choices.count(SUPPORTED_PARSE_TYPES.AMEX.value), 1)
        self.assertNotIn("Amex Short", choices)

    def test_unknown_amex_columns_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "full or short"):
            detect_amex_format(["Date", "Description", "Amount"])

    def test_short_and_detailed_amex_files_both_create_transactions(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        sessions = sessionmaker(bind=engine)
        Base.metadata.create_all(engine)
        with sessions.begin() as session:
            user = User(id="owner", name="Owner", color="#123456")
            session.add(user)
            session.flush()
            session.add(Account(
                user_id=user.id,
                name="Amex",
                institution="American Express",
                account_type="credit",
            ))

        short_contents = (
            "Date,Date Processed,Description,Amount\n"
            "08/15/2026,08/16/2026,SHORT PURCHASE,12.34\n"
        ).encode()
        detailed_contents = (
            ",".join(AMEX_COLUMNS)
            + "\n"
            + "16/08/2026,17/08/2026,DETAILED PURCHASE,45.67,,,,,"
            "Merchant,Address,Toronto,A1A 1A1,Canada,REF123\n"
        ).encode()
        parser = GenericParser([
            ("short.csv", SUPPORTED_PARSE_TYPES.AMEX.value),
            ("detailed.csv", SUPPORTED_PARSE_TYPES.AMEX.value),
        ], "owner")
        with (
            patch("app.parsers.generic_parser.SessionLocal", sessions),
            patch.object(
                GenericParser,
                "_open_file_contents",
                side_effect=(short_contents, detailed_contents),
            ),
        ):
            parser.parse()

        self.assertEqual(parser.get_results(), [])
        with sessions() as session:
            self.assertEqual(
                session.scalar(select(func.count(Transaction.id))),
                2,
            )
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
