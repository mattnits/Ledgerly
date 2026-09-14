from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class Sidebar(QFrame):
    page_changed = Signal(str)

    def __init__(self):
        super().__init__()

        self.setObjectName("sidebar")
        self.setFixedWidth(220)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(8)

        title = QLabel("Finance")
        title.setObjectName("sidebarTitle")

        layout.addWidget(title)

        self.dashboard_button = self.create_button(
            "Dashboard",
            "dashboard",
        )

        self.transactions_button = self.create_button(
            "Transactions",
            "transactions",
        )

        self.import_button = self.create_button(
            "Import",
            "import",
        )

        self.settings_button = self.create_button(
            "Settings",
            "settings",
        )

        layout.addSpacing(24)

        layout.addWidget(self.dashboard_button)
        layout.addWidget(self.transactions_button)
        layout.addWidget(self.import_button)

        # Pushes settings to bottom
        layout.addStretch()

        layout.addWidget(self.settings_button)

        self.setStyleSheet("""
            QFrame#sidebar {
                background-color: #171717;
                border: none;
            }

            QLabel#sidebarTitle {
                color: white;
                font-size: 22px;
                font-weight: 700;
                padding: 0 8px;
            }

            QPushButton {
                background-color: transparent;
                color: #b5b5b5;

                border: none;
                border-radius: 8px;

                text-align: left;

                padding: 12px 14px;

                font-size: 14px;
            }

            QPushButton:hover {
                background-color: #262626;
                color: white;
            }

            QPushButton:checked {
                background-color: #303030;
                color: white;
                font-weight: 600;
            }
        """)

        self.dashboard_button.setChecked(True)

    def create_button(self, text: str, page_name: str):
        button = QPushButton(text)

        button.setCheckable(True)

        button.clicked.connect(
            lambda: self.handle_navigation(
                button,
                page_name,
            )
        )

        return button

    def handle_navigation(
        self,
        selected_button: QPushButton,
        page_name: str,
    ):
        buttons = [
            self.dashboard_button,
            self.transactions_button,
            self.import_button,
            self.settings_button,
        ]

        for button in buttons:
            button.setChecked(button is selected_button)

        self.page_changed.emit(page_name)