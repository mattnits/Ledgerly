from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QMainWindow,
    QMessageBox,
    QWidget,
    QHBoxLayout,
    QStackedWidget,
)

from app.core.db import get_profiles
from app.services.profiles import ProfileContext
from app.core.session_context import CurrentSession
from app.ui.pages.accounts import AccountsPage
from app.ui.pages.categories import CategoriesPage
from app.ui.sidebar import Sidebar

from app.ui.pages.welcome import WelcomePage
from app.ui.dialogs.add_user import AddUserDialog
from app.ui.dialogs.switch_user import SwitchUserDialog
from app.ui.pages.dashboard import DashboardPage
from app.ui.pages.goals import GoalsPage
from app.ui.pages.investments import InvestmentsPage
from app.ui.pages.transactions import TransactionsPage
from app.ui.pages.settings import SettingsPage
from app.ui.pages.user_management import UserManagementPage
from app.ui.preferences import last_user_id, set_last_user_id
from app.utils.constants import (
    ACCOUNTS_PAGE,
    CATEGORIES_PAGE,
    DASHBOARD_PAGE,
    GOALS_PAGE,
    INVESTMENTS_PAGE,
    SETTINGS_PAGE,
    TRANSACTIONS_PAGE,
    USER_MANAGEMENT_PAGE,
)


