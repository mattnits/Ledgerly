from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor

from app.ui.sidebar import ElidedLabel, avatar_icon
from app.ui.theme import COLORS, awesome_icon, set_button_icon


class UserChoiceRow(QFrame):
    """Keyboard- and pointer-accessible row in the user switcher."""

    activated = Signal(str)
    edit_requested = Signal(int)

    def __init__(
        self,
        user: dict[str, str],
        selected: bool,
        parent=None,
        *,
        can_edit_group: bool = True,
    ):
        super().__init__(parent)
        self.profile_type = user.get("type", "user")
        self.user_id = user["id"]
        self.profile_key = user.get("key", str(user["id"]))
        self.setObjectName("userChoiceRow")
        self.setProperty("selected", selected)
        self.setAccessibleName(f"Switch to {user['name']}")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 14, 10)
        layout.setSpacing(8)
        self.avatar = QLabel()
        self.avatar.setFixedSize(42, 42)
        self.avatar.setProperty("profileType", self.profile_type)
        self.avatar.setPixmap(avatar_icon(
            user["name"], user["color"], 42, profile_type=self.profile_type
        ).pixmap(42, 42))
        layout.addWidget(self.avatar)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        self.name_label = ElidedLabel(user["name"])
        self.name_label.setObjectName("userChoiceName")
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(6)
        name_row.addWidget(self.name_label, 1)
        if user.get("is_admin"):
            self.name_label.setAccessibleName(f"{user['name']}, Admin")
            self.admin_star = QLabel()
            self.admin_star.setPixmap(
                awesome_icon("fa6s.star", color="#a7afb9").pixmap(12, 12)
            )
            self.admin_star.setToolTip("Admin")
            name_row.addWidget(self.admin_star)
        subtitle = QLabel(user.get("subtitle", "Personal"))
        subtitle.setObjectName("userChoiceSubtitle")
        text_layout.addLayout(name_row)
        text_layout.addWidget(subtitle)
        layout.addLayout(text_layout, 1)

        if self.profile_type == "group" and can_edit_group:
            edit_button = QToolButton()
            edit_button.setObjectName("editGroupButton")
            edit_button.setFixedSize(30, 30)
            edit_button.setToolTip("Edit group")
            edit_button.setAccessibleName(f"Edit {user['name']} group")
            set_button_icon(
                edit_button,
                "fa6s.pen",
                color=COLORS["text_muted"],
                active_color=COLORS["text"],
                size=13,
            )
            edit_button.clicked.connect(
                lambda checked=False: self.edit_requested.emit(int(self.user_id))
            )
            layout.addWidget(edit_button)

        selected_icon = QLabel()
        selected_icon.setObjectName("selectedUserIcon")
        selected_icon.setFixedSize(24, 24)
        selected_icon.setPixmap(
            avatar_icon("✓", COLORS["primary"], 24).pixmap(24, 24)
        )
        selected_icon.setVisible(selected)
        layout.addWidget(selected_icon)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.activated.emit(self.profile_key)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activated.emit(self.profile_key)
            event.accept()
            return
        super().keyPressEvent(event)


