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

from ui.sidebar import ElidedLabel, avatar_icon
from ui.theme import COLORS, set_button_icon


class UserChoiceRow(QFrame):
    """Keyboard- and pointer-accessible row in the user switcher."""

    activated = Signal(str)

    def __init__(self, user: dict[str, str], selected: bool, parent=None):
        super().__init__(parent)
        self.user_id = user["id"]
        self.setObjectName("userChoiceRow")
        self.setProperty("selected", selected)
        self.setAccessibleName(f"Switch to {user['name']}")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 14, 10)
        layout.setSpacing(13)
        avatar = QLabel()
        avatar.setFixedSize(42, 42)
        avatar.setPixmap(avatar_icon(user["name"], user["color"], 42).pixmap(42, 42))
        layout.addWidget(avatar)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        self.name_label = ElidedLabel(user["name"])
        self.name_label.setObjectName("userChoiceName")
        subtitle = QLabel("Personal")
        subtitle.setObjectName("userChoiceSubtitle")
        text_layout.addWidget(self.name_label)
        text_layout.addWidget(subtitle)
        layout.addLayout(text_layout, 1)

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
            self.activated.emit(self.user_id)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activated.emit(self.user_id)
            event.accept()
            return
        super().keyPressEvent(event)


class SwitchUserDialog(QDialog):
    user_selected = Signal(str)

    def __init__(
        self,
        users: list[dict[str, str]],
        current_user_id: str | None,
        parent=None,
    ):
        super().__init__(parent)
        self.users = users
        self.current_user_id = current_user_id
        self.setObjectName("switchUserDialog")
        self.setWindowTitle("Switch User")
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
        heading = QVBoxLayout()
        heading.setSpacing(5)
        title = QLabel("Switch User")
        title.setObjectName("switchUserTitle")
        subtitle = QLabel(
            "Choose a user to switch to. Each user has separate transactions, "
            "accounts and settings."
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
        for user in users:
            row = UserChoiceRow(user, user["id"] == current_user_id)
            row.activated.connect(self._select_user)
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

    def _select_user(self, user_id: str) -> None:
        self.user_selected.emit(user_id)
        self.accept()

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
                background: #11171e;
                border: 1px solid #34404c;
                border-radius: 14px;
            }}
            QLabel#switchUserTitle {{
                color: {COLORS['text']}; font-size: 22px; font-weight: 700;
            }}
            QLabel#switchUserSubtitle {{
                color: {COLORS['text_muted']}; font-size: 13px;
            }}
            QToolButton#switchUserClose {{
                background: transparent; border: none; border-radius: 7px;
            }}
            QToolButton#switchUserClose:hover {{ background: #252c34; }}
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
            QScrollBar:vertical {{ width: 8px; background: transparent; }}
            QScrollBar::handle:vertical {{
                background: #46515e; border-radius: 4px; min-height: 24px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """
