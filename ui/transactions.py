from PySide6.QtWidgets import QPushButton, QWidget, QVBoxLayout

from ui.components.page_header import PageHeader
from ui.components.statements_table import StatementsTable
from utils.constants import ADD_STATMENT_LABEL


class TransactionsPage(QWidget):

    def __init__(self):
        super().__init__()
        self.setObjectName("transactionsPage")
        self.setStyleSheet("QWidget#transactionsPage { background: #191d22; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 14)
        layout.setSpacing(14)

        add_files_button = QPushButton(ADD_STATMENT_LABEL)
        add_files_button.setObjectName("addStatementsButton")
        add_files_button.clicked.connect(self._open_file_selection)
        layout.addWidget(PageHeader("Transactions", action_button=add_files_button))

        self.statements_table = StatementsTable()
        layout.addWidget(self.statements_table, 1)

    def set_user_id(self, user_id: str | None) -> None:
        self.statements_table.set_user_id(user_id)

    def reload(self) -> None:
        self.statements_table.reload()

    def _open_file_selection(self) -> None:
        self.window().dashboard_page.open_file_selection()
