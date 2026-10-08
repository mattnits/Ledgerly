import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from database.db import Base
from database.deduplication import (
    DuplicateDecision,
    ExistingDuplicateState,
    IncomingTransaction,
    build_transaction_fingerprint,
    classify_import_rows,
    find_existing_duplicate_candidates,
    load_existing_duplicate_state,
)
from database.models import Account, Import, Transaction, User
from parsers.generic_parser import AMEX_COLUMNS, GenericParser
from PySide6.QtWidgets import QApplication, QLabel
from ui.components.duplicate_review_dialog import DuplicateReviewDialog
from ui.theme import APP_STYLESHEET
from utils.constants import SUPPORTED_PARSE_TYPES, TransactionType


class DeduplicationServiceTest(unittest.TestCase):
    def row(
        self,
        *,
        account_id=1,
        batch_file_id="file-1",
        file_hash="hash-1",
        source_id=None,
        description="Tim-Hortons #1234",
        amount=Decimal("-7.50"),
    ):
        return IncomingTransaction(
            account_id=account_id,
            account_name=f"Account {account_id}",
            transaction_date=date(2026, 9, 10),
            description=description,
            amount=amount,
            source_file=f"{batch_file_id}.csv",
            source_file_hash=file_hash,
            batch_file_id=batch_file_id,
            source_transaction_id=source_id,
        )

    def empty_state(self):
        return ExistingDuplicateState((), {}, {}, {})

    def state_with(self, *rows):
        by_source = {}
        by_fingerprint = {}
        by_file = {}
        for row in rows:
            if row.source_transaction_id:
                by_source.setdefault(
                    (row.account_id, row.source_transaction_id), []
                ).append(row)
            by_fingerprint.setdefault(row.fingerprint, []).append(row)
            if row.source_file_hash:
                by_file.setdefault(
                    (row.account_id, row.source_file_hash, row.fingerprint), []
                ).append(row)
        return ExistingDuplicateState(
            tuple(rows),
            {key: tuple(value) for key, value in by_source.items()},
            {key: tuple(value) for key, value in by_fingerprint.items()},
            {key: tuple(value) for key, value in by_file.items()},
        )

    def existing(self, incoming, *, row_id=1, source_id=None, file_hash=None):
        from database.deduplication import ExistingTransactionSnapshot
        from datetime import datetime

        return ExistingTransactionSnapshot(
            id=row_id,
            account_id=incoming.account_id,
            account_name=incoming.account_name,
            transaction_date=incoming.transaction_date,
            description=incoming.description,
            amount=incoming.amount,
            imported_at=datetime(2026, 9, 11),
            source_file="old.csv" if file_hash else None,
            source_file_hash=file_hash,
            source_transaction_id=source_id,
            fingerprint=incoming.fingerprint,
            is_manual=file_hash is None,
        )

    def test_stable_source_id_is_a_definite_duplicate(self):
        row = self.row(source_id="BANK-42")
        existing = self.existing(row, source_id="BANK-42")
        result = classify_import_rows([row], self.state_with(existing))
        self.assertEqual(len(result.definite_duplicates), 1)
        self.assertFalse(result.new_rows)

    def test_source_id_row_matching_manual_transaction_is_possible(self):
        row = self.row(source_id="BANK-42")
        manual = self.existing(row, source_id=None)
        result = classify_import_rows([row], self.state_with(manual))
        self.assertEqual(len(result.possible_duplicates), 1)
        self.assertFalse(result.new_rows)
        self.assertFalse(result.definite_duplicates)

    def test_fallback_match_is_possible_not_definite(self):
        row = self.row()
        result = classify_import_rows(
            [row], self.state_with(self.existing(row))
        )
        self.assertEqual(len(result.possible_duplicates), 1)
        self.assertFalse(result.definite_duplicates)

    def test_same_fields_on_another_account_are_new(self):
        existing_row = self.row(account_id=1)
        incoming = self.row(account_id=2)
        result = classify_import_rows(
            [incoming], self.state_with(self.existing(existing_row))
        )
        self.assertEqual(result.new_rows, (incoming,))

    def test_two_legitimate_identical_purchases_in_one_file_are_new(self):
        first = self.row()
        second = self.row()
        result = classify_import_rows([first, second], self.empty_state())
        self.assertEqual(len(result.new_rows), 2)
        self.assertFalse(result.possible_duplicates)

    def test_db_one_incoming_two_has_one_possible_and_one_new(self):
        first = self.row()
        second = self.row()
        result = classify_import_rows(
            [first, second], self.state_with(self.existing(first))
        )
        self.assertEqual(len(result.new_rows), 1)
        self.assertEqual(len(result.possible_duplicates), 1)

    def test_db_two_incoming_two_has_no_new_occurrence(self):
        first = self.row()
        second = self.row()
        result = classify_import_rows(
            [first, second],
            self.state_with(
                self.existing(first, row_id=1),
                self.existing(first, row_id=2),
            ),
        )
        self.assertFalse(result.new_rows)
        self.assertEqual(len(result.possible_duplicates), 2)

    def test_overlap_across_files_is_held_for_review(self):
        first = self.row(batch_file_id="a", file_hash="a-hash")
        overlap = self.row(batch_file_id="b", file_hash="b-hash")
        result = classify_import_rows([first, overlap], self.empty_state())
        self.assertEqual(len(result.new_rows), 1)
        self.assertEqual(len(result.possible_duplicates), 1)

    def test_identical_files_in_one_batch_are_definite(self):
        first = self.row(batch_file_id="a", file_hash="same")
        renamed = self.row(batch_file_id="b", file_hash="same")
        result = classify_import_rows([first, renamed], self.empty_state())
        self.assertEqual(result.new_rows, (first,))
        self.assertEqual(len(result.definite_duplicates), 1)

    def test_identical_file_content_on_different_accounts_is_not_duplicate(self):
        first = self.row(account_id=1, batch_file_id="a", file_hash="same")
        second = self.row(account_id=2, batch_file_id="b", file_hash="same")
        result = classify_import_rows([first, second], self.empty_state())
        self.assertEqual(result.new_rows, (first, second))
        self.assertFalse(result.definite_duplicates)


class ParserDeduplicationIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.sessions = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        with self.sessions.begin() as session:
            user = User(id="owner", name="Owner", color="#123456")
            session.add(user)
            session.flush()
            self.account = Account(
                user_id=user.id,
                name="TD Debit",
                institution="TD",
                account_type="debit",
            )
            session.add(self.account)
            session.flush()
            self.account_id = self.account.id

    def tearDown(self):
        self.engine.dispose()

    @staticmethod
    def td_bytes(*rows):
        return ("\n".join(rows) + "\n").encode()

    def parser(self, names, contents):
        parser = GenericParser(
            [(name, SUPPORTED_PARSE_TYPES.TD_DEBIT.value) for name in names],
            "owner",
        )
        with (
            patch("parsers.generic_parser.SessionLocal", self.sessions),
            patch.object(
                GenericParser,
                "_open_file_contents",
                side_effect=contents,
            ),
        ):
            parser.parse()
        return parser

    def transaction_count(self):
        with self.sessions() as session:
            return session.scalar(select(func.count(Transaction.id)))

    def test_exact_same_and_renamed_file_are_auto_skipped(self):
        contents = self.td_bytes("09/10/2026,Coffee,-7.50")
        first = self.parser(["original.csv"], [contents])
        second = self.parser(["renamed.csv"], [contents])
        self.assertEqual(first.get_import_summary().added, 1)
        self.assertEqual(
            second.get_import_summary().definite_duplicates_skipped, 1
        )
        self.assertEqual(self.transaction_count(), 1)

    def test_same_batch_overlap_is_not_inserted_before_review(self):
        first = self.td_bytes("09/10/2026,Coffee,-7.50")
        second = self.td_bytes("09/10/2026,Coffee,-7.50", "09/11/2026,Tea,-3.00")
        parser = self.parser(["a.csv", "b.csv"], [first, second])
        self.assertEqual(parser.get_import_summary().added, 2)
        self.assertEqual(len(parser.get_possible_duplicates()), 1)
        self.assertEqual(self.transaction_count(), 2)

    def test_keep_incoming_inserts_and_skip_does_not(self):
        original = self.td_bytes("09/10/2026,Coffee,-7.50")
        changed_file = self.td_bytes("09/10/2026,Coffee,-7.50", "")
        self.parser(["old.csv"], [original])
        keep = self.parser(["new.csv"], [changed_file])
        keep.set_all_duplicate_decisions(DuplicateDecision.KEEP)
        summary = keep.commit_duplicate_decisions()
        self.assertEqual(summary.possible_kept, 1)
        self.assertEqual(self.transaction_count(), 2)

        skip = self.parser(["third.csv"], [changed_file + b"\n"])
        skip.set_all_duplicate_decisions(DuplicateDecision.SKIP)
        summary = skip.commit_duplicate_decisions()
        self.assertEqual(summary.possible_skipped, 1)
        self.assertEqual(self.transaction_count(), 2)

    def test_unresolved_review_cannot_commit(self):
        original = self.td_bytes("09/10/2026,Coffee,-7.50")
        self.parser(["old.csv"], [original])
        pending = self.parser(["new.csv"], [original + b"\n"])
        with self.assertRaisesRegex(ValueError, "Resolve every"):
            pending.commit_duplicate_decisions()

    def test_soft_deleted_transaction_can_be_reimported(self):
        contents = self.td_bytes("09/10/2026,Coffee,-7.50")
        self.parser(["old.csv"], [contents])
        with self.sessions.begin() as session:
            transaction = session.scalar(select(Transaction))
            transaction.is_deleted = True
        again = self.parser(["again.csv"], [contents])
        self.assertEqual(again.get_import_summary().added, 1)
        with self.sessions() as session:
            active = session.scalar(select(func.count(Transaction.id)).where(
                Transaction.is_deleted.is_(False)
            ))
        self.assertEqual(active, 1)

    def test_category_and_type_edits_do_not_change_stored_identity(self):
        contents = self.td_bytes("09/10/2026,Coffee,-7.50")
        self.parser(["old.csv"], [contents])
        with self.sessions.begin() as session:
            transaction = session.scalar(select(Transaction))
            original_fingerprint = transaction.dedupe_fingerprint
            transaction.transaction_type = TransactionType.INCOME
            transaction.category_id = None
        pending = self.parser(["changed.csv"], [contents + b"\n"])
        self.assertEqual(len(pending.get_possible_duplicates()), 1)
        with self.sessions() as session:
            transaction = session.scalar(select(Transaction))
            self.assertEqual(transaction.dedupe_fingerprint, original_fingerprint)

    def test_bulk_existing_load_uses_one_select_and_ignores_deleted(self):
        with self.sessions.begin() as session:
            active = Transaction(
                account_id=self.account_id,
                transaction_date=date(2026, 9, 10),
                description="Coffee",
                amount=Decimal("-7.50"),
            )
            deleted = Transaction(
                account_id=self.account_id,
                transaction_date=date(2026, 9, 11),
                description="Tea",
                amount=Decimal("-3.00"),
                is_deleted=True,
            )
            session.add_all((active, deleted))
        incoming = [IncomingTransaction(
            account_id=self.account_id,
            account_name="TD Debit",
            transaction_date=date(2026, 9, 10),
            description="Coffee",
            amount=Decimal("-7.50"),
            source_file="new.csv",
            source_file_hash="new-hash",
            batch_file_id="one",
        )]
        select_count = 0

        def count_selects(_conn, _cursor, statement, _parameters, _context, _many):
            nonlocal select_count
            if statement.lstrip().upper().startswith("SELECT"):
                select_count += 1

        event.listen(self.engine, "before_cursor_execute", count_selects)
        try:
            with self.sessions() as session:
                state = load_existing_duplicate_state(session, incoming)
        finally:
            event.remove(self.engine, "before_cursor_execute", count_selects)
        self.assertEqual(select_count, 1)
        self.assertEqual(len(state.rows), 1)

    def test_existing_duplicate_utility_reports_without_mutation(self):
        with self.sessions.begin() as session:
            for _ in range(2):
                session.add(Transaction(
                    account_id=self.account_id,
                    transaction_date=date(2026, 9, 10),
                    description="Coffee",
                    amount=Decimal("-7.50"),
                ))
        with self.sessions() as session:
            candidates = find_existing_duplicate_candidates(session)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].count, 2)
        self.assertEqual(self.transaction_count(), 2)

    def test_amex_reference_is_stored_as_source_id(self):
        with self.sessions.begin() as session:
            session.add(Account(
                user_id="owner",
                name="Amex",
                institution="American Express",
                account_type="credit",
            ))
        contents = (
            ",".join(AMEX_COLUMNS)
            + "\n"
            + "10/09/2026,11/09/2026,Coffee,7.50,,,,,Merchant,Address,"
            "Toronto,A1A 1A1,Canada,REF-42\n"
        ).encode()
        parser = GenericParser(
            [("amex.csv", SUPPORTED_PARSE_TYPES.AMEX.value)], "owner"
        )
        with (
            patch("parsers.generic_parser.SessionLocal", self.sessions),
            patch.object(GenericParser, "_open_file_contents", return_value=contents),
        ):
            parser.parse()
        with self.sessions() as session:
            source_id = session.scalar(
                select(Transaction.source_transaction_id).where(
                    Transaction.account_id != self.account_id
                )
            )
        self.assertEqual(source_id, "REF-42")


class DuplicateReviewDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def candidates(self):
        row = IncomingTransaction(
            account_id=1,
            account_name="TD Debit",
            transaction_date=date(2026, 9, 10),
            description="Coffee",
            amount=Decimal("-7.50"),
            source_file="new.csv",
            source_file_hash="new",
            batch_file_id="one",
        )
        overlap = IncomingTransaction(
            account_id=1,
            account_name="TD Debit",
            transaction_date=date(2026, 9, 10),
            description="Coffee",
            amount=Decimal("-7.50"),
            source_file="overlap.csv",
            source_file_hash="overlap",
            batch_file_id="two",
        )
        service = DeduplicationServiceTest()
        existing = service.existing(row)
        return list(classify_import_rows(
            [row, overlap], service.state_with(existing)
        ).possible_duplicates)

    def test_unresolved_candidates_disable_import_selected(self):
        dialog = DuplicateReviewDialog(self.candidates())
        self.assertFalse(dialog.submit_button.isEnabled())
        dialog.close()

    def test_keep_all_and_skip_all_are_overridable(self):
        candidates = self.candidates()
        dialog = DuplicateReviewDialog(candidates)
        dialog.keep_all_button.click()
        self.assertTrue(dialog.submit_button.isEnabled())
        self.assertTrue(all(
            item.decision == DuplicateDecision.KEEP for item in candidates
        ))
        dialog.cards[0].skip_button.click()
        self.assertEqual(candidates[0].decision, DuplicateDecision.SKIP)
        self.assertEqual(candidates[1].decision, DuplicateDecision.KEEP)
        dialog.close()

    def test_skip_all_marks_every_candidate_without_committing(self):
        candidates = self.candidates()
        dialog = DuplicateReviewDialog(candidates)
        dialog.skip_all_button.click()
        self.assertTrue(all(
            item.decision == DuplicateDecision.SKIP for item in candidates
        ))
        self.assertTrue(dialog.submit_button.isEnabled())
        dialog.close()

    def test_possible_duplicate_reason_uses_standard_app_font(self):
        previous_stylesheet = self.app.styleSheet()
        self.app.setStyleSheet(APP_STYLESHEET)
        try:
            dialog = DuplicateReviewDialog(self.candidates())
            reason = dialog.findChild(QLabel, "duplicateReason")
            detail = dialog.findChild(QLabel, "duplicateDetailsText")
            self.assertIsNotNone(reason)
            self.assertIsNotNone(detail)
            self.assertEqual(reason.font().toString(), detail.font().toString())
            dialog.close()
        finally:
            self.app.setStyleSheet(previous_stylesheet)


if __name__ == "__main__":
    unittest.main()
