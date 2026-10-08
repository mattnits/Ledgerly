from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import (
    awesome_icon,
    contrasting_text,
    refresh_button_icon_spacing,
    set_button_icon,
)
from app.utils.constants import (
    ACCOUNTS_LABEL,
    ACCOUNTS_PAGE,
    CATEGORIES_LABEL,
    CATEGORIES_PAGE,
    DASHBOARD_LABEL,
    DASHBOARD_PAGE,
    GOALS_LABEL,
    GOALS_PAGE,
    INVESTMENTS_LABEL,
    INVESTMENTS_PAGE,
    SETTINGS_LABEL,
    SETTINGS_PAGE,
    TRANSACTIONS_LABEL,
    TRANSACTIONS_PAGE,
    USER_MANAGEMENT_LABEL,
    USER_MANAGEMENT_PAGE,
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

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API spelling
        """Keep layouts aware of the full label while still allowing elision."""
        hint = super().sizeHint()
        hint.setWidth(self.fontMetrics().horizontalAdvance(self._full_text))
        return hint

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


def avatar_icon(
    name: str, color: str, size: int = 36, *, profile_type: str = "user"
) -> QIcon:
    """Render a circular user or rounded-square group profile avatar."""
    background = QColor(color)
    if not background.isValid():
        background = QColor("#398cff")

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(background)
    if profile_type == "group":
        radius = max(5, int(size * 0.24))
        painter.drawRoundedRect(1, 1, size - 2, size - 2, radius, radius)
    else:
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


class ProfilePanel(QWidget):
    """Informational while expanded and clickable while the sidebar is collapsed."""

    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._interactive = False
        self.setObjectName("currentUserPanel")
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_interactive(self, interactive: bool) -> None:
        self._interactive = bool(interactive)
        self.setProperty("interactive", self._interactive)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if self._interactive
            else Qt.CursorShape.ArrowCursor
        )
        self.setFocusPolicy(
            Qt.FocusPolicy.StrongFocus
            if self._interactive
            else Qt.FocusPolicy.NoFocus
        )
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API spelling
        if (
            self._interactive
            and event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API spelling
        if self._interactive and event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ProfileMenu(QFrame):
    """Styled, non-modal profile actions used only by the collapsed sidebar."""

    add_user_clicked = Signal()
    change_user_clicked = Signal()
    closed = Signal()

    def __init__(self, profile: dict, parent=None, *, anchor_widget=None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._closed_notified = False
        self._anchor_widget = anchor_widget
        self._app_filter_installed = False
        self.setObjectName("profileMenu")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(238)
        self.setMaximumWidth(320)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        surface = QFrame()
        surface.setObjectName("profileMenuSurface")
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(10, 10, 10, 9)
        layout.setSpacing(5)

        header = QWidget()
        header.setObjectName("profileMenuHeader")
        header.setCursor(Qt.CursorShape.ArrowCursor)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 3, 4, 8)
        header_layout.setSpacing(10)
        avatar = QLabel()
        avatar.setObjectName("profileMenuAvatar")
        avatar.setProperty("profileType", profile.get("type", "user"))
        avatar.setFixedSize(36, 36)
        avatar.setPixmap(avatar_icon(
            profile.get("name", ""),
            profile.get("color", "#398cff"),
            36,
            profile_type=profile.get("type", "user"),
        ).pixmap(36, 36))
        text = QWidget()
        text_layout = QVBoxLayout(text)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        self.name_label = ElidedLabel(str(profile.get("name", "")))
        self.name_label.setObjectName("profileMenuName")
        self.subtitle_label = ElidedLabel(
            str(profile.get("subtitle") or "Personal")
        )
        self.subtitle_label.setObjectName("profileMenuSubtitle")
        text_layout.addWidget(self.name_label)
        text_layout.addWidget(self.subtitle_label)
        header_layout.addWidget(avatar)
        header_layout.addWidget(text, 1)
        if profile.get("type") == "user" and profile.get("is_admin"):
            star = QLabel()
            star.setToolTip("Admin")
            star.setPixmap(awesome_icon("fa6s.star", color="#f4c95d").pixmap(13, 13))
            header_layout.addWidget(star, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(header)

        divider = QFrame()
        divider.setObjectName("profileMenuDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)

        self.add_user_button = self._action_button(
            "Add User", "fa6s.user-plus"
        )
        self.change_user_button = self._action_button(
            "Change User", "fa6s.right-left"
        )
        self.add_user_button.clicked.connect(self._add_user)
        self.change_user_button.clicked.connect(self._change_user)
        layout.addWidget(self.add_user_button)
        layout.addWidget(self.change_user_button)
        outer.addWidget(surface)

        self.setStyleSheet("""
            QFrame#profileMenu { background: transparent; border: none; }
            QFrame#profileMenuSurface {
                background: #171b20;
                border: 1px solid #3a424c;
                border-radius: 11px;
            }
            QWidget#profileMenuHeader { background: transparent; border: none; }
            QLabel#profileMenuName { color: #f2f4f7; font-size: 13px; font-weight: 650; }
            QLabel#profileMenuSubtitle { color: #929ca9; font-size: 10px; }
            QFrame#profileMenuDivider {
                color: #303740;
                background: transparent;
                border: none;
                border-top: 1px solid #303740;
                max-height: 1px;
            }
            QPushButton#profileMenuAction {
                color: #e2e7ed;
                background: transparent;
                border: none;
                border-radius: 7px;
                text-align: left;
                min-height: 22px;
                padding: 7px 9px;
            }
            QPushButton#profileMenuAction:hover { background: #24344f; color: #ffffff; }
            QPushButton#profileMenuAction:pressed { background: #1c2c45; }
        """)

    @staticmethod
    def _action_button(text: str, icon_name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("profileMenuAction")
        button.setAccessibleName(text)
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_button_icon(
            button,
            icon_name,
            color="#b9c6d5",
            active_color="#ffffff",
            size=15,
        )
        return button

    def _add_user(self) -> None:
        self.close()
        self.add_user_clicked.emit()

    def _change_user(self) -> None:
        self.close()
        self.change_user_clicked.emit()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API spelling
        super().showEvent(event)
        app = QApplication.instance()
        if app is not None and not self._app_filter_installed:
            app.installEventFilter(self)
            self._app_filter_installed = True

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API spelling
        app = QApplication.instance()
        if app is not None and self._app_filter_installed:
            app.removeEventFilter(self)
            self._app_filter_installed = False
        super().hideEvent(event)
        if not self._closed_notified:
            self._closed_notified = True
            self.closed.emit()

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.close()
            return True
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(watched, QWidget):
            inside_menu = watched is self or self.isAncestorOf(watched)
            anchor = self._anchor_widget
            inside_anchor = anchor is not None and (
                watched is anchor or anchor.isAncestorOf(watched)
            )
            if not inside_menu and not inside_anchor:
                self.close()
                return False
        return super().eventFilter(watched, event)


class Sidebar(QFrame):
    page_changed = Signal(str)
    user_changed = Signal(str)
    profile_changed = Signal(str)
    create_user_clicked = Signal()
    switch_user_clicked = Signal()
    exit_requested = Signal()
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
        self.profile_menu: ProfileMenu | None = None
        self.setObjectName("sidebar")
        self.setFixedWidth(self.EXPANDED_WIDTH)

        self.sidebar_layout = QVBoxLayout(self)
        self.sidebar_layout.setContentsMargins(12, 18, 12, 18)
        self.sidebar_layout.setSpacing(7)

        self.brand = QWidget()
        self.brand.setObjectName("brand")
        self.brand_layout = QHBoxLayout(self.brand)
        self.brand_layout.setContentsMargins(8, 0, 8, 14)
        self.brand_layout.setSpacing(8)
        self.brand_icon = QLabel()
        self.brand_icon.setPixmap(
            awesome_icon("fa6s.wallet", color="#55a8ff").pixmap(20, 20)
        )
        self.brand_icon.setFixedSize(20, 20)
        self.brand_title = QLabel("Ledgerly")
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
        # The larger top inset raises the divider while keeping the profile row
        # visually centered between that divider and the bottom of the sidebar.
        self.user_bar_layout.setContentsMargins(6, 24, 6, 7)
        self.user_bar_layout.setSpacing(8)
        self.current_user_panel = ProfilePanel()
        self.current_user_layout = QHBoxLayout(self.current_user_panel)
        self.current_user_layout.setContentsMargins(0, 0, 0, 0)
        self.current_user_layout.setSpacing(8)
        self.current_user_avatar = QLabel()
        self.current_user_avatar.setObjectName("currentUserAvatar")
        self.current_user_avatar.setFixedSize(34, 34)
        self.current_user_avatar.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.current_user_text = QWidget()
        self.current_user_text.setObjectName("currentUserText")
        self.current_user_text_layout = QVBoxLayout(self.current_user_text)
        self.current_user_text_layout.setContentsMargins(0, 0, 0, 0)
        self.current_user_text_layout.setSpacing(1)
        self.current_user_name = ElidedLabel()
        self.current_user_name.setObjectName("currentUserName")
        self.current_user_name.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.current_user_subtitle = ElidedLabel()
        self.current_user_subtitle.setObjectName("currentUserSubtitle")
        self.current_user_subtitle.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.current_user_text_layout.addWidget(self.current_user_name)
        self.current_user_text_layout.addWidget(self.current_user_subtitle)
        self.current_user_layout.addWidget(self.current_user_avatar)
        self.current_user_layout.addWidget(self.current_user_text, 1)
        self.user_bar_layout.addWidget(self.current_user_panel, 1)
        self.current_user_panel.clicked.connect(self.toggle_profile_menu)

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
        self.goals_button = self.create_button(
            GOALS_LABEL, GOALS_PAGE, "fa6s.bullseye"
        )
        self.user_management_button = self.create_button(
            USER_MANAGEMENT_LABEL, USER_MANAGEMENT_PAGE, "fa6s.users-gear"
        )
        self.settings_button = self.create_button(
            SETTINGS_LABEL, SETTINGS_PAGE, "fa6s.gear"
        )
        self.exit_button = QPushButton("Exit")
        self.exit_button.setObjectName("sidebarExitButton")
        self.exit_button.setProperty("sidebarLabel", "Exit")
        self.exit_button.setToolTip("Exit Ledgerly")
        self.exit_button.setAccessibleName("Exit Ledgerly")
        set_button_icon(
            self.exit_button,
            "fa6s.right-from-bracket",
            color="#b2b8c1",
            active_color="#ff8a8a",
            size=20,
        )
        self.exit_button.clicked.connect(self.exit_requested.emit)
        self.navigation_buttons = (
            self.dashboard_button,
            self.transactions_button,
            self.investments_button,
            self.accounts_button,
            self.categories_button,
            self.goals_button,
            self.user_management_button,
            self.settings_button,
        )
        self.management_divider = QFrame()
        self.management_divider.setObjectName("sidebarDivider")
        self.management_divider.setFrameShape(QFrame.Shape.HLine)
        self.management_divider.setFixedHeight(17)
        self.sidebar_layout.addSpacing(22)
        self.sidebar_layout.addWidget(self.dashboard_button)
        self.sidebar_layout.addWidget(self.transactions_button)
        self.sidebar_layout.addWidget(self.investments_button)
        self.sidebar_layout.addWidget(self.accounts_button)
        self.sidebar_layout.addWidget(self.categories_button)
        self.sidebar_layout.addWidget(self.goals_button)
        self.sidebar_layout.addWidget(self.management_divider)
        self.sidebar_layout.addWidget(self.user_management_button)
        self.sidebar_layout.addWidget(self.settings_button)
        self.sidebar_layout.addStretch()
        self.sidebar_layout.addWidget(self.exit_button)
        self.sidebar_layout.addWidget(self.user_bar)

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
            }
            QLabel#currentUserName {
                color: #f2f4f7;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#currentUserSubtitle {
                color: #858f9c;
                font-size: 10px;
                font-weight: 400;
            }
            QWidget#currentUserPanel[interactive="true"] {
                background-color: transparent;
                border-radius: 8px;
            }
            QWidget#currentUserPanel[interactive="true"]:hover {
                background-color: #252a31;
            }
            QFrame#sidebarDivider {
                color: #2b3037;
                background-color: transparent;
                border: none;
                border-top: 1px solid #2b3037;
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
            QPushButton#sidebarExitButton {
                background-color: transparent;
                color: #bfc4ca;
                border: none;
                border-radius: 9px;
                text-align: left;
                padding: 11px 14px;
                font-size: 14px;
            }
            QPushButton#sidebarExitButton:hover {
                background-color: #321f24;
                color: #ffb4b4;
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
        self.close_profile_menu()
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
        self.brand_layout.setSpacing(4 if collapsed else 8)
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
            refresh_button_icon_spacing(button)
            button.setMaximumWidth(48 if collapsed else 16777215)
        self.exit_button.setText(
            "" if collapsed else self.exit_button.property("sidebarLabel")
        )
        refresh_button_icon_spacing(self.exit_button)
        self.exit_button.setMaximumWidth(48 if collapsed else 16777215)
        self.current_user_text.setVisible(not collapsed)
        self.current_user_name.setVisible(not collapsed)
        self.current_user_subtitle.setVisible(not collapsed)
        self.add_user_button.setVisible(not collapsed)
        self.switch_user_button.setVisible(not collapsed)
        self.current_user_panel.set_interactive(collapsed)
        self.current_user_avatar.setCursor(
            Qt.CursorShape.PointingHandCursor
            if collapsed
            else Qt.CursorShape.ArrowCursor
        )
        self.user_bar_layout.setContentsMargins(
            7 if collapsed else 6,
            24,
            7 if collapsed else 6,
            7,
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
        self.close_profile_menu()
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
        self.close_profile_menu()
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
            self.current_user_subtitle.setText("")
            self.current_user_avatar.clear()
            return
        user_name = current_user["name"]
        icon = avatar_icon(
            user_name,
            current_user["color"],
            34,
            profile_type=current_user.get("type", "user"),
        )
        self.current_user_avatar.setProperty(
            "profileType", current_user.get("type", "user")
        )
        self.current_user_avatar.setPixmap(icon.pixmap(34, 34))
        profile_label = "group" if current_user.get("type") == "group" else "user"
        self.current_user_avatar.setToolTip(f"Current {profile_label}: {user_name}")
        self.current_user_name.setText(user_name)
        self.current_user_subtitle.setText(
            str(current_user.get("subtitle") or "Personal")
        )
        self.current_user_name.setAccessibleName(
            f"Current {profile_label}: {user_name}"
        )
        self.current_user_panel.setAccessibleName(
            f"Current {profile_label}: {user_name}"
        )

    def toggle_profile_menu(self) -> None:
        """Open or close the collapsed-profile actions without changing profiles."""
        if not self.is_collapsed or self.current_profile is None:
            return
        if self.profile_menu is not None and self.profile_menu.isVisible():
            self.close_profile_menu()
            return

        menu = ProfileMenu(
            self.current_profile,
            self.window(),
            anchor_widget=self.current_user_panel,
        )
        menu.add_user_clicked.connect(self.create_user_clicked.emit)
        menu.change_user_clicked.connect(self.switch_user_clicked.emit)
        menu.closed.connect(self._profile_menu_closed)
        self.profile_menu = menu
        menu.ensurePolished()
        menu.adjustSize()
        menu.resize(menu.sizeHint())
        menu.move(self._profile_menu_position(menu.size()))
        menu.show()
        menu.raise_()
        menu.add_user_button.setFocus(Qt.FocusReason.PopupFocusReason)

    def _profile_menu_position(self, menu_size: QSize) -> QPoint:
        anchor = self.current_user_avatar.mapToGlobal(QPoint(0, 0))
        window = self.window()
        window_top_left = window.mapToGlobal(QPoint(0, 0))
        bounds = QRect(window_top_left, window.size())
        padding = 8
        x = anchor.x()
        y = anchor.y() - menu_size.height() - padding
        x = max(bounds.left() + padding, min(x, bounds.right() - menu_size.width() - padding + 1))
        y = max(bounds.top() + padding, min(y, bounds.bottom() - menu_size.height() - padding + 1))
        return QPoint(x, y)

    def close_profile_menu(self) -> None:
        menu = self.profile_menu
        self.profile_menu = None
        if menu is not None:
            menu.close()

    def _profile_menu_closed(self) -> None:
        sender = self.sender()
        if sender is self.profile_menu:
            self.profile_menu = None

    # Kept as a compatibility entry point for callers of the old dropdown API.
    def toggle_user_dropdown(self):
        self.toggle_profile_menu()

    def select_user(self, user_id: str):
        if user_id == self.current_user_id:
            return
        if user_id not in {user["id"] for user in self.users}:
            return
        self.close_profile_menu()
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
        self.close_profile_menu()
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
        button.setProperty("sidebarPage", page_name)
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

    def set_current_page(self, page_name: str) -> None:
        """Synchronize checked navigation state after programmatic page changes."""
        for button in self.navigation_buttons:
            button.setChecked(button.property("sidebarPage") == page_name)

    def handle_navigation(
        self, selected_button: QPushButton, page_name: str
    ):
        self.set_current_page(page_name)
        self.page_changed.emit(page_name)
