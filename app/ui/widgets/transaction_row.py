from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import QObject, QPoint, QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from app.ui.widgets.account_badge import AccountBadge
from app.ui.widgets.combo_box import AppComboBox
from app.ui.theme import (
    awesome_icon,
    category_icon_name,
    set_label_icon,
    spaced_text_icon,
    spaced_text_icon_size,
    transaction_type_icon,
)

from app.utils.constants import (
    CATEGORY_FREE_TRANSACTION_TYPES,
    INCOME_CATEGORY_NAMES,
    TRANSACTION_TYPE_LABELS,
    TransactionType,
)


ROW_TRANSACTION_TYPE_LABELS = {
    TransactionType.CREDIT_CARD_PAYMENT: "CC Payment",
    TransactionType.REFUND_REIMBURSEMENT: "Refund / Reimb.",
}


class WheelSafeComboBox(AppComboBox):
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
        self.setContentsMargins(10, 0, 10, 0)
        self.setAlignment(
            (Qt.AlignmentFlag.AlignHCenter if centered else Qt.AlignmentFlag.AlignLeft)
            | Qt.AlignmentFlag.AlignVCenter
        )


class TransactionRow(QObject):
    category_changed = Signal(int, object)
    transaction_type_changed = Signal(int, object)
    deletion_changed = Signal(int, bool)
    create_rule_requested = Signal(int)

    COMPACT_CELL_HORIZONTAL_PADDING = 8
    ACTION_BUTTON_SIZE = 34
    ACTION_COLUMN_WIDTH = 80

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
        institution: str,
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
        self.description_label.setContentsMargins(0, 0, 0, 0)
        self.description_label.setToolTip(description)
        self.description_cell = QWidget()
        self.description_cell.setObjectName("tableCell")
        description_layout = QHBoxLayout(self.description_cell)
        description_layout.setContentsMargins(12, 0, 8, 0)
        description_layout.setSpacing(8)
        description_icon = QLabel()
        category = next(
            (
                (name, color)
                for available_id, name, color in categories
                if available_id == category_id
            ),
            None,
        )
        if category is None:
            icon_name = "fa6s.receipt"
            icon_color = "#4aa3ff"
        else:
            icon_name = category_icon_name(category[0])
            icon_color = category[1]
        set_label_icon(description_icon, icon_name, color=icon_color, size=18)
        description_layout.addWidget(description_icon)
        description_layout.addWidget(self.description_label, 1)
        self.amount_label = SelectableTextLabel(
            f"-${abs(amount):,.2f}" if amount < 0 else f"${amount:,.2f}",
            centered=True,
        )
        self.amount_label.setStyleSheet(
            f"color: {'#fb7977' if amount < 0 else '#63dba0' if amount > 0 else '#cbd4e1'};"
        )
        self.account_cell = AccountBadge(account_name, institution, icon_size=22)
        self.imported_label = SelectableTextLabel(
            f"{imported_at:%b} {imported_at.day}, {imported_at:%I:%M %p}"
        )
        self.imported_label.setContentsMargins(
            self.COMPACT_CELL_HORIZONTAL_PADDING,
            0,
            self.COMPACT_CELL_HORIZONTAL_PADDING,
            0,
        )
        self.imported_label.setStyleSheet("color: #a8adb4;")

        self.transaction_type_combo = WheelSafeComboBox()
        self.transaction_type_combo.setIconSize(spaced_text_icon_size())
        self.transaction_type_combo.setObjectName("transactionTypeCombo")
        self.transaction_type_combo.setFixedHeight(34)
        self.transaction_type_combo.setMinimumWidth(0)
        self.transaction_type_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        if transaction_type is None:
            self.transaction_type_combo.addItem(
                spaced_text_icon(
                    awesome_icon("fa6s.circle-exclamation", color="#ffbd4a")
                ),
                "Needs review",
                None,
            )
        for available_type, label in TRANSACTION_TYPE_LABELS.items():
            row_label = ROW_TRANSACTION_TYPE_LABELS.get(available_type, label)
            self.transaction_type_combo.addItem(
                spaced_text_icon(transaction_type_icon(available_type)),
                row_label,
                available_type,
            )
            self.transaction_type_combo.setItemData(
                self.transaction_type_combo.count() - 1,
                label,
                Qt.ItemDataRole.ToolTipRole,
            )
        longest_transaction_type = max(
            (
                self.transaction_type_combo.fontMetrics().horizontalAdvance(label)
                for label in TRANSACTION_TYPE_LABELS.values()
            ),
            default=0,
        )
        self.transaction_type_combo.view().setMinimumWidth(
            longest_transaction_type + 72
        )
        self.transaction_type_combo.setCurrentIndex(
            self.transaction_type_combo.findData(transaction_type)
        )
        self.transaction_type_combo.setEnabled(not is_deleted)
        self.transaction_type_combo.currentIndexChanged.connect(
            self._transaction_type_selected
        )

        self.transaction_type_cell = QWidget()
        self.transaction_type_cell.setObjectName("tableCell")
        transaction_type_layout = QHBoxLayout(self.transaction_type_cell)
        transaction_type_layout.setContentsMargins(6, 0, 6, 0)
        transaction_type_layout.setSpacing(0)
        transaction_type_layout.addWidget(self.transaction_type_combo)

        self.category_combo = WheelSafeComboBox()
        self.category_combo.setIconSize(spaced_text_icon_size())
        self._set_category_options(transaction_type, category_id)
        self._style_category()
        self.category_combo.currentIndexChanged.connect(self._category_selected)

        self.category_cell = QWidget()
        category_layout = QHBoxLayout(self.category_cell)
        category_layout.setContentsMargins(6, 0, 6, 0)
        category_layout.setSpacing(0)
        category_layout.addWidget(self.category_combo)

        self.action_button = QPushButton()
        self.action_button.setObjectName("transactionActionButton")
        self.action_button.setIcon(
            awesome_icon(
                "fa6s.rotate-left" if is_deleted else "fa6s.ellipsis",
                color="#b9bec5",
            )
        )
        self.action_button.setIconSize(QSize(18, 18))
        self.action_button.setAccessibleName(
            "Restore transaction" if is_deleted else "Transaction actions"
        )
        self.action_button.setToolTip(
            "Restore this transaction" if is_deleted else "Transaction actions"
        )
        self.action_button.setFixedSize(
            self.ACTION_BUTTON_SIZE, self.ACTION_BUTTON_SIZE
        )
        self.action_button.setStyleSheet("""
            QPushButton#transactionActionButton {
                background: #20242a;
                border: 1px solid #3a414a;
                border-radius: 8px;
                padding: 0;
            }
            QPushButton#transactionActionButton:hover { background: #2b3036; }
        """)
        self.action_button.clicked.connect(self._show_actions)
        self.action_cell = QWidget()
        action_layout = QHBoxLayout(self.action_cell)
        action_layout.setContentsMargins(
            self.COMPACT_CELL_HORIZONTAL_PADDING,
            0,
            self.COMPACT_CELL_HORIZONTAL_PADDING,
            0,
        )
        action_layout.addWidget(self.action_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.cells = (
            self.date_label,
            self.description_cell,
            self.amount_label,
            self.account_cell,
            self.transaction_type_cell,
            self.category_cell,
            self.imported_label,
            self.action_cell,
        )

    def _show_actions(self) -> None:
        if self.is_deleted:
            self.deletion_changed.emit(self.transaction_id, False)
            return
        menu = QMenu(self.action_button)
        create_rule = menu.addAction(
            awesome_icon("fa6s.wand-magic-sparkles", color="#b9bec5"),
            "Create Rule From Transaction",
        )
        remove = menu.addAction(
            awesome_icon("fa6s.trash", color="#ff8587"),
            "Remove Transaction",
        )
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
                spaced_text_icon(awesome_icon("fa6s.minus", color="#ffffff")),
                self._empty_category_label(transaction_type),
                None,
            )
            for available_id, name, _color in self.categories:
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
                self.category_combo.addItem(
                    spaced_text_icon(awesome_icon(
                        category_icon_name(name),
                        color="#ffffff",
                    )),
                    name,
                    available_id,
                )
            for index in range(self.category_combo.count()):
                self.category_combo.setItemData(
                    index,
                    QColor("#ffffff"),
                    Qt.ItemDataRole.ForegroundRole,
                )
            longest_label = max(
                (
                    self.category_combo.fontMetrics().horizontalAdvance(
                        self.category_combo.itemText(index)
                    )
                    for index in range(self.category_combo.count())
                ),
                default=0,
            )
            self.category_combo.view().setMinimumWidth(
                max(220, longest_label + 64)
            )
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
        color = QColor(self.category_colors.get(category_id, "#34383e"))
        background = color.name()
        border = color.darker(125).name() if category_id is not None else "#545a62"
        self.category_combo.setMinimumWidth(110)
        self.category_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.category_combo.setFixedHeight(34)
        self.category_combo.setToolTip(name)
        self.category_combo.setStyleSheet(f"""
            QComboBox {{
                color: #ffffff;
                background: {background};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 4px 10px;
                font-size: 12px;
            }}
            QComboBox:hover {{ border-color: #737980; }}
            QComboBox:focus {{ border: 1px solid #4c99f3; }}
            QComboBox::drop-down {{ border: none; width: 0px; }}
            QComboBox QAbstractItemView {{
                color: #e0e2e5;
                background: #22262b;
                border: 1px solid #40464e;
                selection-background-color: #3b4858;
                selection-color: #ffffff;
                padding: 0;
                margin: 0;
                outline: none;
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
