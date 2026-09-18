from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
)

from utils.constants import (
    ACCOUNTS_LABEL,
    ACCOUNTS_PAGE,
    CATEGORIES_LABEL,
    CATEGORIES_PAGE,
    DASHBOARD_LABEL,
    DASHBOARD_PAGE,
    SETTINGS_LABEL,
    SETTINGS_PAGE,
    TRANSACTIONS_LABEL,
    TRANSACTIONS_PAGE,
)


class Sidebar(QFrame):
    page_changed = Signal(str)
    user_changed = Signal(str)
    create_user_clicked = Signal()

    def __init__(self):
        super().__init__()

        self.setObjectName("sidebar")
        self.setFixedWidth(220)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(8)

        self.users = []
        self.current_user_id = None
        self.showing_all_users = False

        self.current_user_button = QToolButton()
        self.current_user_button.setObjectName("currentUserButton")
        self.current_user_button.setToolButtonStyle(
            Qt.ToolButtonTextBesideIcon
        )
        self.current_user_button.clicked.connect(
            self.toggle_user_dropdown
        )

        self.user_dropdown = QFrame()
        self.user_dropdown.setObjectName("userDropdown")
        self.user_dropdown_layout = QVBoxLayout(
            self.user_dropdown
        )
        self.user_dropdown_layout.setContentsMargins(0, 4, 0, 4)
        self.user_dropdown_layout.setSpacing(2)
        self.user_dropdown.hide()

        self.create_user_button = QPushButton("+  Create User")
        self.create_user_button.setObjectName("createUserButton")
        self.create_user_button.clicked.connect(
            self.create_user_clicked.emit
        )

        layout.addWidget(self.current_user_button)
        layout.addWidget(self.user_dropdown)
        layout.addWidget(self.create_user_button)

        self.dashboard_button = self.create_button(
            DASHBOARD_LABEL,
            DASHBOARD_PAGE,
        )

        self.transactions_button = self.create_button(
            TRANSACTIONS_LABEL,
            TRANSACTIONS_PAGE,
        )

        self.accounts_button = self.create_button(
            ACCOUNTS_LABEL,
            ACCOUNTS_PAGE,
        )

        self.categories_button = self.create_button(
            CATEGORIES_LABEL,
            CATEGORIES_PAGE,
        )

        self.settings_button = self.create_button(
            SETTINGS_LABEL,
            SETTINGS_PAGE,
        )

        layout.addSpacing(24)

        layout.addWidget(self.dashboard_button)
        layout.addWidget(self.transactions_button)
        layout.addWidget(self.accounts_button)
        layout.addWidget(self.categories_button)


        # Pushes settings to bottom
        layout.addStretch()

        layout.addWidget(self.settings_button)

        self.setStyleSheet("""
            QFrame#sidebar {
                background-color: #171717;
                border: none;
            }

            QToolButton#currentUserButton {
                background-color: #262626;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 10px;
                font-size: 16px;
                font-weight: 700;
                text-align: left;
            }

            QToolButton#currentUserButton:hover {
                background-color: #303030;
            }

            QFrame#userDropdown {
                background-color: #202020;
                border-radius: 8px;
            }

            QPushButton#userOptionButton,
            QPushButton#showMoreButton,
            QPushButton#createUserButton {
                padding: 9px 10px;
            }

            QPushButton#createUserButton {
                color: #d6d6d6;
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

    @staticmethod
    def color_icon(color: str) -> QIcon:
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(1, 1, 14, 14)
        painter.end()

        return QIcon(pixmap)

    def set_users(
        self,
        users: list[dict[str, str]],
        current_user_id: str | None = None,
    ):
        self.users = users

        user_ids = {user["id"] for user in users}
        if current_user_id not in user_ids:
            current_user_id = users[0]["id"] if users else None

        self.current_user_id = current_user_id
        self.showing_all_users = False
        self.user_dropdown.hide()
        self.refresh_user_selector()

    def refresh_user_selector(self):
        current_user = next(
            (
                user
                for user in self.users
                if user["id"] == self.current_user_id
            ),
            None,
        )

        self.current_user_button.setVisible(current_user is not None)
        if current_user is None:
            self.clear_user_dropdown()
            return

        self.current_user_button.setText(
            f'{current_user["name"]}  ▾'
        )
        self.current_user_button.setIcon(
            self.color_icon(current_user["color"])
        )

        self.clear_user_dropdown()
        other_users = [
            user
            for user in self.users
            if user["id"] != self.current_user_id
        ]
        visible_users = (
            other_users
            if self.showing_all_users
            else other_users[:3]
        )

        for user in visible_users:
            button = QPushButton(user["name"])
            button.setObjectName("userOptionButton")
            button.setIcon(self.color_icon(user["color"]))
            button.clicked.connect(
                lambda checked=False, user_id=user["id"]:
                self.select_user(user_id)
            )
            self.user_dropdown_layout.addWidget(button)

        if len(other_users) > 3:
            show_more_button = QPushButton(
                "Show less" if self.showing_all_users else "Show more"
            )
            show_more_button.setObjectName("showMoreButton")
            show_more_button.clicked.connect(self.toggle_show_more)
            self.user_dropdown_layout.addWidget(show_more_button)

    def clear_user_dropdown(self):
        while self.user_dropdown_layout.count():
            item = self.user_dropdown_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def toggle_user_dropdown(self):
        self.user_dropdown.setVisible(
            not self.user_dropdown.isVisible()
        )

    def toggle_show_more(self):
        self.showing_all_users = not self.showing_all_users
        self.refresh_user_selector()
        self.user_dropdown.show()

    def select_user(self, user_id: str):
        self.current_user_id = user_id
        self.showing_all_users = False
        self.user_dropdown.hide()
        self.refresh_user_selector()
        self.user_changed.emit(user_id)

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
            self.accounts_button,
            self.categories_button,
            self.settings_button,
        ]

        for button in buttons:
            button.setChecked(button is selected_button)

        self.page_changed.emit(page_name)
