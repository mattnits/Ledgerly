import os
import threading
import time
import unittest
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database.db import Base
from database.models import Account, Transaction, User
from database.transactions import TransactionQueryResult, TransactionRowData
from ui.components.statements_table import StatementsTable
from ui.shell import ShellWindow
from utils.constants import TRANSACTIONS_PAGE, TransactionType


def _result(description: str) -> TransactionQueryResult:
    row = TransactionRowData(
        id=1,
        transaction_date=date.today(),
        description=description,
        amount=Decimal("-1.00"),
        transaction_type=TransactionType.EXPENSE,
        imported_at=datetime.now(),
        category_id=None,
        account_name="Checking",
        institution="Test",
        is_deleted=False,
    )
    return TransactionQueryResult(
        rows=(row,),
        total_count=1,
        filtered_count=1,
        accounts=((1, "Checking", "Test"),),
        categories=(),
        available_months=frozenset({(date.today().year, date.today().month)}),
    )


class TransactionAsyncLoadingTest(unittest.TestCase):
    @staticmethod
    def _wait_for(predicate, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            QApplication.processEvents()
            if predicate():
                return
            QTest.qWait(10)
        raise AssertionError("Timed out waiting for asynchronous UI state")

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])

    def test_worker_loading_state_and_stale_result_protection(self):
        first_query_release = threading.Event()
        worker_threads = []

        def loader(params, session_factory):
            worker_threads.append(threading.get_ident())
            if not params.search:
                first_query_release.wait(2)
                return _result("old result")
            return _result(params.search)

        table = StatementsTable(query_loader=loader)
        table.show()
        main_thread = threading.get_ident()
        table.set_user_id("test-user")

        self.assertTrue(table._loading)
        self.assertTrue(table.loading_overlay.isVisible())
        table.search.setText("new result")
        self._wait_for(
            lambda: not table._loading
            and table.rows
            and table.rows[0].description == "new result"
        )

        first_query_release.set()
        self._wait_for(lambda: not table._active_workers)
        self.assertEqual(table.rows[0].description, "new result")
        self.assertTrue(worker_threads)
        self.assertTrue(all(thread_id != main_thread for thread_id in worker_threads))
        self.assertFalse(table.loading_overlay.isVisible())
        table.close()

    def test_search_is_debounced_to_one_query_after_typing_pauses(self):
        searches = []

        def loader(params, session_factory):
            searches.append(params.search)
            return _result(params.search or "initial")

        table = StatementsTable(query_loader=loader)
        table.show()
        table.set_user_id("test-user")
        self._wait_for(lambda: not table._loading)
        searches.clear()

        table.search.setText("t")
        table.search.setText("ti")
        table.search.setText("tim")
        QTest.qWait(150)
        QApplication.processEvents()
        self.assertEqual(searches, [])
        self._wait_for(lambda: not table._loading and searches == ["tim"])
        table.close()

    def test_query_failure_shows_non_blocking_retry_state(self):
        attempts = 0

        def loader(params, session_factory):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("database detail that should stay out of the UI")
            return _result("retry succeeded")

        table = StatementsTable(query_loader=loader)
        table.show()
        with self.assertLogs("ui.components.statements_table", level="ERROR"):
            table.set_user_id("test-user")
            self._wait_for(lambda: not table._loading)

        self.assertTrue(table.loading_overlay.isVisible())
        self.assertTrue(table.loading_overlay.retry_button.isVisible())
        self.assertEqual(
            table.loading_overlay.label.text(),
            "Could not load transactions.",
        )
        self.assertNotIn("database detail", table.loading_overlay.label.text())
        table.loading_overlay.retry_button.click()
        self._wait_for(
            lambda: not table._loading
            and table.rows
            and table.rows[0].description == "retry succeeded"
        )
        table.close()

    def test_real_query_session_is_created_and_closed_in_worker_thread(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        setup_sessions = sessionmaker(bind=engine)
        with setup_sessions.begin() as session:
            user = User(id="test-user", name="Test", color="#123456")
            session.add(user)
            session.flush()
            account = Account(
                user_id=user.id,
                name="Checking",
                institution="Test",
                account_type="debit",
            )
            session.add(account)
            session.flush()
            session.add(Transaction(
                account_id=account.id,
                transaction_date=date.today(),
                description="Worker owned",
                amount=Decimal("-1.00"),
                transaction_type=TransactionType.EXPENSE,
            ))

        created_threads = []
        closed_threads = []

        class TrackingSession(Session):
            def __init__(self, *args, **kwargs):
                created_threads.append(threading.get_ident())
                super().__init__(*args, **kwargs)

            def close(self):
                closed_threads.append(threading.get_ident())
                super().close()

        sessions = sessionmaker(bind=engine, class_=TrackingSession)
        main_thread = threading.get_ident()
        table = StatementsTable(session_factory=sessions)
        table.show()
        table.set_user_id("test-user")
        self._wait_for(lambda: not table._loading and table.loaded_count == 1)

        self.assertEqual(len(created_threads), 1)
        self.assertEqual(closed_threads, created_threads)
        self.assertNotEqual(created_threads[0], main_thread)
        table.close()
        engine.dispose()

    def test_navigation_switches_to_transactions_before_refresh(self):
        events = []

        class Page:
            def reload(self):
                events.append("refresh")

        class Stack:
            def setCurrentWidget(self, page):
                events.append("switch")

        transactions_page = Page()
        shell = SimpleNamespace(
            pages=Stack(),
            dashboard_page=Page(),
            transactions_page=transactions_page,
            accounts_page=Page(),
            investments_page=Page(),
            categories_page=Page(),
            settings_page=Page(),
        )

        ShellWindow.change_page(shell, TRANSACTIONS_PAGE)

        self.assertEqual(events, ["switch", "refresh"])


if __name__ == "__main__":
    unittest.main()
