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
from ui.theme import set_button_icon, set_delete_button_icon


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
        title = QLabel("Transaction data")
        title.setObjectName("sectionTitle")
        card_layout.addWidget(title)

        reset_row = QHBoxLayout()
        description = QLabel(
            "Delete all transactions and statement import history. Accounts, "
            "investments, categories, and categorization rules will be kept."
        )
        description.setWordWrap(True)
        description.setObjectName("mutedLabel")
        reset_row.addWidget(description, 1)

        reset_button = QPushButton("Delete Data")
        reset_button.setObjectName("dangerButton")
        reset_button.setToolTip("Delete all transaction and statement import data")
        set_delete_button_icon(reset_button)
        reset_button.clicked.connect(self.confirm_reset)
        reset_row.addWidget(reset_button)
        card_layout.addLayout(reset_row)
        layout.addWidget(card)

        layout.addStretch()

    def confirm_reset(self) -> None:
        answer = QMessageBox.question(
            self,
            "Delete transaction data",
            "Delete all transactions and statement import history for every user? "
            "This cannot be undone. Accounts, investments, categories, and "
            "categorization rules will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            reset_financial_data()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Delete failed",
                f"Could not delete transaction data:\n{exc}",
            )
            return

        self.data_reset.emit()
