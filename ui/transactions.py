from PySide6.QtWidgets import QWidget, QVBoxLayout

from ui.components.statements_table import StatementsTable


class TransactionsPage(QWidget):

    def __init__(self):
        super().__init__()
        self.setObjectName("transactionsPage")
        self.setStyleSheet("QWidget#transactionsPage { background: #191d22; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        self.statements_table = StatementsTable()
        layout.addWidget(self.statements_table, 1)

    def set_user_id(self, user_id: str | None) -> None:
        self.statements_table.set_user_id(user_id)

    def reload(self) -> None:
        self.statements_table.reload()
