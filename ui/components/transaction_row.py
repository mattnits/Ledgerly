from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import QObject, QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QWidget


def _action_icon(restore: bool) -> QIcon:
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#dce6f3"), 1.6, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if restore:
        path = QPainterPath()
        path.moveTo(4, 8)
        path.cubicTo(5, 4, 10, 3, 13, 6)
        path.cubicTo(16, 9, 14, 14, 9, 14)
        painter.drawPath(path)
        painter.drawLine(4, 8, 4, 4)
        painter.drawLine(4, 8, 8, 8)
    else:
        painter.drawLine(4, 5, 14, 5)
        painter.drawLine(7, 3, 11, 3)
        painter.drawLine(5, 7, 6, 15)
        painter.drawLine(13, 7, 12, 15)
        painter.drawLine(6, 15, 12, 15)
        painter.drawLine(8, 8, 8, 13)
        painter.drawLine(10, 8, 10, 13)
    painter.end()
    return QIcon(pixmap)


class TransactionRow(QObject):
    category_changed = Signal(int, object)
    deletion_changed = Signal(int, bool)

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
        deleted_category_id: int | None = None,
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
        self.is_deleted = category_id == deleted_category_id and deleted_category_id is not None

        self.category_combo = QComboBox()
        if not self.is_deleted:
            self.category_combo.addItem("Uncategorized", None)
        for available_id, name, _ in categories:
            if (available_id == deleted_category_id) == self.is_deleted:
                self.category_combo.addItem(name, available_id)
        self.category_combo.setCurrentIndex(self.category_combo.findData(category_id))
        self.category_combo.setEnabled(not self.is_deleted)
        self._style_category()
        self.category_combo.currentIndexChanged.connect(self._category_selected)

        self.category_cell = QWidget()
        category_layout = QHBoxLayout(self.category_cell)
        category_layout.setContentsMargins(14, 0, 0, 0)
        category_layout.setSpacing(0)
        category_layout.addWidget(self.category_combo, alignment=Qt.AlignmentFlag.AlignVCenter)
        category_layout.addStretch()

        self.action_button = QPushButton()
        self.action_button.setObjectName("transactionActionButton")
        self.action_button.setIcon(_action_icon(self.is_deleted))
        self.action_button.setIconSize(QSize(18, 18))
        self.action_button.setAccessibleName(
            "Restore transaction" if self.is_deleted else "Remove transaction"
        )
        self.action_button.setToolTip(
            "Restore this transaction to its previous category"
            if self.is_deleted else "Move this transaction to Deleted"
        )
        self.action_button.setFixedSize(28, 28)
        self.action_button.setStyleSheet("""
            QPushButton#transactionActionButton {
                color: #cbd4e1;
                background: #303945;
                border: 1px solid #465263;
                border-radius: 6px;
            }
            QPushButton#transactionActionButton:hover {
                color: #ffffff;
                background: #465263;
            }
        """)
        self.action_button.clicked.connect(
            lambda: self.deletion_changed.emit(self.transaction_id, not self.is_deleted)
        )
        self.action_cell = QWidget()
        action_layout = QHBoxLayout(self.action_cell)
        action_layout.setContentsMargins(4, 0, 4, 0)
        action_layout.addWidget(self.action_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.cells = (
            f"{transaction_date:%b} {transaction_date.day}, {transaction_date.year}",
            description,
            f"-${abs(amount):,.2f}" if amount < 0 else f"${amount:,.2f}",
            account_name,
            f"{imported_at:%b} {imported_at.day}, {imported_at:%I:%M %p}",
            self.category_cell,
            self.action_cell,
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
