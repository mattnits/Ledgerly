from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
)


class SettingsPage(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)

        title = QLabel("Settings")

        title.setStyleSheet("""
            font-size: 28px;
            font-weight: 700;
        """)

        layout.addWidget(title)

        layout.addStretch()