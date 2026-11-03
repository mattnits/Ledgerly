import os
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QLineEdit, QMessageBox
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models.models import Account, Category, CategoryRule, User
from app.ui.dialogs.classification_rules import ClassificationRulesDialog
from app.ui.dialogs.generic_dialog import GenericDialog


class ClassificationRuleAsyncUiTest(unittest.TestCase):
    @staticmethod
    def _wait_for(predicate, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            QApplication.processEvents()
            if predicate():
                return
            QTest.qWait(10)
        raise AssertionError("Timed out waiting for asynchronous rule save")

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions.begin() as session:
            user = User(id="test-user", name="Test", color="#123456")
            food = Category(name="Food", color="#f97316")
            session.add_all((user, food))
            session.flush()
            session.add(
                Account(
                    user_id=user.id,
                    name="Checking",
                    institution="Test",
                    account_type="debit",
                )
            )

    def tearDown(self):
        self.engine.dispose()

    def test_apply_existing_shows_spinner_before_confirmation(self):
        started = threading.Event()
        release = threading.Event()
        worker_thread_ids = []
        captured_editor = []

        def slow_apply(_session, _user_id, _rule):
            worker_thread_ids.append(threading.get_ident())
            started.set()
            if not release.wait(2):
                raise TimeoutError("Test did not release the rule worker")
            return 7

        def exercise_editor(editor: GenericDialog):
            captured_editor.append(editor)
            editor.show()
            QApplication.processEvents()
            pattern = next(
                field
                for field in editor.findChildren(QLineEdit)
                if field.maxLength() == 255
            )
            apply_checkbox = next(
                field
                for field in editor.findChildren(QCheckBox)
                if field.text().startswith("Apply to")
            )
            pattern.setText("COFFEE")
            apply_checkbox.setChecked(True)
            editor.submit_button.click()
            self._wait_for(started.is_set)

            self.assertTrue(editor._busy)
            self.assertTrue(editor.loading_overlay.isVisible())
            self.assertTrue(editor.loading_overlay.spinner._timer.isActive())
            self.assertFalse(editor.submit_button.isEnabled())
            self.assertFalse(editor.cancel_button.isEnabled())
            self.assertFalse(editor.close_button.isEnabled())

            release.set()
            self._wait_for(lambda: editor.result() == QDialog.DialogCode.Accepted)
            return editor.result()

        rules_dialog = ClassificationRulesDialog(
            "test-user",
            session_factory=self.sessions,
        )
        main_thread_id = threading.get_ident()

        try:
            with (
                patch(
                    "app.ui.dialogs.classification_rules.apply_rule_to_existing_transactions",
                    side_effect=slow_apply,
                ),
                patch(
                    "app.ui.dialogs.classification_rules.count_transactions_matching_rule",
                    return_value=0,
                ),
                patch.object(GenericDialog, "exec", exercise_editor),
                patch.object(QMessageBox, "information", return_value=None) as info,
            ):
                rules_dialog._open_editor()
                self._wait_for(lambda: info.called)
        finally:
            release.set()
            rules_dialog._thread_pool.waitForDone(2000)
            rules_dialog.close()

        editor = captured_editor[0]
        self.assertFalse(editor.loading_overlay.spinner._timer.isActive())
        self.assertEqual(rules_dialog._active_save_workers, set())
        self.assertEqual(len(worker_thread_ids), 1)
        self.assertNotEqual(worker_thread_ids[0], main_thread_id)
        info.assert_called_once()
        self.assertIn("Updated 7", info.call_args.args[2])
        with self.sessions() as session:
            saved_count = session.scalar(select(func.count(CategoryRule.id)))
        self.assertEqual(saved_count, 1)

