from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QStackedWidget,
)

from database.db import get_users
from ui.accounts import AccountsPage
from ui.categories import CategoriesPage
from ui.sidebar import Sidebar

from ui.welcome import WelcomePage
from ui.add_user import AddUserPage
from ui.dashboard import DashboardPage
from ui.transactions import TransactionsPage
from ui.settings import SettingsPage
from utils.constants import (
    ACCOUNTS_PAGE,
    CATEGORIES_PAGE,
    DASHBOARD_PAGE,
    SETTINGS_PAGE,
    TRANSACTIONS_PAGE,
)


class ShellWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Finance")
        self.resize(1400, 850)

        # -------------------------
        # Root widget
        # -------------------------

        root = QWidget()
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

        self.welcome_page = WelcomePage()
        self.add_user_page = AddUserPage()

        self.dashboard_page = DashboardPage()
        self.transactions_page = TransactionsPage()
        self.settings_page = SettingsPage()
        self.accounts_page = AccountsPage()
        self.categories_page = CategoriesPage()

        self.pages.addWidget(
            self.welcome_page
        )

        self.pages.addWidget(
            self.add_user_page
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

        self.sidebar.user_changed.connect(
            self.handle_user_changed
        )

        self.welcome_page.add_user_clicked.connect(
            self.show_add_user
        )

        self.add_user_page.user_created.connect(
            self.handle_user_created
        )

        self.settings_page.data_reset.connect(self.handle_data_reset)

        # -------------------------
        # Initial page
        # -------------------------

        self.load_users()

    def load_users(self, current_user_id: str | None = None):
        users = get_users()
        self.sidebar.set_users(users, current_user_id)
        self.dashboard_page.set_user_id(self.sidebar.current_user_id)
        self.transactions_page.set_user_id(self.sidebar.current_user_id)

        if users:
            self.sidebar.show()
            self.pages.setCurrentWidget(self.dashboard_page)
        else:
            self.sidebar.hide()
            self.pages.setCurrentWidget(self.welcome_page)

    def show_add_user(self):
        self.sidebar.user_dropdown.hide()
        self.pages.setCurrentWidget(
            self.add_user_page
        )

    def handle_user_created(self, user_id: str):
        self.load_users(user_id)

    def handle_user_changed(self, user_id: str):
        self.dashboard_page.set_user_id(user_id)
        self.transactions_page.set_user_id(user_id)
        self.pages.setCurrentWidget(self.dashboard_page)

    def handle_data_reset(self) -> None:
        self.dashboard_page.reload()
        self.transactions_page.reload()
        self.accounts_page.reload()

    def change_page(self, page_name: str):

        pages = {
            DASHBOARD_PAGE: self.dashboard_page,
            TRANSACTIONS_PAGE: self.transactions_page,
            ACCOUNTS_PAGE: self.accounts_page,
            CATEGORIES_PAGE: self.categories_page,
            SETTINGS_PAGE: self.settings_page,
        }

        page = pages.get(page_name)

        if page is not None:
            if page is self.transactions_page:
                self.transactions_page.reload()
            if page is self.dashboard_page:
                self.dashboard_page.reload()
            if page is self.accounts_page:
                self.accounts_page.reload()
            if page is self.categories_page:
                self.categories_page.reload()
            self.pages.setCurrentWidget(page)
