from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
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

from ui.theme import awesome_icon, contrasting_text, set_button_icon
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


class ElidedLabel(QLabel):
    """A label that only exposes a tooltip when its text is clipped."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API spelling
        self._full_text = text
        self._refresh_text()

    def fullText(self) -> str:  # noqa: N802 - Qt API spelling
        return self._full_text

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API spelling
        super().resizeEvent(event)
        self._refresh_text()

    def _refresh_text(self) -> None:
        width = max(0, self.contentsRect().width())
        metrics = self.fontMetrics()
        clipped = metrics.horizontalAdvance(self._full_text) > width
        super().setText(
            metrics.elidedText(
                self._full_text,
                Qt.TextElideMode.ElideRight,
                width,
            )
        )
        self.setToolTip(self._full_text if clipped else "")


def avatar_icon(name: str, color: str, size: int = 36) -> QIcon:
    """Render a circular profile avatar using the user's first initial."""
    background = QColor(color)
    if not background.isValid():
        background = QColor("#398cff")

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(background)
    painter.drawEllipse(1, 1, size - 2, size - 2)

    font = painter.font()
    font.setPixelSize(max(13, int(size * 0.46)))
    font.setWeight(QFont.Weight.Medium)
    painter.setFont(font)
    painter.setPen(QColor(contrasting_text(background.name())))
    painter.drawText(
        pixmap.rect(),
        Qt.AlignmentFlag.AlignCenter,
        (name.strip()[:1] or "?").upper(),
    )
    painter.end()
    return QIcon(pixmap)


