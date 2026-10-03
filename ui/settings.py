from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QFrame,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
    QVBoxLayout,
)

from database.reset import reset_financial_data
from database.user_management import delete_user
from ui.components.page_header import PageHeader
from ui.theme import set_button_icon, set_delete_button_icon


class SettingsPage(QWidget):
    data_reset = Signal()
    profile_deleted = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("settingsPage")
        self.current_user_id: str | None = None
        self.current_user_name = "this profile"

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

        danger = QFrame()
        danger.setObjectName("settingsCard")
        danger_layout = QVBoxLayout(danger)
        danger_layout.setContentsMargins(20, 18, 20, 18)
        danger_layout.setSpacing(8)
        danger_title = QLabel("Danger Zone")
        danger_title.setObjectName("sectionTitle")
        danger_layout.addWidget(danger_title)
        delete_row = QHBoxLayout()
        delete_description = QLabel(
            "Permanently delete your profile and all financial data owned by it."
        )
        delete_description.setWordWrap(True)
        delete_description.setObjectName("mutedLabel")
        delete_row.addWidget(delete_description, 1)
        self.delete_profile_button = QPushButton("Delete My Profile")
        self.delete_profile_button.setObjectName("dangerButton")
        set_button_icon(self.delete_profile_button, "fa6s.trash", size=14)
        self.delete_profile_button.clicked.connect(self.confirm_delete_profile)
        delete_row.addWidget(self.delete_profile_button)
        danger_layout.addLayout(delete_row)
        layout.addWidget(danger)

        layout.addStretch()

    def set_current_user(
        self, user_id: str | None, user_name: str | None = None
    ) -> None:
        self.current_user_id = user_id
        self.current_user_name = user_name or "this profile"
        self.delete_profile_button.setEnabled(user_id is not None)

    def confirm_delete_profile(self) -> None:
        if self.current_user_id is None:
            return
        prompt = (
            f"Delete {self.current_user_name}?\n\nThis permanently deletes transactions, accounts, "
            "import history, investments, savings data, budgets/goals, rules, "
            "custom categories where safe, memberships, and profile settings.\n\n"
            "This cannot be undone. Type DELETE to continue."
        )
        confirmation, accepted = QInputDialog.getText(
            self, "Delete My Profile", prompt
        )
        if not accepted or confirmation != "DELETE":
            return
        user_id = self.current_user_id
        try:
            delete_user(
                user_id,
                user_id,
                allow_self=True,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Profile not deleted", str(exc))
            return
        self.profile_deleted.emit(user_id)

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
