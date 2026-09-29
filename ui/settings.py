from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QFrame,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
    QVBoxLayout,
)

from database.reset import reset_financial_data
from ui.components.page_header import PageHeader
from ui.theme import set_button_icon


class SettingsPage(QWidget):
    data_reset = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("settingsPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(18)

        layout.addWidget(PageHeader("Settings", "Manage application data and preferences"))

        card = QFrame()
        card.setObjectName("settingsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(8)
        title = QLabel("Financial data")
        title.setObjectName("sectionTitle")
        card_layout.addWidget(title)

        reset_row = QHBoxLayout()
        description = QLabel(
            "Clear all transactions, accounts, and import history. "
            "Categories and category rules will be kept."
        )
        description.setWordWrap(True)
        description.setObjectName("mutedLabel")
        reset_row.addWidget(description, 1)

        reset_button = QPushButton("Reset")
        reset_button.setObjectName("dangerButton")
        set_button_icon(reset_button, "fa6s.trash", color="#ff9da0", size=15)
        reset_button.clicked.connect(self.confirm_reset)
        reset_row.addWidget(reset_button)
        card_layout.addLayout(reset_row)
        layout.addWidget(card)

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
