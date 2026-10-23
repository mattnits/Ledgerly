"""Render selector surfaces with synthetic data, never the application database.

Run from the repository root with QT_SCALE_FACTOR=1, 1.25 or 1.5. Outputs go
to a new dropdown-review-* directory. This is a manual visual audit, not a golden test.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea, QToolButton, QVBoxLayout, QWidget
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, engine as application_engine
from app.models.models import Account, Category, Transaction, User
from app.services.investments import (
    create_investment_account, create_investment_snapshot, get_investment_accounts,
)
from app.services.goals import CategoryBudgetProgress, SavingsGoalRecord
from app.ui.dialogs.add_user import AddUserDialog
from app.ui.dialogs.classification_rules import ClassificationRulesDialog
from app.ui.dialogs.duplicate_review_dialog import DuplicateReviewDialog
from app.ui.dialogs.file_upload_dialog import FileUploadDialog
from app.ui.dialogs.generic_dialog import GenericDialog
from app.ui.dialogs.switch_user import SwitchUserDialog
from app.ui.pages.accounts import AccountsPage
from app.ui.pages.categories import CategoriesPage
from app.ui.pages.dashboard import DashboardPage
from app.ui.pages.goals import BudgetDialog, GoalsPage, SavingsGoalDialog
from app.ui.pages.investments import (
    InvestmentAccountDialog, InvestmentsPage, PortfolioEntryDialog, WorkRrspContributionDialog,
)
from app.ui.pages.settings import SettingsPage
from app.ui.pages.transactions import TransactionsPage
from app.ui.pages.user_management import UserManagementPage
from app.ui.sidebar import ProfileMenu
from app.ui.theme import apply_theme
from app.ui.widgets.combo_box import AppComboBox
from app.ui.widgets.date_picker import DatePickerEdit
from app.ui.widgets.statements_table import StatementsTable
from app.ui.widgets.transaction_row import TransactionRow
from app.utils.constants import TransactionType


def main() -> None:
    # Normal inherited permissions are needed for viewing screenshots in a
    # separate process on Windows; tempfile.mkdtemp uses an owner-only ACL.
    output = Path(__file__).resolve().parents[1] / f"dropdown-review-{uuid4().hex[:8]}"
    output.mkdir()

    def reject_default_connection(*_args):
        raise AssertionError("The visual audit must never connect to the application database")

    event.listen(application_engine, "do_connect", reject_default_connection)
    app = QApplication.instance() or QApplication([])
    # Windows' offscreen Qt plugin does not enumerate installed system fonts.
    font_path = Path("C:/Windows/Fonts/segoeui.ttf")
    if font_path.is_file():
        QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Segoe UI", 10))
    apply_theme(app)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    categories = [(1, "Food", "#df6714"), (2, "Travel and transportation", "#398cff")]
    with sessions.begin() as session:
        session.add(User(id="audit", name="Example User", color="#398cff", is_admin=True))
        session.add_all(Category(id=i, name=n, color=c) for i, n, c in categories)
        account = Account(name="Everyday account", institution="Example Bank", account_type="debit", user_id="audit")
        session.add(account)
        session.flush()
        session.add(Transaction(account_id=account.id, transaction_date=date.today(),
                                description="Example purchase", amount=Decimal(-10),
                                transaction_type=TransactionType.EXPENSE, category_id=1))
    investment_id = create_investment_account("Example Bank", "Retirement", account_type="RRSP", user_id="audit", is_work_related=True, session_factory=sessions)
    create_investment_snapshot(investment_id, date.today(), Decimal(1000), session_factory=sessions)
    accounts = get_investment_accounts(user_id="audit", session_factory=sessions)
    captures = []
    page_captures = []
    maximized_captures = []
    checked = 0

    def capture_surface(name, root, *, page=False):
        nonlocal checked
        sizes = [(800, 650), (1400, 900), (1800, 1000), (None, None)] if page else [(root.width(), root.height())]
        for width, height in sizes:
            if width is None:
                root.showMaximized()
            else:
                root.resize(width, height)
                root.show()
            app.processEvents()
            for combo in root.findChildren(AppComboBox):
                if not combo.isVisible() or not combo.isEnabled() or not combo.count():
                    continue
                for scroll in root.findChildren(QScrollArea):
                    if scroll.widget() and scroll.widget().isAncestorOf(combo):
                        scroll.ensureWidgetVisible(combo)
                app.processEvents()
                before = root.geometry(), combo.geometry(), combo.currentIndex()
                combo.showPopup()
                app.processEvents()
                popup = combo.view().window()
                assert popup.isVisible(), name
                assert (root.geometry(), combo.geometry(), combo.currentIndex()) == before, name
                assert combo.screen().availableGeometry().contains(popup.geometry()), name
                assert popup.height() == combo.view().viewport().height() + 2, name
                assert combo.view().viewport().height() % combo.popup_row_height() == 0, (name, combo.objectName(), popup.geometry(), combo.popup_row_height(), combo.view().font().toString())
                assert combo.view().horizontalScrollBar().maximum() == 0, name
                checked += 1
                if width == sizes[0][0]:
                    captures.append((f"{name}: {combo.objectName() or combo.currentText()}", popup.grab().toImage()))
                combo.hidePopup()
            if width == sizes[0][0]:
                for editor in root.findChildren(DatePickerEdit):
                    if not editor.isVisible() or not editor.isEnabled():
                        continue
                    for scroll in root.findChildren(QScrollArea):
                        if scroll.widget() and scroll.widget().isAncestorOf(editor):
                            scroll.ensureWidgetVisible(editor)
                    app.processEvents()
                    QTest.mouseClick(editor, Qt.MouseButton.LeftButton,
                                     pos=QPoint(editor.width() - 20, editor.height() // 2))
                    app.processEvents()
                    calendar = editor.calendarWidget()
                    assert calendar.isVisible(), name
                    assert calendar.window().windowFlags() & Qt.WindowType.NoDropShadowWindowHint
                    captures.append((f"{name}: calendar", calendar.window().grab().toImage()))
                    month_button = calendar.findChild(QToolButton, "qt_calendar_monthbutton")
                    menu = month_button.menu()
                    menu.popup(month_button.mapToGlobal(QPoint(0, month_button.height())))
                    app.processEvents()
                    captures.append((f"{name}: calendar months", menu.grab().toImage()))
                    menu.hide()
                    calendar.window().hide()
            if width == sizes[0][0]:
                image = root.grab().toImage()
                assert image.save(str(output / f"{name}.png"))
                page_captures.append((name, image))
            if width is None:
                image = root.grab().toImage()
                assert image.save(str(output / f"{name}-maximized.png"))
                maximized_captures.append((f"{name}: maximized", image))
        root.close()

    with patch("app.ui.widgets.file_selection.save_imported_files_enabled", return_value=False), \
         patch("app.ui.pages.settings.open_fullscreen_enabled", return_value=True), \
         patch("app.ui.pages.settings.save_imported_files_enabled", return_value=False), \
         patch("app.ui.pages.categories.list_categories", return_value=[(*c, True) for c in categories]), \
         patch("app.ui.pages.transactions.StatementsTable", side_effect=lambda: StatementsTable(session_factory=sessions)):
        for name, factory in (
            ("dashboard", lambda: DashboardPage(session_factory=sessions)),
            ("transactions", TransactionsPage),
            ("investments", lambda: InvestmentsPage(session_factory=sessions)),
            ("accounts", lambda: AccountsPage(session_factory=sessions)),
            ("categories", CategoriesPage),
            ("goals", lambda: GoalsPage(session_factory=sessions)),
            ("user-management", lambda: UserManagementPage(session_factory=sessions)),
            ("settings", SettingsPage),
        ):
            root = factory()
            if hasattr(root, "set_user_id"):
                root.set_user_id("audit")
            if name == "transactions":
                for _ in range(200):
                    app.processEvents()
                    if not root.statements_table._loading:
                        break
                    QTest.qWait(10)
                assert not root.statements_table._loading
            if name == "user-management":
                root.set_current_user("audit")
            capture_surface(name, root, page=True)

        for name, factory in (
            ("add-investment-account", InvestmentAccountDialog),
            ("edit-investment-account", lambda: InvestmentAccountDialog(account=accounts[0])),
            ("portfolio-entry", lambda: PortfolioEntryDialog(accounts)),
            ("rrsp-contribution", lambda: WorkRrspContributionDialog(accounts, session_factory=sessions)),
            ("add-budget", lambda: BudgetDialog(categories, 2026, 10)),
            ("edit-budget", lambda: BudgetDialog(categories, 2026, 10,
                CategoryBudgetProgress(1, "Food", "#df6714", Decimal(20), Decimal(300)))),
            ("savings-goal", SavingsGoalDialog),
            ("edit-savings-goal", lambda: SavingsGoalDialog(SavingsGoalRecord(
                1, "Trip", Decimal(2000), Decimal(500), date(2027, 5, 1), "Example goal"))),
            ("add-user", lambda: AddUserDialog(session_factory=sessions)),
            ("switch-user", lambda: SwitchUserDialog([dict(id="audit", name="Example User", color="#398cff", is_admin=True)], "audit")),
            ("duplicate-review", lambda: DuplicateReviewDialog([])),
        ):
            capture_surface(name, factory())
        group = AddUserDialog(session_factory=sessions)
        group.set_creation_type("group")
        capture_surface("add-group", group)
        statements = FileUploadDialog()
        statements.file_selection.set_files([str(Path(__file__).resolve())])
        capture_surface("statements", statements)
        rules = ClassificationRulesDialog("audit", session_factory=sessions)
        with patch.object(GenericDialog, "exec", lambda dialog: capture_surface("classification-editor", dialog) or 0):
            rules._open_editor()
        capture_surface("classification-rules", rules)
        profile = ProfileMenu(dict(
            id="audit", name="Example User", color="#398cff", is_admin=True, type="user"))
        profile.adjustSize()
        capture_surface("profile-menu", profile)
        inline = QWidget()
        layout = QVBoxLayout(inline)
        row = TransactionRow(1, date.today(), "Example purchase", Decimal(-10),
                             TransactionType.EXPENSE, datetime.now(), 1,
                             "Everyday account", "Example Bank", False, categories)
        layout.addWidget(row.transaction_type_cell)
        layout.addWidget(row.category_cell)
        inline.resize(320, 110)
        capture_surface("transaction-inline", inline)

    for count in (1, 3, 6, 20):
        combo = AppComboBox()
        combo.addItems([f"Example option {i + 1}" for i in range(count)])
        combo.resize(260, 42)
        combo.move(80, 80)
        combo.show()
        combo.showPopup()
        app.processEvents()
        captures.append((f"{count} options", combo.view().window().grab().toImage()))
        combo.hidePopup()
        combo.close()

    def sheets(items, prefix, cell_width, cell_height):
        for offset in range(0, len(items), 12):
            batch = items[offset:offset + 12]
            sheet = QImage(cell_width * 3, cell_height * 4, QImage.Format.Format_ARGB32)
            sheet.fill(QColor("#0d0f12"))
            painter = QPainter(sheet)
            painter.setFont(QFont("Segoe UI", 10))
            painter.setPen(QColor("white"))
            for i, (label, image) in enumerate(batch):
                x, y = i % 3 * cell_width, i // 3 * cell_height
                painter.drawText(QRect(x + 8, y, cell_width - 16, 28), Qt.AlignmentFlag.AlignVCenter, label)
                thumb = image.scaled(cell_width - 16, cell_height - 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                thumb.setDevicePixelRatio(1)
                painter.drawImage(QPoint(x + 8, y + 30), thumb)
            painter.end()
            assert sheet.save(str(output / f"{prefix}-{offset // 12}.png"))

    sheets(captures, "popups", 460, 370)
    sheets(page_captures, "surfaces", 460, 400)
    sheets(maximized_captures, "maximized", 460, 400)
    print(f"Checked {checked} popup openings; {len(page_captures)} surfaces; scale={os.environ.get('QT_SCALE_FACTOR', '1')}")
    print(output)
    engine.dispose()


if __name__ == "__main__":
    main()
