from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
)


class TransactionsPage(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)

        title = QLabel("Transactions")

        title.setStyleSheet("""
            font-size: 28px;
            font-weight: 700;
        """)

        layout.addWidget(title)

        layout.addStretch()