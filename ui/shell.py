from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QStackedWidget,
)

from database.db import get_profiles
from database.profiles import ProfileContext
from ui.accounts import AccountsPage
from ui.categories import CategoriesPage
from ui.sidebar import Sidebar

from ui.welcome import WelcomePage
from ui.add_user import AddUserDialog
from ui.switch_user import SwitchUserDialog
from ui.dashboard import DashboardPage
from ui.investments import InvestmentsPage
from ui.transactions import TransactionsPage
from ui.settings import SettingsPage
from utils.constants import (
    ACCOUNTS_PAGE,
    CATEGORIES_PAGE,
    DASHBOARD_PAGE,
    INVESTMENTS_PAGE,
    SETTINGS_PAGE,
    TRANSACTIONS_PAGE,
)


class ShellWindow(QMainWindow):
    startup_ready = Signal()

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Finance")
        self.resize(1400, 850)
        self.setMinimumSize(1100, 700)
        self._active_user_dialog: QDialog | None = None
        self._pending_group_edit: int | None = None
        self._startup_setup_complete = False
        self._startup_ready = False

        # -------------------------
        # Root widget
        # -------------------------

        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)

        root_layout = QHBoxLayout(root)

        root_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        root_layout.setSpacing(0)

        # -------------------------
        # Sidebar
        # -------------------------

        self.sidebar = Sidebar()

        # Hidden during initial setup
        self.sidebar.hide()

        # -------------------------
        # Page stack
        # -------------------------

        self.pages = QStackedWidget()
        self.pages.setObjectName("pageStack")

        self.welcome_page = WelcomePage()

        self.dashboard_page = DashboardPage()
        self.transactions_page = TransactionsPage()
        self.settings_page = SettingsPage()
        self.accounts_page = AccountsPage()
        self.investments_page = InvestmentsPage()
        self.categories_page = CategoriesPage()

        self.pages.addWidget(
            self.welcome_page
        )

        self.pages.addWidget(
            self.dashboard_page
        )

        self.pages.addWidget(
            self.transactions_page
        )

        self.pages.addWidget(
            self.accounts_page
        )

        self.pages.addWidget(self.investments_page)

        self.pages.addWidget(self.categories_page)

        self.pages.addWidget(
            self.settings_page
        )

        # -------------------------
        # Main layout
        # -------------------------

        root_layout.addWidget(
            self.sidebar
        )

        root_layout.addWidget(
            self.pages,
            1,
        )

        # -------------------------
        # Navigation signals
        # -------------------------

        self.sidebar.page_changed.connect(
            self.change_page
        )

        self.sidebar.create_user_clicked.connect(
            self.show_add_user
        )

        self.sidebar.switch_user_clicked.connect(
            self.show_switch_user
        )

        self.sidebar.user_changed.connect(
            self.handle_user_changed
        )
        self.sidebar.profile_changed.connect(self.handle_profile_changed)

        self.welcome_page.add_user_clicked.connect(
            self.show_add_user
        )

        self.settings_page.data_reset.connect(self.handle_data_reset)
        self.transactions_page.statements_table.loading_changed.connect(
            self._handle_startup_loading_changed
        )

        # -------------------------
        # Initial page
        # -------------------------

        self.load_users()

    @property
    def is_startup_ready(self) -> bool:
        return self._startup_ready

    def _handle_startup_loading_changed(self, loading: bool) -> None:
        if self._startup_setup_complete and not loading:
            self._mark_startup_ready()

    def _mark_startup_ready(self) -> None:
        if self._startup_ready:
            return
        self._startup_ready = True
        self.startup_ready.emit()

    def load_users(self, current_user_id: str | None = None):
        current_key = f"user:{current_user_id}" if current_user_id else None
        self.load_profiles(current_key)

    def load_profiles(self, current_profile_key: str | None = None) -> None:
        profiles = get_profiles()
        self.sidebar.set_profiles(profiles, current_profile_key)
        self._apply_profile(self.sidebar.current_profile_key)

        if profiles:
            self.sidebar.show()
            self.pages.setCurrentWidget(self.dashboard_page)
        else:
            self.sidebar.hide()
            self.pages.setCurrentWidget(self.welcome_page)
        if not self._startup_setup_complete:
            self._startup_setup_complete = True
            if not self.transactions_page.statements_table._loading:
                self._mark_startup_ready()

    def show_add_user(self):
        dialog = AddUserDialog(self)
        dialog.user_created.connect(self.handle_user_created)
        dialog.group_created.connect(self.handle_group_created)
        self._run_user_dialog(dialog)

    def show_switch_user(self):
        dialog = SwitchUserDialog(
            self.sidebar.profiles,
            self.sidebar.current_profile_key,
            self,
        )
        dialog.profile_selected.connect(self.sidebar.select_profile)
        dialog.group_edit_requested.connect(self._queue_group_edit)
        self._run_user_dialog(dialog)
        if self._pending_group_edit is not None:
            group_id = self._pending_group_edit
            self._pending_group_edit = None
            self.show_edit_group(group_id)

    def _queue_group_edit(self, group_id: int) -> None:
        self._pending_group_edit = group_id

    def show_edit_group(self, group_id: int) -> None:
        dialog = AddUserDialog(self, group_id=group_id)
        dialog.group_updated.connect(self.handle_group_updated)
        self._run_user_dialog(dialog)

    def _run_user_dialog(self, dialog: QDialog) -> None:
        """Run one centered user dialog at a time."""
        if self._active_user_dialog is not None:
            dialog.deleteLater()
            self._active_user_dialog.raise_()
            self._active_user_dialog.activateWindow()
            return

        self._active_user_dialog = dialog
        try:
            dialog.exec()
        finally:
            self._active_user_dialog = None
            dialog.deleteLater()

    def handle_user_created(self, user_id: str):
        self.load_users(user_id)

    def handle_group_created(self, group_id: int) -> None:
        self.load_profiles(f"group:{group_id}")

    def handle_group_updated(self, group_id: int) -> None:
        self.load_profiles(f"group:{group_id}")

    def handle_user_changed(self, user_id: str):
        # Compatibility path for older callers that still select raw users.
        self._apply_profile(f"user:{user_id}")
        self.pages.setCurrentWidget(self.dashboard_page)

    def handle_profile_changed(self, profile_key: str) -> None:
        self._apply_profile(profile_key)
        self.pages.setCurrentWidget(self.dashboard_page)

    def _apply_profile(self, profile_key: str | None) -> None:
        if profile_key is None:
            user_id = group_id = None
        else:
            context = ProfileContext.from_key(profile_key)
            user_id, group_id = context.user_id, context.group_id
        self.dashboard_page.set_profile(user_id=user_id, group_id=group_id)
        self.transactions_page.set_profile(user_id=user_id, group_id=group_id)
        self.investments_page.set_profile(user_id=user_id, group_id=group_id)
        self.accounts_page.set_profile(user_id=user_id, group_id=group_id)

    def handle_data_reset(self) -> None:
        self.dashboard_page.reload()
        self.transactions_page.reload()
        self.accounts_page.reload()
        self.investments_page.reload()

    def change_page(self, page_name: str):

        pages = {
            DASHBOARD_PAGE: self.dashboard_page,
            TRANSACTIONS_PAGE: self.transactions_page,
            ACCOUNTS_PAGE: self.accounts_page,
            INVESTMENTS_PAGE: self.investments_page,
            CATEGORIES_PAGE: self.categories_page,
            SETTINGS_PAGE: self.settings_page,
        }

        page = pages.get(page_name)

        if page is not None:
            self.pages.setCurrentWidget(page)
            if page is self.transactions_page:
                self.transactions_page.reload()
            if page is self.dashboard_page:
                self.dashboard_page.reload()
            if page is self.accounts_page:
                self.accounts_page.reload()
            if page is self.investments_page:
                self.investments_page.reload()
            if page is self.categories_page:
                self.categories_page.reload()
