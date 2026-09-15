from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QColorDialog,
    QMessageBox,
)

from database.db import SessionLocal
from database.models import User


class AddUserPage(QWidget):
    user_created = Signal(str)

    def __init__(self):
        super().__init__()

        self.selected_color = QColor("#3498db")

        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(
            40,
            40,
            40,
            40,
        )

        main_layout.setAlignment(Qt.AlignCenter)

        # Form container
        form = QVBoxLayout()
        form.setSpacing(16)

        # -------------------------
        # Title
        # -------------------------

        title = QLabel("Add User")

        title.setStyleSheet("""
            font-size: 28px;
            font-weight: 700;
        """)

        title.setAlignment(Qt.AlignCenter)

        # -------------------------
        # Name
        # -------------------------

        name_label = QLabel("Name")

        self.name_input = QLineEdit()

        self.name_input.setPlaceholderText(
            "Enter your name"
        )

        self.name_input.setFixedWidth(350)
        self.name_input.setFixedHeight(40)

        # -------------------------
        # Colour picker
        # -------------------------

        color_label = QLabel("Profile Colour")

        color_row = QHBoxLayout()

        self.color_preview = QWidget()

        self.color_preview.setFixedSize(
            40,
            40,
        )

        self.update_color_preview()

        self.color_button = QPushButton(
            "Choose Colour"
        )

        self.color_button.setFixedHeight(40)

        self.color_button.clicked.connect(
            self.open_color_picker
        )

        color_row.addWidget(
            self.color_preview
        )

        color_row.addWidget(
            self.color_button
        )

        # -------------------------
        # Add user button
        # -------------------------

        self.add_user_button = QPushButton(
            "Add User"
        )

        self.add_user_button.setFixedHeight(44)

        self.add_user_button.clicked.connect(
            self.add_user
        )

        # -------------------------
        # Add to form
        # -------------------------

        form.addWidget(title)

        form.addSpacing(20)

        form.addWidget(name_label)
        form.addWidget(self.name_input)

        form.addSpacing(10)

        form.addWidget(color_label)
        form.addLayout(color_row)

        form.addSpacing(20)

        form.addWidget(self.add_user_button)

        main_layout.addLayout(form)

    def open_color_picker(self):
        color = QColorDialog.getColor(
            self.selected_color,
            self,
            "Choose Profile Colour",
        )

        if color.isValid():
            self.selected_color = color
            self.update_color_preview()

    def update_color_preview(self):
        self.color_preview.setStyleSheet(
            f"""
            background-color: {self.selected_color.name()};
            border-radius: 8px;
            border: 1px solid #888888;
            """
        )

    def add_user(self):
        name = self.name_input.text().strip()

        if not name:
            QMessageBox.warning(
                self,
                "Missing Name",
                "Please enter a name.",
            )
            return

        session = SessionLocal()

        try:
            user = User(
                name=name,
                color=self.selected_color.name(),
                profile_code_hash=None,
            )

            session.add(user)
            session.commit()

            user_id = user.id

            self.user_created.emit(user_id)

            self.name_input.clear()

        except Exception as exc:
            session.rollback()

            QMessageBox.critical(
                self,
                "Error",
                f"Could not create user:\n{exc}",
            )

        finally:
            session.close()