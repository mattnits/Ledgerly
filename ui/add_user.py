from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from database.db import SessionLocal
from database.models import User
from ui.theme import COLORS, set_button_icon


class AddUserDialog(QDialog):
    """Modal user-creation form shared by onboarding and the sidebar."""

    user_created = Signal(str)

    def __init__(self, parent=None, session_factory=SessionLocal):
        super().__init__(parent)
        self.session_factory = session_factory
        self.selected_color = QColor("#249cf0")

        self.setObjectName("addUserDialog")
        self.setWindowTitle("Add User")
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.setFixedSize(500, 390)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)

        self.card = QFrame()
        self.card.setObjectName("addUserDialogCard")
        outer_layout.addWidget(self.card)

        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 7)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(26, 21, 26, 20)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)
        heading = QVBoxLayout()
        heading.setSpacing(4)
        self.title_label = QLabel("Add User")
        self.title_label.setObjectName("addUserDialogTitle")
        self.subtitle_label = QLabel("Create a new profile for this finance app.")
        self.subtitle_label.setObjectName("addUserDialogSubtitle")
        heading.addWidget(self.title_label)
        heading.addWidget(self.subtitle_label)
        header.addLayout(heading, 1)

        self.close_button = QToolButton()
        self.close_button.setObjectName("addUserDialogClose")
        self.close_button.setFixedSize(30, 30)
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
        header.addWidget(
            self.close_button,
            alignment=Qt.AlignmentFlag.AlignTop,
        )
        layout.addLayout(header)

        layout.addSpacing(18)
        layout.addWidget(self._separator())
        layout.addSpacing(17)

        self.name_label = QLabel("Name")
        self.name_label.setObjectName("addUserFieldLabel")
        self.name_input = QLineEdit()
        self.name_input.setObjectName("addUserNameInput")
        self.name_input.setPlaceholderText("Enter your name")
        self.name_input.setMaxLength(100)
        self.name_input.setFixedHeight(40)
        self.name_input.setAccessibleName("Name")
        self.name_label.setBuddy(self.name_input)
        layout.addWidget(self.name_label)
        layout.addSpacing(7)
        layout.addWidget(self.name_input)

        layout.addSpacing(18)
        self.color_label = QLabel("Profile Colour")
        self.color_label.setObjectName("addUserFieldLabel")
        layout.addWidget(self.color_label)
        layout.addSpacing(8)

        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(14)
        self.color_preview = QWidget()
        self.color_preview.setObjectName("addUserColorPreview")
        self.color_preview.setFixedSize(40, 40)
        self.color_preview.setAccessibleName("Selected profile colour")
        self.color_button = QPushButton("Choose Colour")
        self.color_button.setObjectName("addUserColorButton")
        self.color_button.setFixedHeight(40)
        set_button_icon(self.color_button, "fa6s.palette", size=16)
        self.color_button.clicked.connect(self.open_color_picker)
        color_row.addWidget(self.color_preview)
        color_row.addWidget(self.color_button, 1)
        layout.addLayout(color_row)

        layout.addSpacing(22)
        layout.addWidget(self._separator())
        layout.addSpacing(18)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(12)
        footer.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("addUserCancelButton")
        self.cancel_button.setFixedHeight(40)
        self.cancel_button.clicked.connect(self.reject)
        self.add_user_button = QPushButton("Add User")
        self.add_user_button.setObjectName("primaryButton")
        self.add_user_button.setFixedHeight(40)
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

        self.update_color_preview()
        self.setStyleSheet(self._stylesheet())
        for control in (
            self.name_input,
            self.color_button,
            self.cancel_button,
            self.add_user_button,
        ):
            control.setFixedHeight(40)

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setObjectName("addUserSeparator")
        line.setFixedHeight(1)
        return line

    def open_color_picker(self) -> None:
        color = QColorDialog.getColor(
            self.selected_color,
            self,
            "Choose Profile Colour",
        )
        if color.isValid():
            self.selected_color = color
            self.update_color_preview()

    def update_color_preview(self) -> None:
        color = self.selected_color.name()
        self.color_preview.setStyleSheet(
            f"background-color: {color}; border-radius: 8px; "
            f"border: 1px solid #4d5966;"
        )
        self.color_preview.setToolTip(color.upper())

    def add_user(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(
                self,
                "Missing Name",
                "Please enter a name.",
            )
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
                self,
                "Error",
                f"Could not create user:\n{exc}",
            )
            return

        self.name_input.clear()
        self.accept()
        self.user_created.emit(user_id)

    @staticmethod
    def _stylesheet() -> str:
        return f"""
            QDialog#addUserDialog {{
                background: transparent;
            }}
            QFrame#addUserDialogCard {{
                background: #11161c;
                border: 1px solid #303944;
                border-radius: 13px;
            }}
            QLabel#addUserDialogTitle {{
                color: {COLORS['text']};
                font-size: 21px;
                font-weight: 700;
            }}
            QLabel#addUserDialogSubtitle {{
                color: {COLORS['text_muted']};
                font-size: 13px;
            }}
            QLabel#addUserFieldLabel {{
                color: #eef1f5;
                font-size: 13px;
                font-weight: 500;
            }}
            QFrame#addUserSeparator {{
                background: #252d36;
                border: none;
            }}
            QToolButton#addUserDialogClose {{
                background: transparent;
                border: none;
                border-radius: 7px;
                padding: 0;
            }}
            QToolButton#addUserDialogClose:hover {{
                background: #252c34;
            }}
            QLineEdit#addUserNameInput {{
                background: #171d24;
                border: 1px solid #36414d;
                border-radius: 9px;
                padding: 0 13px;
            }}
            QLineEdit#addUserNameInput:focus {{
                border-color: #398cff;
            }}
            QPushButton#addUserColorButton {{
                background: #1b222a;
                border-color: #303a45;
            }}
            QPushButton#addUserCancelButton {{
                min-width: 92px;
                padding: 8px 18px;
            }}
            QPushButton#primaryButton {{
                min-width: 118px;
                padding: 8px 18px;
            }}
        """


# Keep the old import name working for callers while the UI is now a dialog.
AddUserPage = AddUserDialog
