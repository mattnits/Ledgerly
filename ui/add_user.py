from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QFrame,
    QGridLayout,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from database.db import SessionLocal
from database.models import User
from ui.sidebar import ElidedLabel, avatar_icon
from ui.theme import COLORS, set_button_icon


PROFILE_COLORS = (
    "#3397f5",
    "#9148e8",
    "#ef4a8b",
    "#ff5b5b",
    "#ff8a34",
    "#ffd04a",
    "#57c978",
    "#2ebcc9",
    "#55a4f2",
    "#6265ed",
    "#a668e5",
    "#8793aa",
)


class ColorSwatchButton(QToolButton):
    color_selected = Signal(str)

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setObjectName("profileColorSwatch")
        self.setProperty("selected", False)
        self.setFixedSize(40, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(color.upper())
        self.setAccessibleName(f"Profile colour {color.upper()}")
        self.clicked.connect(lambda: self.color_selected.emit(self.color))
        self._apply_style()

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self._apply_style()

    def _apply_style(self) -> None:
        border = "3px solid #62acff" if self.property("selected") else "3px solid transparent"
        self.setStyleSheet(f"""
            QToolButton#profileColorSwatch {{
                background: {self.color};
                border: {border};
                border-radius: 20px;
            }}
            QToolButton#profileColorSwatch:hover {{
                border: 3px solid #c4ddf9;
            }}
        """)


class AddUserDialog(QDialog):
    """Responsive modal user-creation form shared by onboarding and the sidebar."""

    user_created = Signal(str)

    def __init__(self, parent=None, session_factory=SessionLocal):
        super().__init__(parent)
        self.session_factory = session_factory
        self.selected_color = QColor(PROFILE_COLORS[0])
        self.setObjectName("addUserDialog")
        self.setWindowTitle("Add User")
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(560, 410)
        self.resize(self._preferred_width(), 440)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(12, 12, 12, 12)
        self.card = QFrame()
        self.card.setObjectName("addUserDialogCard")
        outer_layout.addWidget(self.card)
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 7)
        shadow.setColor(QColor(0, 0, 0, 155))
        self.card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(0)
        header = QHBoxLayout()
        header.setSpacing(12)
        heading = QVBoxLayout()
        heading.setSpacing(5)
        self.title_label = QLabel("Add User")
        self.title_label.setObjectName("addUserDialogTitle")
        self.subtitle_label = QLabel(
            "Create a new user to keep transactions separate."
        )
        self.subtitle_label.setObjectName("addUserDialogSubtitle")
        self.subtitle_label.setWordWrap(True)
        heading.addWidget(self.title_label)
        heading.addWidget(self.subtitle_label)
        header.addLayout(heading, 1)
        self.close_button = QToolButton()
        self.close_button.setObjectName("addUserDialogClose")
        self.close_button.setFixedSize(30, 30)
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setToolTip("Close")
        self.close_button.setAccessibleName("Close add user dialog")
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

        content = QHBoxLayout()
        content.setSpacing(22)
        form = QVBoxLayout()
        form.setSpacing(0)
        self.name_label = QLabel("Name")
        self.name_label.setObjectName("addUserFieldLabel")
        self.name_input = QLineEdit()
        self.name_input.setObjectName("addUserNameInput")
        self.name_input.setPlaceholderText("Enter a name (e.g. Alex)")
        self.name_input.setMaxLength(100)
        self.name_input.setFixedHeight(40)
        self.name_input.setAccessibleName("Name")
        self.name_label.setBuddy(self.name_input)
        self.name_input.textChanged.connect(self.update_preview)
        form.addWidget(self.name_label)
        form.addSpacing(7)
        form.addWidget(self.name_input)
        form.addSpacing(20)
        self.color_label = QLabel("Profile Colour")
        self.color_label.setObjectName("addUserFieldLabel")
        form.addWidget(self.color_label)
        form.addSpacing(10)

        palette = QGridLayout()
        palette.setContentsMargins(0, 0, 0, 0)
        palette.setHorizontalSpacing(12)
        palette.setVerticalSpacing(12)
        self.color_swatches: list[ColorSwatchButton] = []
        for index, color in enumerate(PROFILE_COLORS):
            swatch = ColorSwatchButton(color)
            swatch.color_selected.connect(self.select_color)
            palette.addWidget(swatch, index // 6, index % 6)
            self.color_swatches.append(swatch)
        self.color_button = self.color_swatches[0]
        self.color_label.setBuddy(self.color_button)
        form.addLayout(palette)
        form.addStretch()
        content.addLayout(form, 2)

        self.preview_card = QFrame()
        self.preview_card.setObjectName("addUserPreviewCard")
        self.preview_card.setMinimumWidth(150)
        self.preview_card.setMaximumWidth(190)
        preview_layout = QVBoxLayout(self.preview_card)
        preview_layout.setContentsMargins(18, 16, 18, 20)
        preview_title = QLabel("Preview")
        preview_title.setObjectName("addUserPreviewTitle")
        preview_layout.addWidget(preview_title)
        preview_layout.addStretch()
        self.color_preview = QLabel()
        self.color_preview.setObjectName("addUserColorPreview")
        self.color_preview.setFixedSize(76, 76)
        self.color_preview.setAccessibleName("Selected profile colour")
        preview_layout.addWidget(
            self.color_preview, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        preview_layout.addSpacing(12)
        self.preview_name = ElidedLabel("New user")
        self.preview_name.setObjectName("addUserPreviewName")
        self.preview_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_name.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        preview_layout.addWidget(self.preview_name)
        self.preview_type = QLabel("Personal")
        self.preview_type.setObjectName("addUserPreviewType")
        self.preview_type.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.preview_type)
        preview_layout.addStretch()
        content.addWidget(self.preview_card, 1)
        layout.addLayout(content, 1)
        layout.addSpacing(20)

        footer = QHBoxLayout()
        footer.setSpacing(12)
        footer.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("addUserCancelButton")
        self.cancel_button.setFixedSize(98, 40)
        self.cancel_button.clicked.connect(self.reject)
        self.add_user_button = QPushButton("Add User")
        self.add_user_button.setObjectName("primaryButton")
        self.add_user_button.setFixedSize(124, 40)
        self.add_user_button.setDefault(True)
        set_button_icon(
            self.add_user_button,
            "fa6s.user-plus",
            color="#ffffff",
            active_color="#ffffff",
            size=16,
        )
        self.add_user_button.clicked.connect(self.add_user)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.add_user_button)
        layout.addLayout(footer)

        self.setStyleSheet(self._stylesheet())
        self.update_preview()
        self.name_input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _preferred_width(self) -> int:
        parent_width = self.parentWidget().width() if self.parentWidget() else 700
        return max(560, min(720, int(parent_width * 0.62)))

    def select_color(self, color: str) -> None:
        selected = QColor(color)
        if not selected.isValid():
            return
        self.selected_color = selected
        self.update_preview()

    def open_color_picker(self) -> None:
        """Keep custom-colour support available to programmatic callers."""
        color = QColorDialog.getColor(
            self.selected_color, self, "Choose Profile Colour"
        )
        if color.isValid():
            self.selected_color = color
            self.update_preview()

    def update_color_preview(self) -> None:
        """Backward-compatible alias used by existing integrations."""
        self.update_preview()

    def update_preview(self) -> None:
        name = self.name_input.text().strip() or "New user"
        color = self.selected_color.name()
        self.color_preview.setPixmap(avatar_icon(name, color, 76).pixmap(76, 76))
        self.color_preview.setToolTip(color.upper())
        self.preview_name.setText(name)
        for swatch in self.color_swatches:
            swatch.set_selected(swatch.color.casefold() == color.casefold())

    def add_user(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a name.")
            self.name_input.setFocus()
            return

        self.add_user_button.setEnabled(False)
        try:
            with self.session_factory.begin() as session:
                user = User(
                    name=name,
                    color=self.selected_color.name(),
                    profile_code_hash=None,
                )
                session.add(user)
                session.flush()
                user_id = user.id
        except Exception as exc:
            self.add_user_button.setEnabled(True)
            QMessageBox.critical(
                self, "Error", f"Could not create user:\n{exc}"
            )
            return

        self.name_input.clear()
        self.accept()
        self.user_created.emit(user_id)

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
            QDialog#addUserDialog {{ background: transparent; }}
            QFrame#addUserDialogCard {{
                background: #11171e;
                border: 1px solid #34404c;
                border-radius: 14px;
            }}
            QLabel#addUserDialogTitle {{
                color: {COLORS['text']}; font-size: 22px; font-weight: 700;
            }}
            QLabel#addUserDialogSubtitle {{
                color: {COLORS['text_muted']}; font-size: 13px;
            }}
            QLabel#addUserFieldLabel, QLabel#addUserPreviewTitle {{
                color: #eef1f5; font-size: 13px; font-weight: 500;
            }}
            QToolButton#addUserDialogClose {{
                background: transparent; border: none; border-radius: 7px;
            }}
            QToolButton#addUserDialogClose:hover {{ background: #252c34; }}
            QLineEdit#addUserNameInput {{
                background: #171d24;
                border: 1px solid #36414d;
                border-radius: 9px;
                min-height: 38px;
                max-height: 38px;
                padding: 0 13px;
            }}
            QLineEdit#addUserNameInput:focus {{ border-color: #398cff; }}
            QFrame#addUserPreviewCard {{
                background: #0e141a;
                border: 1px solid #2f3944;
                border-radius: 11px;
            }}
            QLabel#addUserPreviewName {{
                color: {COLORS['text']}; font-size: 15px; font-weight: 650;
            }}
            QLabel#addUserPreviewType {{
                color: {COLORS['text_muted']}; font-size: 12px;
            }}
            QPushButton#addUserCancelButton {{
                min-height: 38px; max-height: 38px; padding: 0 18px;
            }}
            QPushButton#primaryButton {{
                min-height: 38px; max-height: 38px; padding: 0 18px;
            }}
        """


# Keep the old import name working for callers while the UI is now a dialog.
AddUserPage = AddUserDialog
