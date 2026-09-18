from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
)

from ui.components.page_header import PageHeader


class SettingsPage(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)

        layout.addWidget(PageHeader("Settings"))

        layout.addStretch()
