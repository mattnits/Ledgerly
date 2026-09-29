from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget, QVBoxLayout

from ui.classification_rules import ClassificationRulesDialog
from ui.components.page_header import PageHeader
from ui.components.statements_table import StatementsTable
from ui.theme import set_button_icon
from utils.constants import ADD_STATMENT_LABEL


class TransactionsPage(QWidget):

    def __init__(self):
        super().__init__()
        self.user_id: str | None = None
        self.setObjectName("transactionsPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(18)

        add_files_button = QPushButton(ADD_STATMENT_LABEL)
        add_files_button.setObjectName("primaryButton")
        set_button_icon(
            add_files_button,
            "fa6s.plus",
            color="#ffffff",
            active_color="#ffffff",
        )
        add_files_button.clicked.connect(self._open_file_selection)
        rules_button = QPushButton("Classification Rules")
        rules_button.setObjectName("secondaryActionButton")
        set_button_icon(rules_button, "fa6s.gear", color="#b9bec5")
        rules_button.clicked.connect(self._open_classification_rules)
        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)
        actions_layout.addWidget(rules_button)
        actions_layout.addWidget(add_files_button)
        self.header = PageHeader(
            "Transactions",
            "0 transactions",
            action_button=actions,
        )
        layout.addWidget(self.header)

        self.statements_table = StatementsTable()
        self.statements_table.count_changed.connect(self._update_count)
        self.statements_table.create_rule_requested.connect(
            self._open_rule_from_transaction
        )
        layout.addWidget(self.statements_table, 1)

    def _update_count(self, count: int) -> None:
        noun = "transaction" if count == 1 else "transactions"
        self.header.set_subtitle(f"{count:,} {noun}")

    def set_user_id(self, user_id: str | None) -> None:
        self.user_id = user_id
        self.statements_table.set_user_id(user_id)

    def reload(self) -> None:
        self.statements_table.reload()

    def _open_file_selection(self) -> None:
        self.window().dashboard_page.open_file_selection()

    def _open_classification_rules(self) -> None:
        if self.user_id is None:
            return
        dialog = ClassificationRulesDialog(self.user_id, self)
        dialog.rules_changed.connect(self.reload)
        dialog.exec()

    def _open_rule_from_transaction(self, prefill) -> None:
        if self.user_id is None:
            return
        dialog = ClassificationRulesDialog(
            self.user_id,
            self,
            prefill=prefill,
        )
        dialog.rules_changed.connect(self.reload)
        dialog.exec()