class Sidebar(QFrame):
    page_changed = Signal(str)
    user_changed = Signal(str)
    profile_changed = Signal(str)
    create_user_clicked = Signal()
    switch_user_clicked = Signal()
    collapsed_changed = Signal(bool)

    EXPANDED_WIDTH = 260
    COLLAPSED_WIDTH = 72

    def __init__(self):
        super().__init__()
        self.is_collapsed = False
        self.users: list[dict[str, str]] = []
        self.profiles: list[dict] = []
        self.current_user_id: str | None = None
        self.current_profile_key: str | None = None
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

        self.user_bar = QFrame()
        self.user_bar.setObjectName("userBar")
        self.user_bar_layout = QHBoxLayout(self.user_bar)
        self.user_bar_layout.setContentsMargins(6, 7, 6, 7)
        self.user_bar_layout.setSpacing(6)
        self.current_user_panel = QWidget()
        self.current_user_panel.setObjectName("currentUserPanel")
        self.current_user_layout = QHBoxLayout(self.current_user_panel)
        self.current_user_layout.setContentsMargins(0, 0, 0, 0)
        self.current_user_layout.setSpacing(8)
        self.current_user_avatar = QLabel()
        self.current_user_avatar.setObjectName("currentUserAvatar")
        self.current_user_avatar.setFixedSize(34, 34)
        self.current_user_name = ElidedLabel()
        self.current_user_name.setObjectName("currentUserName")
        self.current_user_name.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.current_user_layout.addWidget(self.current_user_avatar)
        self.current_user_layout.addWidget(self.current_user_name, 1)
        self.user_bar_layout.addWidget(self.current_user_panel, 1)

        self.add_user_button = self._user_action_button(
            "addUserButton", "Add user or group", "fa6s.user-plus"
        )
        self.add_user_button.clicked.connect(self.create_user_clicked.emit)
        self.switch_user_button = self._user_action_button(
            "switchUserButton", "Switch profile", "fa6s.right-left"
        )
        self.switch_user_button.clicked.connect(self.switch_user_clicked.emit)
        self.user_bar_layout.addWidget(self.add_user_button)
        self.user_bar_layout.addWidget(self.switch_user_button)
        self.sidebar_layout.addWidget(self.user_bar)

        self.dashboard_button = self.create_button(
            DASHBOARD_LABEL, DASHBOARD_PAGE, "fa6s.house"
        )
        self.transactions_button = self.create_button(
            TRANSACTIONS_LABEL, TRANSACTIONS_PAGE, "fa6s.right-left"
        )
        self.investments_button = self.create_button(
            INVESTMENTS_LABEL, INVESTMENTS_PAGE, "fa6s.arrow-trend-up"
        )
        self.accounts_button = self.create_button(
            ACCOUNTS_LABEL, ACCOUNTS_PAGE, "fa6s.wallet"
        )
        self.categories_button = self.create_button(
            CATEGORIES_LABEL, CATEGORIES_PAGE, "fa6s.tags"
        )
        self.settings_button = self.create_button(
            SETTINGS_LABEL, SETTINGS_PAGE, "fa6s.gear"
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
            QToolButton#sidebarToggle,
            QToolButton#addUserButton,
            QToolButton#switchUserButton {
                background-color: transparent;
                color: #bfc4ca;
                border: none;
                border-radius: 8px;
                padding: 0;
            }
            QToolButton#sidebarToggle:hover,
            QToolButton#addUserButton:hover,
            QToolButton#switchUserButton:hover {
                background-color: #252a31;
            }
            QFrame#userBar {
                background-color: transparent;
                border-top: 1px solid #2b3037;
                border-bottom: 1px solid #2b3037;
            }
            QLabel#currentUserName {
                color: #f2f4f7;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton#navButton {
                background-color: transparent;
                color: #bfc4ca;
                border: none;
                border-radius: 9px;
                text-align: left;
                padding: 11px 14px;
                font-size: 14px;
            }
            QPushButton#navButton:hover {
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

    def _user_action_button(
        self, object_name: str, tooltip: str, icon_name: str
    ) -> QToolButton:
        button = QToolButton()
        button.setObjectName(object_name)
        button.setFixedSize(34, 34)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_button_icon(
            button,
            icon_name,
            color="#aeb7c4",
            active_color="#ffffff",
            size=15,
        )
        return button

    def toggle_collapsed(self):
        self.set_collapsed(not self.is_collapsed)

    def set_collapsed(self, collapsed: bool):
        """Switch between the full sidebar and its icon-only form."""
        collapsed = bool(collapsed)
        if collapsed == self.is_collapsed:
            return
        self.is_collapsed = collapsed
        self.setFixedWidth(
            self.COLLAPSED_WIDTH if collapsed else self.EXPANDED_WIDTH
        )
        side_margin = 8 if collapsed else 12
        self.sidebar_layout.setContentsMargins(side_margin, 18, side_margin, 18)
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
        self.current_user_name.setVisible(not collapsed)
        self.add_user_button.setVisible(not collapsed)
        self.switch_user_button.setVisible(not collapsed)
        self.user_bar_layout.setContentsMargins(
            7 if collapsed else 6, 7, 7 if collapsed else 6, 7
        )
        self.refresh_user_display()
        self.collapsed_changed.emit(collapsed)

    @staticmethod
    def color_icon(color: str) -> QIcon:
        """Backward-compatible colour marker used by older callers."""
        return avatar_icon("", color, 16)

    def set_users(
        self,
        users: list[dict[str, str]],
        current_user_id: str | None = None,
    ):
        self.users = users
        self.profiles = [
            {
                **user,
                "key": str(user["id"]),
                "type": "user",
                "subtitle": "Personal",
            }
            for user in users
        ]
        user_ids = {user["id"] for user in users}
        if current_user_id not in user_ids:
            current_user_id = users[0]["id"] if users else None
        self.current_user_id = current_user_id
        self.current_profile_key = current_user_id
        self.refresh_user_display()

    def set_profiles(
        self,
        profiles: list[dict],
        current_profile_key: str | None = None,
    ) -> None:
        self.profiles = profiles
        self.users = [profile for profile in profiles if profile["type"] == "user"]
        keys = {profile["key"] for profile in profiles}
        if current_profile_key not in keys:
            current_profile_key = profiles[0]["key"] if profiles else None
        self.current_profile_key = current_profile_key
        current = self.current_profile
        self.current_user_id = (
            str(current["id"])
            if current is not None and current["type"] == "user"
            else None
        )
        self.refresh_user_display()

    @property
    def current_profile(self) -> dict | None:
        return next(
            (
                profile for profile in self.profiles
                if profile["key"] == self.current_profile_key
            ),
            None,
        )

    def refresh_user_display(self):
        current_user = self.current_profile
        self.user_bar.setVisible(current_user is not None)
        if current_user is None:
            self.current_user_name.setText("")
            self.current_user_avatar.clear()
            return
        user_name = current_user["name"]
        icon = avatar_icon(user_name, current_user["color"], 34)
        self.current_user_avatar.setPixmap(icon.pixmap(34, 34))
        profile_label = "group" if current_user.get("type") == "group" else "user"
        self.current_user_avatar.setToolTip(f"Current {profile_label}: {user_name}")
        self.current_user_name.setText(user_name)
        self.current_user_name.setAccessibleName(
            f"Current {profile_label}: {user_name}"
        )

    # Kept as a compatibility entry point; it now opens the modal switcher.
    def toggle_user_dropdown(self):
        if self.is_collapsed:
            self.set_collapsed(False)
        self.switch_user_clicked.emit()

    def select_user(self, user_id: str):
        if user_id == self.current_user_id:
            return
        if user_id not in {user["id"] for user in self.users}:
            return
        self.current_user_id = user_id
        self.current_profile_key = user_id
        self.refresh_user_display()
        self.user_changed.emit(user_id)

    def select_profile(self, profile_key: str) -> None:
        if profile_key == self.current_profile_key:
            return
        profile = next(
            (item for item in self.profiles if item["key"] == profile_key),
            None,
        )
        if profile is None:
            return
        self.current_profile_key = profile_key
        self.current_user_id = (
            str(profile["id"]) if profile["type"] == "user" else None
        )
        self.refresh_user_display()
        self.profile_changed.emit(profile_key)

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
        button.clicked.connect(lambda: self.handle_navigation(button, page_name))
        return button

    def handle_navigation(
        self, selected_button: QPushButton, page_name: str
    ):
        for button in self.navigation_buttons:
            button.setChecked(button is selected_button)
        self.page_changed.emit(page_name)
