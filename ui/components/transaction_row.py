from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import QObject, QPoint, QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QWidget,
)

from utils.constants import (
    CATEGORY_FREE_TRANSACTION_TYPES,
    INCOME_CATEGORY_NAMES,
    TRANSACTION_TYPE_LABELS,
    TransactionType,
)


class WheelSafeComboBox(QComboBox):
    """An inline editor that lets wheel events continue to the table."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class SelectableTextLabel(QLabel):
    """Table text that supports normal mouse selection and Ctrl+C."""

    def __init__(self, text: str, *, centered: bool = False):
        super().__init__(text)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setContentsMargins(14, 0, 14, 0)
        self.setAlignment(
            (Qt.AlignmentFlag.AlignHCenter if centered else Qt.AlignmentFlag.AlignLeft)
            | Qt.AlignmentFlag.AlignVCenter
        )


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
    transaction_type_changed = Signal(int, object)
    deletion_changed = Signal(int, bool)
    create_rule_requested = Signal(int)

    def __init__(
        self,
        transaction_id: int,
        transaction_date: date,
        description: str,
        amount: Decimal,
        transaction_type: TransactionType | None,
        imported_at: datetime,
        category_id: int | None,
        account_name: str,
        is_deleted: bool,
        categories: list[tuple[int, str, str]],
        parent=None,
    ):
        super().__init__(parent)
        self.transaction_id = transaction_id
        self.saved_transaction_type = transaction_type
        self.saved_category_id = category_id
        self.description = description
        self.account_name = account_name
        self.category_colors = {
            available_id: color for available_id, _, color in categories
        }
        self.categories = categories
        self.amount = amount
        self.is_deleted = is_deleted

        self.date_label = SelectableTextLabel(
            f"{transaction_date:%b} {transaction_date.day}, {transaction_date.year}"
        )
        self.description_label = SelectableTextLabel(description)
        self.description_label.setToolTip(description)
        self.amount_label = SelectableTextLabel(
            f"-${abs(amount):,.2f}" if amount < 0 else f"${amount:,.2f}",
            centered=True,
        )
        self.amount_label.setStyleSheet(
            f"color: {'#fb7977' if amount < 0 else '#63dba0' if amount > 0 else '#cbd4e1'};"
        )
        self.account_label = SelectableTextLabel(account_name)
        self.imported_label = SelectableTextLabel(
            f"{imported_at:%b} {imported_at.day}, {imported_at:%I:%M %p}"
        )
        self.imported_label.setStyleSheet("color: #9eabba;")

        self.transaction_type_combo = WheelSafeComboBox()
        if transaction_type is None:
            self.transaction_type_combo.addItem("Needs review", None)
        for available_type, label in TRANSACTION_TYPE_LABELS.items():
            self.transaction_type_combo.addItem(label, available_type)
        self.transaction_type_combo.setCurrentIndex(
            self.transaction_type_combo.findData(transaction_type)
        )
        self.transaction_type_combo.setEnabled(not is_deleted)
        self.transaction_type_combo.currentIndexChanged.connect(
            self._transaction_type_selected
        )

        self.category_combo = WheelSafeComboBox()
        self._set_category_options(transaction_type, category_id)
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
        if is_deleted:
            self.action_button.setIcon(_action_icon(True))
            self.action_button.setIconSize(QSize(18, 18))
        else:
            self.action_button.setText("⋯")
        self.action_button.setAccessibleName(
            "Restore transaction" if is_deleted else "Transaction actions"
        )
        self.action_button.setToolTip(
            "Restore this transaction" if is_deleted else "Transaction actions"
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
        self.action_button.clicked.connect(self._show_actions)
        self.action_cell = QWidget()
        action_layout = QHBoxLayout(self.action_cell)
        action_layout.setContentsMargins(4, 0, 4, 0)
        action_layout.addWidget(self.action_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.cells = (
            self.date_label,
            self.description_label,
            self.amount_label,
            self.account_label,
            self.transaction_type_combo,
            self.category_cell,
            self.imported_label,
            self.action_cell,
        )

    def _show_actions(self) -> None:
        if self.is_deleted:
            self.deletion_changed.emit(self.transaction_id, False)
            return
        menu = QMenu(self.action_button)
        create_rule = menu.addAction("Create Rule From Transaction")
        remove = menu.addAction("Remove Transaction")
        selected = menu.exec(
            self.action_button.mapToGlobal(QPoint(0, self.action_button.height()))
        )
        if selected == create_rule:
            self.create_rule_requested.emit(self.transaction_id)
        elif selected == remove:
            self.deletion_changed.emit(self.transaction_id, True)

    @staticmethod
    def _empty_category_label(transaction_type: TransactionType | None) -> str:
        if transaction_type in CATEGORY_FREE_TRANSACTION_TYPES:
            return "—"
        return "Uncategorized"

    def _set_category_options(
        self,
        transaction_type: TransactionType | None,
        category_id: int | None,
    ) -> None:
        with QSignalBlocker(self.category_combo):
            self.category_combo.clear()
            self.category_combo.addItem(
                self._empty_category_label(transaction_type), None
            )
            for available_id, name, _ in self.categories:
                if transaction_type in CATEGORY_FREE_TRANSACTION_TYPES:
                    continue
                if (
                    transaction_type == TransactionType.INCOME
                    and name not in INCOME_CATEGORY_NAMES
                ):
                    continue
                if (
                    transaction_type == TransactionType.EXPENSE
                    and name in INCOME_CATEGORY_NAMES
                ):
                    continue
                self.category_combo.addItem(name, available_id)
            selected = self.category_combo.findData(category_id)
            self.category_combo.setCurrentIndex(max(0, selected))
        self.category_combo.setEnabled(
            not self.is_deleted
            and transaction_type not in CATEGORY_FREE_TRANSACTION_TYPES
        )
        self._style_category()

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
            min(152, max(90, self.category_combo.fontMetrics().horizontalAdvance(name) + 30))
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

    def _transaction_type_selected(self, index: int) -> None:
        transaction_type = self.transaction_type_combo.itemData(index)
        self._set_category_options(
            transaction_type,
            self.category_combo.currentData(),
        )
        if transaction_type != self.saved_transaction_type:
            self.transaction_type_changed.emit(self.transaction_id, transaction_type)

    def mark_saved(
        self,
        transaction_type: TransactionType | None,
        category_id: int | None,
    ) -> None:
        self.saved_transaction_type = transaction_type
        self.saved_category_id = category_id

    def restore_assignment(self) -> None:
        with QSignalBlocker(self.transaction_type_combo):
            self.transaction_type_combo.setCurrentIndex(
                self.transaction_type_combo.findData(self.saved_transaction_type)
            )
        self._set_category_options(
            self.saved_transaction_type,
            self.saved_category_id,
        )