class SwitchUserDialog(QDialog):
    user_selected = Signal(str)
    profile_selected = Signal(str)
    group_edit_requested = Signal(int)

    def __init__(
        self,
        users: list[dict[str, str]],
        current_user_id: str | None,
        parent=None,
        *,
        can_manage_groups: bool = True,
    ):
        super().__init__(parent)
        self.users = users
        self.current_user_id = current_user_id
        self.setObjectName("switchUserDialog")
        self.setWindowTitle("Switch Profile")
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(420, 260)
        self.resize(self._preferred_width(), self._preferred_height())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        self.card = QFrame()
        self.card.setObjectName("switchUserDialogCard")
        outer.addWidget(self.card)
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 7)
        shadow.setColor(QColor(0, 0, 0, 155))
        self.card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(28, 24, 28, 26)
        layout.setSpacing(0)
        header = QHBoxLayout()
        header.setSpacing(8)
        icon_frame = QFrame()
        icon_frame.setObjectName("dialogIconFrame")
        icon_frame.setFixedSize(56, 56)
        icon_layout = QVBoxLayout(icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(
            awesome_icon("fa6s.arrow-right-arrow-left", color="#56a9ff").pixmap(27, 27)
        )
        icon_layout.addWidget(icon)
        header.addWidget(icon_frame, alignment=Qt.AlignmentFlag.AlignTop)
        heading = QVBoxLayout()
        heading.setSpacing(5)
        title = QLabel("Switch Profile")
        title.setObjectName("switchUserTitle")
        subtitle = QLabel(
            "Choose a personal profile or a group financial view."
        )
        subtitle.setObjectName("switchUserSubtitle")
        subtitle.setWordWrap(True)
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)
        self.close_button = QToolButton()
        self.close_button.setObjectName("switchUserClose")
        self.close_button.setFixedSize(30, 30)
        self.close_button.setToolTip("Close")
        self.close_button.setAccessibleName("Close switch user dialog")
        set_button_icon(
            self.close_button,
            "fa6s.xmark",
            color=COLORS["text_muted"],
            active_color=COLORS["text"],
            size=17,
        )
        self.close_button.clicked.connect(self.reject)
        header.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)
        layout.addSpacing(20)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("switchUserScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rows_widget = QWidget()
        self.rows_widget.setObjectName("switchUserRows")
        self.rows_layout = QVBoxLayout(self.rows_widget)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(6)
        self.user_rows: list[UserChoiceRow] = []
        for profile_type, heading in (("user", "PEOPLE"), ("group", "GROUPS")):
            section_profiles = [
                profile for profile in users
                if profile.get("type", "user") == profile_type
            ]
            if not section_profiles:
                continue
            section = QLabel(heading)
            section.setObjectName("profileSectionLabel")
            self.rows_layout.addWidget(section)
            for user in section_profiles:
                current_key = user.get("key", str(user["id"]))
                row = UserChoiceRow(
                    user,
                    current_key == current_user_id,
                    can_edit_group=can_manage_groups,
                )
                row.activated.connect(self._select_user)
                row.edit_requested.connect(self._edit_group)
                self.rows_layout.addWidget(row)
                self.user_rows.append(row)
        self.rows_layout.addStretch()
        self.scroll.setWidget(self.rows_widget)
        layout.addWidget(self.scroll, 1)
        self.setStyleSheet(self._stylesheet())

    def _preferred_width(self) -> int:
        parent_width = self.parentWidget().width() if self.parentWidget() else 520
        return max(420, min(560, int(parent_width * 0.48)))

    def _preferred_height(self) -> int:
        parent_height = self.parentWidget().height() if self.parentWidget() else 600
        content_height = 168 + min(max(len(self.users), 1), 6) * 74
        return max(260, min(content_height, min(620, parent_height - 60)))

    def _select_user(self, profile_key: str) -> None:
        self.profile_selected.emit(profile_key)
        selected = next(
            (
                profile for profile in self.users
                if profile.get("key", str(profile["id"])) == profile_key
            ),
            None,
        )
        if selected is not None and selected.get("type", "user") == "user":
            self.user_selected.emit(str(selected["id"]))
        self.accept()

    def _edit_group(self, group_id: int) -> None:
        self.group_edit_requested.emit(group_id)
        self.reject()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API spelling
        super().showEvent(event)
        self._center_on_parent()

    def _center_on_parent(self) -> None:
        parent = self.parentWidget()
        target = parent.window().frameGeometry() if parent else self.screen().availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(target.center())
        available = self.screen().availableGeometry()
        x = max(available.left(), min(frame.left(), available.right() - frame.width() + 1))
        y = max(available.top(), min(frame.top(), available.bottom() - frame.height() + 1))
        self.move(x, y)

    @staticmethod
    def _stylesheet() -> str:
        return f"""
            QDialog#switchUserDialog {{ background: transparent; }}
            QFrame#switchUserDialogCard {{
                background: #111820;
                border: 1px solid #344351;
                border-radius: 16px;
            }}
            QLabel#switchUserTitle {{
                color: {COLORS['text']}; font-size: 24px; font-weight: 750;
            }}
            QLabel#switchUserSubtitle {{
                color: #aebbd0; font-size: 14px;
            }}
            QToolButton#switchUserClose {{
                background: transparent; border: none; border-radius: 7px;
            }}
            QToolButton#switchUserClose:hover {{ background: #252c34; }}
            QToolButton#editGroupButton {{
                background: transparent; border: none; border-radius: 7px;
            }}
            QToolButton#editGroupButton:hover {{ background: #2b3540; }}
            QScrollArea#switchUserScroll, QWidget#switchUserRows {{
                background: transparent; border: none;
            }}
            QFrame#userChoiceRow {{
                background: #171d24;
                border: 1px solid #303a45;
                border-radius: 10px;
            }}
            QFrame#userChoiceRow:hover, QFrame#userChoiceRow:focus {{
                background: #1d2733; border-color: #4d6e94;
            }}
            QFrame#userChoiceRow[selected="true"] {{
                background: #17253a; border-color: #2f76c8;
            }}
            QLabel#userChoiceName {{
                color: {COLORS['text']}; font-size: 14px; font-weight: 650;
            }}
            QLabel#userChoiceSubtitle {{
                color: {COLORS['text_muted']}; font-size: 12px;
            }}
            QLabel#profileSectionLabel {{
                color: {COLORS['text_dim']}; font-size: 11px; font-weight: 700;
                padding: 10px 4px 3px 4px;
            }}
            QScrollBar:vertical {{ width: 8px; background: transparent; }}
            QScrollBar::handle:vertical {{
                background: #46515e; border-radius: 4px; min-height: 24px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """
