from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QStackedWidget,
)

from database.db import get_users
from ui.sidebar import Sidebar

from ui.welcome import WelcomePage
from ui.add_user import AddUserPage
from ui.dashboard import DashboardPage
from ui.transactions import TransactionsPage
from ui.import_data import ImportPage
from ui.settings import SettingsPage


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
        self.import_page = ImportPage()
        self.settings_page = SettingsPage()

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
            self.import_page
        )

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

        # -------------------------
        # Initial page
        # -------------------------

        self.load_users()

    def load_users(self, current_user_id: str | None = None):
        users = get_users()
        self.sidebar.set_users(users, current_user_id)

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
        self.pages.setCurrentWidget(self.dashboard_page)

    def change_page(self, page_name: str):

        pages = {
            "dashboard": self.dashboard_page,
            "transactions": self.transactions_page,
            "import": self.import_page,
            "settings": self.settings_page,
        }

        page = pages.get(page_name)

        if page is not None:
            self.pages.setCurrentWidget(page)
