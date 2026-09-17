from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import QObject, QSignalBlocker, Signal
from PySide6.QtWidgets import QComboBox


class TransactionRow(QObject):
    category_changed = Signal(int, object)

    def __init__(
        self,
        transaction_id: int,
        transaction_date: date,
        description: str,
        amount: Decimal,
        imported_at: datetime,
        category_id: int | None,
        account_name: str,
        categories: list[tuple[int, str]],
        parent=None,
    ):
        super().__init__(parent)
        self.transaction_id = transaction_id
        self.saved_category_id = category_id
        self.description = description
        self.account_name = account_name
        self.category_names = dict(categories)
        self.amount = amount

        self.category_combo = QComboBox()
        self.category_combo.addItem("Uncategorized", None)
        for available_id, name in categories:
            self.category_combo.addItem(name, available_id)
        self.category_combo.setCurrentIndex(self.category_combo.findData(category_id))
        self.category_combo.setStyleSheet("""
            QComboBox {
                color: #d6deea;
                background: #2b3038;
                border: 1px solid #383f49;
                border-radius: 9px;
                padding: 5px 10px;
                margin: 4px 8px;
            }
            QComboBox:hover { border-color: #657183; }
            QComboBox:focus { border: 1px solid #4c99f3; }
            QComboBox::drop-down { border: none; width: 22px; }
            QComboBox QAbstractItemView {
                color: #d6deea;
                background: #23282f;
                border: 1px solid #414955;
                selection-background-color: #304b6b;
                selection-color: #ffffff;
            }
        """)
        self.category_combo.currentIndexChanged.connect(self._category_selected)

        self.cells = (
            f"{transaction_date:%b} {transaction_date.day}, {transaction_date.year}",
            description,
            f"-${abs(amount):,.2f}" if amount < 0 else f"${amount:,.2f}",
            account_name,
            f"{imported_at:%b} {imported_at.day}, {imported_at:%I:%M %p}",
            self.category_combo,
        )

    def _category_selected(self, index: int) -> None:
        category_id = self.category_combo.itemData(index)
        if category_id != self.saved_category_id:
            self.category_changed.emit(self.transaction_id, category_id)

    def mark_saved(self, category_id: int | None) -> None:
        self.saved_category_id = category_id

    def restore_category(self) -> None:
        with QSignalBlocker(self.category_combo):
            self.category_combo.setCurrentIndex(
                self.category_combo.findData(self.saved_category_id)
            )
