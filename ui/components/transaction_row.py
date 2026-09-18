from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import QObject, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QWidget


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
        categories: list[tuple[int, str, str]],
        parent=None,
    ):
        super().__init__(parent)
        self.transaction_id = transaction_id
        self.saved_category_id = category_id
        self.description = description
        self.account_name = account_name
        self.category_colors = {
            available_id: color for available_id, _, color in categories
        }
        self.amount = amount

        self.category_combo = QComboBox()
        self.category_combo.addItem("Uncategorized", None)
        for available_id, name, _ in categories:
            self.category_combo.addItem(name, available_id)
        self.category_combo.setCurrentIndex(self.category_combo.findData(category_id))
        self._style_category()
        self.category_combo.currentIndexChanged.connect(self._category_selected)

        self.category_cell = QWidget()
        category_layout = QHBoxLayout(self.category_cell)
        category_layout.setContentsMargins(14, 0, 0, 0)
        category_layout.setSpacing(0)
        category_layout.addWidget(self.category_combo, alignment=Qt.AlignmentFlag.AlignVCenter)
        category_layout.addStretch()

        self.cells = (
            f"{transaction_date:%b} {transaction_date.day}, {transaction_date.year}",
            description,
            f"-${abs(amount):,.2f}" if amount < 0 else f"${amount:,.2f}",
            account_name,
            f"{imported_at:%b} {imported_at.day}, {imported_at:%I:%M %p}",
            self.category_cell,
        )

    def _style_category(self) -> None:
        name = self.category_combo.currentText()
        category_id = self.category_combo.currentData()
        color = QColor(self.category_colors.get(category_id, "#303b4b"))
        background = color.name()
        border = color.darker(125).name() if category_id is not None else "#4a5a70"
        channels = (color.redF(), color.greenF(), color.blueF())
        linear = tuple(
            channel / 12.92 if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        )
        luminance = sum(weight * channel for weight, channel in zip(
            (0.2126, 0.7152, 0.0722), linear
        ))
        foreground = "#10151c" if luminance > 0.179 else "#f8fafc"
        self.category_combo.setFixedWidth(
            min(190, max(90, self.category_combo.fontMetrics().horizontalAdvance(name) + 30))
        )
        self.category_combo.setFixedHeight(26)
        self.category_combo.setStyleSheet(f"""
            QComboBox {{
                color: {foreground};
                background: {background};
                border: 1px solid {border};
                border-radius: 13px;
                padding: 2px 10px;
                font-size: 12px;
            }}
            QComboBox:hover {{ border-color: #657183; }}
            QComboBox:focus {{ border: 1px solid #4c99f3; }}
            QComboBox::drop-down {{ border: none; width: 0px; }}
            QComboBox QAbstractItemView {{
                color: #d6deea;
                background: #23282f;
                border: 1px solid #414955;
                selection-background-color: #304b6b;
                selection-color: #ffffff;
            }}
        """)

    def _category_selected(self, index: int) -> None:
        self._style_category()
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
        self._style_category()
