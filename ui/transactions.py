from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget, QVBoxLayout

from ui.classification_rules import ClassificationRulesDialog
from ui.components.page_header import PageHeader
from ui.components.statements_table import StatementsTable
from utils.constants import ADD_STATMENT_LABEL


class TransactionsPage(QWidget):

    def __init__(self):
        super().__init__()
        self.user_id: str | None = None
        self.setObjectName("transactionsPage")
        self.setStyleSheet("QWidget#transactionsPage { background: #191d22; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 14)
        layout.setSpacing(14)

        add_files_button = QPushButton(ADD_STATMENT_LABEL)
        add_files_button.setObjectName("addStatementsButton")
        add_files_button.clicked.connect(self._open_file_selection)
        rules_button = QPushButton("Classification Rules")
        rules_button.setObjectName("pageActionButton")
        rules_button.clicked.connect(self._open_classification_rules)
        add_files_button.setObjectName("pageActionButton")
        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)
        actions_layout.addWidget(rules_button)
        actions_layout.addWidget(add_files_button)
        layout.addWidget(PageHeader("Transactions", action_button=actions))

        self.statements_table = StatementsTable()
        self.statements_table.create_rule_requested.connect(
            self._open_rule_from_transaction
        )
        layout.addWidget(self.statements_table, 1)

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
