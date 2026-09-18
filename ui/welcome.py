from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
)

from ui.components.page_header import PageHeader


class WelcomePage(QWidget):
    add_user_clicked = Signal()

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)

        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        header = PageHeader(
            "Welcome to the Finance App",
            "Please click below to add a user.",
            centered=True,
        )

        add_user_button = QPushButton("Add User")

        add_user_button.setFixedWidth(180)
        add_user_button.setFixedHeight(44)

        add_user_button.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                font-weight: 600;
                border-radius: 8px;
                padding: 10px 18px;
            }
        """)

        add_user_button.clicked.connect(
            self.add_user_clicked.emit
        )

        layout.addWidget(header)
        layout.addSpacing(10)
        layout.addWidget(
            add_user_button,
            alignment=Qt.AlignCenter,
        )
