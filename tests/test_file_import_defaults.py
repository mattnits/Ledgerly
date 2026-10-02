import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.components.file_row import FileRow, infer_parse_type_from_filename
from utils.constants import SUPPORTED_PARSE_TYPES


class FileImportDefaultTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_amex_word_anywhere_in_filename_selects_amex(self):
        for filename in ("april-amex.csv", "amex-july29-aug29.csv"):
            with self.subTest(filename=filename):
                self.assertEqual(
                    infer_parse_type_from_filename(filename),
                    SUPPORTED_PARSE_TYPES.AMEX,
                )
                self.assertEqual(
                    FileRow(filename).get_parse_type(),
                    SUPPORTED_PARSE_TYPES.AMEX.value,
                )

    def test_ambiguous_td_filename_defaults_to_debit(self):
        self.assertEqual(
            FileRow("july29-td-aug29.csv").get_parse_type(),
            SUPPORTED_PARSE_TYPES.TD_DEBIT.value,
        )

    def test_explicit_td_credit_hint_selects_credit(self):
        for filename in ("td-credit-july.csv", "td-visa-july.csv"):
            with self.subTest(filename=filename):
                self.assertEqual(
                    FileRow(filename).get_parse_type(),
                    SUPPORTED_PARSE_TYPES.TD_CREDIT.value,
                )

    def test_explicit_td_debit_hint_selects_debit(self):
        self.assertEqual(
            FileRow("may-td-debit-june.csv").get_parse_type(),
            SUPPORTED_PARSE_TYPES.TD_DEBIT.value,
        )

    def test_unknown_filename_keeps_existing_default(self):
        self.assertIsNone(infer_parse_type_from_filename("statement-april.csv"))
        self.assertEqual(
            FileRow("statement-april.csv").get_parse_type(),
            SUPPORTED_PARSE_TYPES.TD_DEBIT.value,
        )


if __name__ == "__main__":
    unittest.main()