class ShellWindow(QMainWindow):
    startup_ready = Signal()

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Ledgerly")
        self.resize(1400, 850)
        self.setMinimumSize(1100, 700)
        self._active_user_dialog: QDialog | None = None
        self._pending_group_edit: int | None = None
        self._startup_setup_complete = False
        self._startup_ready = False
        self.session = CurrentSession(current_user_id=last_user_id())

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
        self.goals_page = GoalsPage()
        self.user_management_page = UserManagementPage()

        # Month/year navigation is shared across the monthly pages.  The
        # value is initialized from the dashboard once the active profile is
        # loaded, then retained while the user moves around the app.
        self._selected_month: tuple[int, int] | None = None
        self._syncing_month_selection = False
        self.dashboard_page.period_selector.selection_changed.connect(
            self._handle_period_selection_changed
        )
        (
            self.transactions_page.statements_table.period_selector
            .selection_changed.connect(self._handle_period_selection_changed)
        )
        self.investments_page.period_selector.selection_changed.connect(
            self._handle_period_selection_changed
        )
        self.goals_page.month_navigator.period_changed.connect(
            self._handle_goal_month_changed
        )

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

        self.pages.addWidget(self.goals_page)

        self.pages.addWidget(self.user_management_page)

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
        self.sidebar.exit_requested.connect(self.confirm_exit)

        self.welcome_page.add_user_clicked.connect(
            self.show_add_user
        )

        self.settings_page.data_reset.connect(self.handle_data_reset)
        self.settings_page.fullscreen_preference_changed.connect(
            self.set_fullscreen_mode
        )
        self.dashboard_page.goals_requested.connect(
            self._show_goals_from_dashboard
        )
        self.settings_page.profile_deleted.connect(self.handle_profile_deleted)
        self.user_management_page.edit_user_requested.connect(self.show_edit_user)
        self.user_management_page.edit_group_requested.connect(
            self.show_edit_group_from_management
        )
        self.user_management_page.add_profile_requested.connect(
            self.show_add_profile_from_management
        )
        self.user_management_page.profiles_changed.connect(self.refresh_profiles)
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

    @property
    def opens_in_fullscreen(self) -> bool:
        return self.settings_page.open_fullscreen

    def show_with_saved_window_mode(self) -> None:
        if self.opens_in_fullscreen:
            self.showFullScreen()
        else:
            self.show()

    def set_fullscreen_mode(self, enabled: bool) -> None:
        if not self.isVisible():
            return
        if enabled:
            self.showFullScreen()
        else:
            self.showNormal()

    def confirm_exit(self) -> None:
        answer = QMessageBox.question(
            self,
            "Exit Ledgerly?",
            "Are you sure you want to exit Ledgerly?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.close()

    def _handle_startup_loading_changed(self, loading: bool) -> None:
        if self._startup_setup_complete and not loading:
            self._mark_startup_ready()

    def _mark_startup_ready(self) -> None:
        if self._startup_ready:
            return
        self._startup_ready = True
        self.startup_ready.emit()

    def load_users(self, current_user_id: str | None = None):
        if current_user_id is not None:
            self.session.current_user_id = current_user_id
            set_last_user_id(current_user_id)
        current_key = f"user:{current_user_id}" if current_user_id else None
        self.load_profiles(current_key)

    def load_profiles(
        self,
        current_profile_key: str | None = None,
        *,
        navigate_to_dashboard: bool = True,
    ) -> None:
        profiles = get_profiles()
        user_profiles = [item for item in profiles if item["type"] == "user"]
        user_ids = {str(item["id"]) for item in user_profiles}
        if self.session.current_user_id not in user_ids:
            self.session.current_user_id = (
                str(user_profiles[0]["id"]) if user_profiles else None
            )
        set_last_user_id(self.session.current_user_id)
        profiles = get_profiles(current_user_id=self.session.current_user_id)
        preferred_key = current_profile_key or self.session.active_profile_key
        profile_keys = {item["key"] for item in profiles}
        if preferred_key not in profile_keys and self.session.current_user_id is not None:
            preferred_key = f"user:{self.session.current_user_id}"
        self.sidebar.set_profiles(profiles, preferred_key)
        self.session.set_active_profile(self.sidebar.current_profile_key)
        self._apply_profile(self.sidebar.current_profile_key)
        current_user_profile = next((
            item for item in profiles
            if item["type"] == "user"
            and str(item["id"]) == self.session.current_user_id
        ), None)
        self.settings_page.set_current_user(
            self.session.current_user_id,
            current_user_profile["name"] if current_user_profile else None,
        )
        self.user_management_page.set_current_user(
            self._management_user_id(profiles, self.sidebar.current_profile_key)
        )
        if hasattr(self.categories_page, "set_current_user"):
            self.categories_page.set_current_user(self.session.current_user_id)

        if profiles:
            self.sidebar.show()
            if navigate_to_dashboard:
                self.pages.setCurrentWidget(self.dashboard_page)
                self.sidebar.set_current_page(DASHBOARD_PAGE)
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

    def show_add_profile_from_management(self) -> None:
        dialog = AddUserDialog(self)
        dialog.user_created.connect(self.handle_management_profile_created)
        dialog.group_created.connect(self.handle_group_created)
        self._run_user_dialog(dialog)

    def show_switch_user(self):
        current = next((
            item for item in self.sidebar.profiles
            if item.get("type") == "user"
            and str(item["id"]) == self.session.current_user_id
        ), None)
        dialog = SwitchUserDialog(
            self.sidebar.profiles,
            self.sidebar.current_profile_key,
            self,
            can_manage_groups=bool(current and current.get("is_admin")),
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
        dialog = AddUserDialog(
            self,
            group_id=group_id,
            actor_user_id=self.session.current_user_id,
        )
        dialog.group_updated.connect(self.handle_group_updated)
        self._run_user_dialog(dialog)

    def show_edit_group_from_management(self, group_id: int) -> None:
        dialog = AddUserDialog(
            self,
            group_id=group_id,
            actor_user_id=self.user_management_page.current_user_id,
        )
        dialog.group_updated.connect(
            lambda _group_id: self.refresh_profiles()
        )
        self._run_user_dialog(dialog)

    def show_edit_user(self, user_id: str) -> None:
        dialog = AddUserDialog(
            self,
            user_id=user_id,
            actor_user_id=self.user_management_page.current_user_id,
        )
        dialog.user_updated.connect(lambda _user_id: self.refresh_profiles())
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

    def handle_management_profile_created(self, _profile_id) -> None:
        self.refresh_profiles()

    def handle_user_changed(self, user_id: str):
        # Compatibility path for older callers that still select raw users.
        self.session.current_user_id = user_id
        set_last_user_id(user_id)
        self.session.set_active_profile(f"user:{user_id}")
        self.user_management_page.set_current_user(user_id)
        self._apply_profile(f"user:{user_id}")
        self.pages.setCurrentWidget(self.dashboard_page)
        self.sidebar.set_current_page(DASHBOARD_PAGE)

    def handle_profile_changed(self, profile_key: str) -> None:
        context = ProfileContext.from_key(profile_key)
        self.session.set_active_profile(profile_key)
        if context.user_id is not None:
            self.session.current_user_id = context.user_id
            set_last_user_id(context.user_id)
            selected = next(
                (
                    profile for profile in self.sidebar.profiles
                    if profile["key"] == profile_key
                ),
                None,
            )
            self.settings_page.set_current_user(
                context.user_id,
                selected["name"] if selected is not None else None,
            )
            if hasattr(self.categories_page, "set_current_user"):
                self.categories_page.set_current_user(context.user_id)
        self.user_management_page.set_current_user(
            self._management_user_id(self.sidebar.profiles, profile_key)
        )
        self._apply_profile(profile_key)
        self.pages.setCurrentWidget(self.dashboard_page)
        self.sidebar.set_current_page(DASHBOARD_PAGE)

    def refresh_profiles(self) -> None:
        self.load_profiles(
            self.session.active_profile_key,
            navigate_to_dashboard=False,
        )

    @staticmethod
    def _management_user_id(
        profiles: list[dict],
        profile_key: str | None,
    ) -> str | None:
        """Resolve the user whose role controls the management page."""
        selected = next(
            (profile for profile in profiles if profile["key"] == profile_key),
            None,
        )
        if selected is not None and selected["type"] == "user":
            return str(selected["id"])
        first_admin = next(
            (
                profile for profile in profiles
                if profile["type"] == "user" and profile.get("is_admin")
            ),
            None,
        )
        return str(first_admin["id"]) if first_admin is not None else None

    def handle_profile_deleted(self, user_id: str) -> None:
        if self.session.current_user_id == user_id:
            self.session.current_user_id = None
            self.session.active_profile = None
        self.load_profiles()

    def _apply_profile(self, profile_key: str | None) -> None:
        preserved_month = self._selected_month
        if profile_key is None:
            user_id = group_id = None
        else:
            context = ProfileContext.from_key(profile_key)
            user_id, group_id = context.user_id, context.group_id
        self.dashboard_page.set_profile(user_id=user_id, group_id=group_id)
        self.transactions_page.set_profile(user_id=user_id, group_id=group_id)
        self.investments_page.set_profile(user_id=user_id, group_id=group_id)
        self.accounts_page.set_profile(user_id=user_id, group_id=group_id)
        self.goals_page.set_profile(user_id=user_id, group_id=group_id)

        selected_month = preserved_month or self.dashboard_page.selected_month
        self._set_selected_month(selected_month)
        if preserved_month is not None:
            # Dashboard set_profile() resets its selector before loading. Load
            # it once more after restoring the app-wide month.
            self.dashboard_page.reload()

    def _handle_period_selection_changed(
        self,
        _period: str,
        selected_month: tuple[int, int],
    ) -> None:
        self._set_selected_month(selected_month)

    def _handle_goal_month_changed(self, year: int, month: int) -> None:
        self._set_selected_month((year, month))

    def _set_selected_month(self, selected_month: tuple[int, int]) -> None:
        """Apply one month/year selection to every monthly page."""
        if self._syncing_month_selection:
            return

        self._syncing_month_selection = True
        try:
            self._selected_month = selected_month
            self.dashboard_page.period_selector.set_selected_month(
                selected_month,
                emit=False,
            )
            self.transactions_page.statements_table.set_selected_month(
                selected_month,
                reload=True,
            )
            self.investments_page.period_selector.set_selected_month(
                selected_month,
                emit=False,
            )
            self.goals_page.month_navigator.set_period(
                *selected_month,
                emit=False,
            )
        finally:
            self._syncing_month_selection = False

    def handle_data_reset(self) -> None:
        self.dashboard_page.reload()
        self.transactions_page.reload()
        self.accounts_page.reload()
        self.investments_page.reload()
        self.goals_page.reload()

    def change_page(self, page_name: str):

        pages = {
            DASHBOARD_PAGE: self.dashboard_page,
            TRANSACTIONS_PAGE: self.transactions_page,
            ACCOUNTS_PAGE: self.accounts_page,
            INVESTMENTS_PAGE: self.investments_page,
            CATEGORIES_PAGE: self.categories_page,
            SETTINGS_PAGE: self.settings_page,
        }
        if hasattr(self, "goals_page"):
            pages[GOALS_PAGE] = self.goals_page
        if hasattr(self, "user_management_page"):
            pages[USER_MANAGEMENT_PAGE] = self.user_management_page

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
            if hasattr(self, "goals_page") and page is self.goals_page:
                self.goals_page.reload()
            if (
                hasattr(self, "user_management_page")
                and page is self.user_management_page
            ):
                self.user_management_page.reload()

    def _show_goals_from_dashboard(self) -> None:
        self.sidebar.set_current_page(GOALS_PAGE)
        self.change_page(GOALS_PAGE)
