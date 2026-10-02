from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import awesome_icon, set_button_icon

from utils.constants import (
    ACCOUNTS_LABEL,
    ACCOUNTS_PAGE,
    CATEGORIES_LABEL,
    CATEGORIES_PAGE,
    DASHBOARD_LABEL,
    DASHBOARD_PAGE,
    INVESTMENTS_LABEL,
    INVESTMENTS_PAGE,
    SETTINGS_LABEL,
    SETTINGS_PAGE,
    TRANSACTIONS_LABEL,
    TRANSACTIONS_PAGE,
)


class Sidebar(QFrame):
    page_changed = Signal(str)
    user_changed = Signal(str)
    create_user_clicked = Signal()
    collapsed_changed = Signal(bool)

    EXPANDED_WIDTH = 238
    COLLAPSED_WIDTH = 72

    def __init__(self):
        super().__init__()

        self.is_collapsed = False
        self.setObjectName("sidebar")
        self.setFixedWidth(self.EXPANDED_WIDTH)

        self.sidebar_layout = QVBoxLayout(self)
        self.sidebar_layout.setContentsMargins(12, 18, 12, 18)
        self.sidebar_layout.setSpacing(7)

        self.brand = QWidget()
        self.brand.setObjectName("brand")
        self.brand_layout = QHBoxLayout(self.brand)
        self.brand_layout.setContentsMargins(8, 0, 8, 14)
        self.brand_layout.setSpacing(10)
        self.brand_icon = QLabel()
        self.brand_icon.setPixmap(
            awesome_icon("fa6s.wallet", color="#55a8ff").pixmap(20, 20)
        )
        self.brand_icon.setFixedSize(20, 20)
        self.brand_title = QLabel("Finance")
        self.brand_title.setObjectName("brandTitle")

        self.collapse_button = QToolButton()
        self.collapse_button.setObjectName("sidebarToggle")
        self.collapse_button.setFixedSize(28, 28)
        self.collapse_button.setToolTip("Collapse sidebar")
        self.collapse_button.setAccessibleName("Collapse sidebar")
        set_button_icon(
            self.collapse_button,
            "fa6s.angles-left",
            color="#aeb4bc",
            active_color="#ffffff",
            size=14,
        )
        self.collapse_button.clicked.connect(self.toggle_collapsed)

        self.brand_layout.addWidget(self.brand_icon)
        self.brand_layout.addWidget(self.brand_title)
        self.brand_layout.addStretch()
        self.brand_layout.addWidget(self.collapse_button)
        self.sidebar_layout.addWidget(self.brand)

        self.users = []
        self.current_user_id = None
        self.showing_all_users = False

        self.current_user_button = QToolButton()
        self.current_user_button.setObjectName("currentUserButton")
        self.current_user_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.current_user_button.setFixedWidth(
            self.EXPANDED_WIDTH - 24
        )
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

        self.create_user_button = QPushButton("Create User")
        self.create_user_button.setObjectName("createUserButton")
        self.create_user_button.setToolTip("Create User")
        self.create_user_button.setAccessibleName("Create User")
        set_button_icon(
            self.create_user_button,
            "fa6s.plus",
            color="#aeb4bc",
            active_color="#ffffff",
            size=16,
        )
        self.create_user_button.clicked.connect(
            self.create_user_clicked.emit
        )

        self.sidebar_layout.addWidget(self.current_user_button)
        self.sidebar_layout.addWidget(self.user_dropdown)
        self.sidebar_layout.addWidget(self.create_user_button)

        self.dashboard_button = self.create_button(
            DASHBOARD_LABEL,
            DASHBOARD_PAGE,
            "fa6s.house",
        )

        self.transactions_button = self.create_button(
            TRANSACTIONS_LABEL,
            TRANSACTIONS_PAGE,
            "fa6s.right-left",
        )

        self.investments_button = self.create_button(
            INVESTMENTS_LABEL,
            INVESTMENTS_PAGE,
            "fa6s.arrow-trend-up",
        )

        self.accounts_button = self.create_button(
            ACCOUNTS_LABEL,
            ACCOUNTS_PAGE,
            "fa6s.wallet",
        )

        self.categories_button = self.create_button(
            CATEGORIES_LABEL,
            CATEGORIES_PAGE,
            "fa6s.tags",
        )

        self.settings_button = self.create_button(
            SETTINGS_LABEL,
            SETTINGS_PAGE,
            "fa6s.gear",
        )

        self.navigation_buttons = (
            self.dashboard_button,
            self.transactions_button,
            self.investments_button,
            self.accounts_button,
            self.categories_button,
            self.settings_button,
        )

        self.sidebar_layout.addSpacing(22)

        self.sidebar_layout.addWidget(self.dashboard_button)
        self.sidebar_layout.addWidget(self.transactions_button)
        self.sidebar_layout.addWidget(self.investments_button)
        self.sidebar_layout.addWidget(self.accounts_button)
        self.sidebar_layout.addWidget(self.categories_button)


        # Pushes settings to bottom
        self.sidebar_layout.addStretch()

        self.sidebar_layout.addWidget(self.settings_button)

        self.setStyleSheet("""
            QFrame#sidebar {
                background-color: #101318;
                border: none;
                border-right: 1px solid #2b3037;
            }

            QLabel#brandTitle {
                color: #f2f4f7;
                font-size: 16px;
                font-weight: 650;
            }

            QToolButton#sidebarToggle {
                background-color: transparent;
                color: #bfc4ca;
                border: none;
                border-radius: 7px;
                padding: 4px;
            }

            QToolButton#sidebarToggle:hover {
                background-color: #252a31;
            }

            QToolButton#currentUserButton {
                background-color: #1b1f24;
                color: #f2f4f7;
                border: 1px solid #343a42;
                border-radius: 10px;
                min-height: 36px;
                padding: 10px 12px;
                font-size: 14px;
                font-weight: 600;
                text-align: left;
            }

            QToolButton#currentUserButton:hover {
                background-color: #252a31;
                border-color: #4a515a;
            }

            QFrame#userDropdown {
                background-color: #181b20;
                border: 1px solid #333941;
                border-radius: 8px;
            }

            QPushButton#userOptionButton,
            QPushButton#showMoreButton,
            QPushButton#createUserButton {
                padding: 9px 10px;
            }

            QPushButton#createUserButton {
                color: #cdd1d6;
                margin-top: 2px;
            }

            QPushButton#navButton,
            QPushButton#createUserButton,
            QPushButton#userOptionButton,
            QPushButton#showMoreButton {
                background-color: transparent;
                color: #bfc4ca;
                border: none;
                border-radius: 9px;
                text-align: left;
                padding: 11px 14px;
                font-size: 14px;
            }

            QPushButton#navButton:hover,
            QPushButton#createUserButton:hover,
            QPushButton#userOptionButton:hover,
            QPushButton#showMoreButton:hover {
                background-color: #1d2127;
                color: #ffffff;
            }

            QPushButton#navButton:checked {
                background-color: #1c2d4f;
                border-left: 3px solid #2587ff;
                color: #ffffff;
                font-weight: 600;
            }
        """)

        self.dashboard_button.setChecked(True)

    def toggle_collapsed(self):
        self.set_collapsed(not self.is_collapsed)

    def set_collapsed(self, collapsed: bool):
        """Switch between the full sidebar and its icon-only form."""
        collapsed = bool(collapsed)
        if collapsed == self.is_collapsed:
            return

        self.is_collapsed = collapsed
        self.user_dropdown.hide()
        self.setFixedWidth(
            self.COLLAPSED_WIDTH if collapsed else self.EXPANDED_WIDTH
        )
        side_margin = 8 if collapsed else 12
        self.sidebar_layout.setContentsMargins(
            side_margin,
            18,
            side_margin,
            18,
        )
        self.brand_layout.setContentsMargins(
            0 if collapsed else 8,
            0,
            0 if collapsed else 8,
            14,
        )
        self.brand_layout.setSpacing(4 if collapsed else 10)
        self.brand_title.setVisible(not collapsed)

        toggle_label = "Expand sidebar" if collapsed else "Collapse sidebar"
        self.collapse_button.setToolTip(toggle_label)
        self.collapse_button.setAccessibleName(toggle_label)
        set_button_icon(
            self.collapse_button,
            "fa6s.angles-right" if collapsed else "fa6s.angles-left",
            color="#aeb4bc",
            active_color="#ffffff",
            size=14,
        )

        for button in self.navigation_buttons:
            label = button.property("sidebarLabel")
            button.setText("" if collapsed else label)
            button.setMaximumWidth(48 if collapsed else 16777215)

        self.create_user_button.setText("" if collapsed else "Create User")
        self.create_user_button.setMaximumWidth(
            48 if collapsed else 16777215
        )
        self.current_user_button.setFixedWidth(
            48 if collapsed else self.EXPANDED_WIDTH - 24
        )
        self.current_user_button.setToolButtonStyle(
            Qt.ToolButtonIconOnly
            if collapsed
            else Qt.ToolButtonTextBesideIcon
        )
        self.refresh_user_selector()
        self.collapsed_changed.emit(collapsed)

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

        user_name = current_user["name"]
        self.current_user_button.setText(
            ""
            if self.is_collapsed
            else f"{user_name}  \N{BLACK DOWN-POINTING SMALL TRIANGLE}"
        )
        self.current_user_button.setToolTip(f"Current user: {user_name}")
        self.current_user_button.setAccessibleName(
            f"Current user: {user_name}"
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
        if self.is_collapsed:
            self.set_collapsed(False)
            self.user_dropdown.show()
            return

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

    def create_button(self, text: str, page_name: str, icon_name: str):
        button = QPushButton(text)
        button.setObjectName("navButton")
        button.setProperty("sidebarLabel", text)
        button.setToolTip(text)
        button.setAccessibleName(text)
        button.setCheckable(True)
        set_button_icon(
            button,
            icon_name,
            color="#b2b8c1",
            active_color="#4aa3ff",
            size=20,
        )

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
            self.investments_button,
            self.categories_button,
            self.settings_button,
        ]

        for button in buttons:
            button.setChecked(button is selected_button)

        self.page_changed.emit(page_name)
