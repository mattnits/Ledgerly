from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
    QVBoxLayout,
)

from database.reset import reset_financial_data
from ui.components.page_header import PageHeader


class SettingsPage(QWidget):
    data_reset = Signal()

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)

        layout.addWidget(PageHeader("Settings"))

        reset_row = QHBoxLayout()
        description = QLabel(
            "Clear all transactions, accounts, and import history. "
            "Categories and category rules will be kept."
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #aeb9c8; font-size: 14px;")
        reset_row.addWidget(description, 1)

        reset_button = QPushButton("Reset")
        reset_button.setFixedWidth(80)
        reset_button.setStyleSheet("""
            QPushButton {
                color: #ffffff;
                background: #8b3541;
                border: 1px solid #b44b5a;
                border-radius: 8px;
                padding: 7px 10px;
            }
            QPushButton:hover { background: #a6404e; }
        """)
        reset_button.clicked.connect(self.confirm_reset)
        reset_row.addWidget(reset_button)
        layout.addLayout(reset_row)

        layout.addStretch()

    def confirm_reset(self) -> None:
        answer = QMessageBox.question(
            self,
            "Reset financial data",
            "Delete all transactions, accounts, and import history for every user? "
            "This cannot be undone. Categories and category rules will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            reset_financial_data()
        except Exception as exc:
            QMessageBox.critical(self, "Reset failed", f"Could not reset financial data:\n{exc}")
            return

        self.data_reset.emit()
