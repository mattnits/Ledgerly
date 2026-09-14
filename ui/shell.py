from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QStackedWidget,
)

from ui.sidebar import Sidebar

from ui.dashboard import DashboardPage
from ui.transactions import TransactionsPage
from ui.import_data import ImportPage
from ui.settings import SettingsPage


class ShellWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Finance")
        self.resize(1400, 850)

        root = QWidget()
        self.setCentralWidget(root)

        root_layout = QHBoxLayout(root)

        # Important: removes default spacing
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --------------------------------
        # Sidebar
        # --------------------------------

        self.sidebar = Sidebar()

        # --------------------------------
        # Pages
        # --------------------------------

        self.pages = QStackedWidget()

        self.dashboard_page = DashboardPage()
        self.transactions_page = TransactionsPage()
        self.import_page = ImportPage()
        self.settings_page = SettingsPage()

        self.pages.addWidget(self.dashboard_page)
        self.pages.addWidget(self.transactions_page)
        self.pages.addWidget(self.import_page)
        self.pages.addWidget(self.settings_page)

        # --------------------------------
        # Root layout
        # --------------------------------

        root_layout.addWidget(self.sidebar)
        root_layout.addWidget(self.pages, 1)

        # --------------------------------
        # Navigation
        # --------------------------------

        self.sidebar.page_changed.connect(
            self.change_page
        )

    def change_page(self, page_name: str):

        pages = {
            "dashboard": self.dashboard_page,
            "transactions": self.transactions_page,
            "import": self.import_page,
            "settings": self.settings_page,
        }

        page = pages.get(page_name)

        if page:
            self.pages.setCurrentWidget(page)