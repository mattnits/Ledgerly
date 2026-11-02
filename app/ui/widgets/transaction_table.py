from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QRect,
    QSignalBlocker,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemDelegate,
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
)

from app.services.transactions import TransactionRowData
from app.ui.theme import awesome_icon, brand_icon, category_icon_name, transaction_type_icon
from app.ui.widgets.transaction_row import WheelSafeComboBox
from app.utils.constants import (
    CATEGORY_FREE_TRANSACTION_TYPES,
    INCOME_CATEGORY_NAMES,
    TRANSACTION_TYPE_LABELS,
    TransactionType,
)


@dataclass
class TransactionTableRow:
    transaction_id: int
    transaction_date: date
    description: str
    amount: Decimal
    transaction_type: TransactionType | None
    imported_at: datetime
    category_id: int | None
    account_name: str
    institution: str
    is_deleted: bool
    confirmed_transaction_type: TransactionType | None
    confirmed_category_id: int | None
    pending: bool = False

    @classmethod
    def from_data(cls, data: TransactionRowData) -> "TransactionTableRow":
        return cls(
            transaction_id=data.id,
            transaction_date=data.transaction_date,
            description=data.description,
            amount=data.amount,
            transaction_type=data.transaction_type,
            imported_at=data.imported_at,
            category_id=data.category_id,
            account_name=data.account_name,
            institution=data.institution,
            is_deleted=data.is_deleted,
            confirmed_transaction_type=data.transaction_type,
            confirmed_category_id=data.category_id,
        )


class TransactionTableModel(QAbstractTableModel):
    assignment_requested = Signal(int, object, object)

    HEADERS = (
        "Date",
        "Description",
        "Amount",
        "Account",
        "Transaction Type",
        "Category",
        "Imported At",
        "Action",
    )
    TYPE_COLUMN = 4
    CATEGORY_COLUMN = 5
    ACTION_COLUMN = 7
    ROW_ROLE = Qt.ItemDataRole.UserRole + 1
    COLOR_ROLE = Qt.ItemDataRole.UserRole + 2
    PENDING_ROLE = Qt.ItemDataRole.UserRole + 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[TransactionTableRow] = []
        self.categories: list[tuple[int, str, str]] = []
        self._category_by_id: dict[int, tuple[str, str]] = {}
        self._sort_column = 0
        self._sort_descending = True

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            label = self.HEADERS[section]
            if section == self._sort_column:
                return f"{label} {'↓' if self._sort_descending else '↑'}"
            return label
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        row = self.rows[index.row()]
        column = index.column()
        if role == self.ROW_ROLE:
            return row
        if role == self.PENDING_ROLE:
            return row.pending
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if role == Qt.ItemDataRole.EditRole:
                if column == self.TYPE_COLUMN:
                    return row.transaction_type
                if column == self.CATEGORY_COLUMN:
                    return row.category_id
            values = (
                f"{row.transaction_date:%b} {row.transaction_date.day}, "
                f"{row.transaction_date.year}",
                row.description,
                f"-${abs(row.amount):,.2f}" if row.amount < 0 else f"${row.amount:,.2f}",
                row.account_name,
                TRANSACTION_TYPE_LABELS.get(row.transaction_type, "Needs review"),
                self.category_name(row.category_id, row.transaction_type),
                f"{row.imported_at:%b} {row.imported_at.day}, {row.imported_at:%I:%M %p}",
                "Restore" if row.is_deleted else "More actions",
            )
            return values[column]
        if role == Qt.ItemDataRole.DecorationRole:
            if column == 1:
                name, color = self._category_by_id.get(
                    row.category_id, ("", "#4aa3ff")
                )
                return awesome_icon(
                    category_icon_name(name) if name else "fa6s.receipt",
                    color=color,
                )
            if column == 3:
                return brand_icon(row.institution, size=22)
            if column == self.TYPE_COLUMN:
                return transaction_type_icon(row.transaction_type)
            if column == self.CATEGORY_COLUMN:
                name, _color = self._category_by_id.get(row.category_id, ("", ""))
                return awesome_icon(category_icon_name(name), color="#ffffff")
            if column == self.ACTION_COLUMN:
                return awesome_icon(
                    "fa6s.rotate-left" if row.is_deleted else "fa6s.ellipsis",
                    color="#b9bec5",
                )
        if role == Qt.ItemDataRole.ForegroundRole:
            if column == 2:
                return QColor("#fb7977" if row.amount < 0 else "#63dba0")
            if column == 6:
                return QColor("#a8adb4")
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if column in (2, self.TYPE_COLUMN, self.CATEGORY_COLUMN, self.ACTION_COLUMN):
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        if role == Qt.ItemDataRole.ToolTipRole:
            if column == 1:
                return row.description
            if column == 3:
                return f"{row.account_name} · {row.institution}"
            if column in (self.TYPE_COLUMN, self.CATEGORY_COLUMN):
                return self.data(index, Qt.ItemDataRole.DisplayRole)
            if column == self.ACTION_COLUMN:
                return self.data(index, Qt.ItemDataRole.DisplayRole)
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return self.data(index, Qt.ItemDataRole.DisplayRole)
        if role == self.COLOR_ROLE and column == self.CATEGORY_COLUMN:
            return QColor(self._category_by_id.get(row.category_id, ("", "#34383e"))[1])
        return None

    def flags(self, index):
        flags = super().flags(index)
        if not index.isValid():
            return flags
        row = self.rows[index.row()]
        if not row.is_deleted and index.column() == self.TYPE_COLUMN:
            flags |= Qt.ItemFlag.ItemIsEditable
        if (
            not row.is_deleted
            and index.column() == self.CATEGORY_COLUMN
            and row.transaction_type not in CATEGORY_FREE_TRANSACTION_TYPES
        ):
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        row = self.rows[index.row()]
        if index.column() == self.TYPE_COLUMN:
            if value == row.transaction_type:
                return False
            row.transaction_type = value
            if value in CATEGORY_FREE_TRANSACTION_TYPES:
                row.category_id = None
        elif index.column() == self.CATEGORY_COLUMN:
            if value == row.category_id:
                return False
            row.category_id = value
        else:
            return False
        row.pending = True
        self.dataChanged.emit(
            self.index(index.row(), 1),
            self.index(index.row(), self.CATEGORY_COLUMN),
        )
        self.assignment_requested.emit(
            row.transaction_id,
            row.transaction_type,
            row.category_id,
        )
        return True

    def replace_rows(self, rows) -> None:
        self.beginResetModel()
        self.rows.clear()
        self.rows.extend(TransactionTableRow.from_data(row) for row in rows)
        self.endResetModel()

    def append_rows(self, rows) -> None:
        items = [TransactionTableRow.from_data(row) for row in rows]
        if not items:
            return
        first = len(self.rows)
        self.beginInsertRows(QModelIndex(), first, first + len(items) - 1)
        self.rows.extend(items)
        self.endInsertRows()

    def clear(self) -> None:
        self.replace_rows(())

    def set_categories(self, categories: list[tuple[int, str, str]]) -> None:
        self.categories = list(categories)
        self._category_by_id = {
            category_id: (name, color)
            for category_id, name, color in self.categories
        }
        if self.rows:
            self.dataChanged.emit(
                self.index(0, 1),
                self.index(len(self.rows) - 1, self.CATEGORY_COLUMN),
            )

    def set_sort(self, column: int, descending: bool) -> None:
        old = self._sort_column
        self._sort_column = column
        self._sort_descending = descending
        self.headerDataChanged.emit(
            Qt.Orientation.Horizontal,
            min(old, column),
            max(old, column),
        )

    def category_name(
        self,
        category_id: int | None,
        transaction_type: TransactionType | None,
    ) -> str:
        if transaction_type in CATEGORY_FREE_TRANSACTION_TYPES:
            return "—"
        return self._category_by_id.get(category_id, ("Uncategorized", ""))[0]

    def category_choices(self, row: TransactionTableRow):
        for category_id, name, color in self.categories:
            if (
                row.transaction_type == TransactionType.INCOME
                and name not in INCOME_CATEGORY_NAMES
            ):
                continue
            if row.transaction_type == TransactionType.EXPENSE and name in INCOME_CATEGORY_NAMES:
                continue
            yield category_id, name, color

    def mark_saved(
        self,
        transaction_id: int,
        transaction_type: TransactionType | None,
        category_id: int | None,
    ) -> None:
        found = self.find_row(transaction_id)
        if found is None:
            return
        index, row = found
        row.confirmed_transaction_type = transaction_type
        row.confirmed_category_id = category_id
        if (row.transaction_type, row.category_id) == (transaction_type, category_id):
            row.pending = False
        self.dataChanged.emit(self.index(index, 1), self.index(index, 5))

    def restore_confirmed(self, transaction_id: int) -> None:
        found = self.find_row(transaction_id)
        if found is None:
            return
        index, row = found
        row.transaction_type = row.confirmed_transaction_type
        row.category_id = row.confirmed_category_id
        row.pending = False
        self.dataChanged.emit(self.index(index, 1), self.index(index, 5))

    def remove_transaction(self, transaction_id: int) -> bool:
        found = self.find_row(transaction_id)
        if found is None:
            return False
        index, _row = found
        self.beginRemoveRows(QModelIndex(), index, index)
        del self.rows[index]
        self.endRemoveRows()
        return True

    def find_row(self, transaction_id: int):
        return next(
            (
                (index, row)
                for index, row in enumerate(self.rows)
                if row.transaction_id == transaction_id
            ),
            None,
        )


class _TransactionEditorCombo(WheelSafeComboBox):
    popup_dismissed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent, compact=True)
        self._committing = False

    def hidePopup(self) -> None:
        was_visible = self._popup_window.isVisible()
        super().hidePopup()
        if was_visible and not self._committing:
            QTimer.singleShot(0, self.popup_dismissed.emit)


class TransactionItemDelegate(QStyledItemDelegate):
    ACTION_BUTTON_WIDTH = 52
    ACTION_BUTTON_HEIGHT = 32
    ACTION_ICON_SIZE = 18

    def createEditor(self, parent, option, index):
        if index.column() not in (
            TransactionTableModel.TYPE_COLUMN,
            TransactionTableModel.CATEGORY_COLUMN,
        ):
            return None
        editor = _TransactionEditorCombo(parent=parent)
        editor.setObjectName(
            "transactionTypeCombo"
            if index.column() == TransactionTableModel.TYPE_COLUMN
            else "transactionCategoryCombo"
        )
        editor.setMinimumWidth(0)
        model: TransactionTableModel = index.model()
        row = model.rows[index.row()]
        if index.column() == TransactionTableModel.TYPE_COLUMN:
            if row.transaction_type is None:
                editor.addItem(
                    awesome_icon("fa6s.circle-exclamation", color="#ffbd4a"),
                    "Needs review",
                    None,
                )
            for transaction_type, label in TRANSACTION_TYPE_LABELS.items():
                editor.addItem(
                    transaction_type_icon(transaction_type),
                    label,
                    transaction_type,
                )
        else:
            editor.addItem(
                awesome_icon("fa6s.minus", color="#ffffff"),
                "Uncategorized",
                None,
            )
            for category_id, name, _color in model.category_choices(row):
                editor.addItem(
                    awesome_icon(category_icon_name(name), color="#ffffff"),
                    name,
                    category_id,
                )
                editor.setItemData(
                    editor.count() - 1,
                    QColor("#ffffff"),
                    Qt.ItemDataRole.ForegroundRole,
                )
        background = QColor("#20242a")
        if index.column() == TransactionTableModel.CATEGORY_COLUMN:
            background = index.data(TransactionTableModel.COLOR_ROLE) or QColor(
                "#34383e"
            )
        border = background.lighter(125)
        editor.setStyleSheet(f"""
            QComboBox#{editor.objectName()} {{
                color: #ffffff;
                background: {background.name()};
                border: 1px solid {border.name()};
                border-radius: 9px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QComboBox#{editor.objectName()}:hover {{
                border-color: #737980;
            }}
            QComboBox#{editor.objectName()}::drop-down {{
                border: none;
                width: 0;
            }}
        """)
        editor.currentIndexChanged.connect(lambda _index: self._commit(editor))
        editor.popup_dismissed.connect(lambda: self._cancel(editor))
        return editor

    def setEditorData(self, editor, index) -> None:
        with QSignalBlocker(editor):
            selected = editor.findData(index.data(Qt.ItemDataRole.EditRole))
            editor.setCurrentIndex(max(0, selected))
        QTimer.singleShot(0, editor.showPopup)

    def setModelData(self, editor, model, index) -> None:
        model.setData(index, editor.currentData(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, _index) -> None:
        editor.setGeometry(option.rect.adjusted(6, 9, -6, -9))

    def _commit(self, editor) -> None:
        editor._committing = True
        self.commitData.emit(editor)
        self.closeEditor.emit(editor)

    def _cancel(self, editor) -> None:
        if editor._committing:
            return
        self.closeEditor.emit(
            editor,
            QAbstractItemDelegate.EndEditHint.RevertModelCache,
        )

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        column = index.column()
        if column not in (
            TransactionTableModel.TYPE_COLUMN,
            TransactionTableModel.CATEGORY_COLUMN,
            TransactionTableModel.ACTION_COLUMN,
        ):
            super().paint(painter, option, index)
            return
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            background = (
                option.palette.alternateBase()
                if index.row() % 2
                else option.palette.base()
            )
            painter.fillRect(option.rect, background)
        if column == TransactionTableModel.ACTION_COLUMN:
            icon = index.data(Qt.ItemDataRole.DecorationRole)
            button_rect = QRect(
                0,
                0,
                self.ACTION_BUTTON_WIDTH,
                self.ACTION_BUTTON_HEIGHT,
            )
            button_rect.moveCenter(option.rect.center())
            if option.state & QStyle.StateFlag.State_MouseOver:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(QPen(QColor("#414a55"), 1))
                painter.setBrush(QColor("#252b33"))
                painter.drawRoundedRect(button_rect, 9, 9)
            icon_rect = QRect(0, 0, self.ACTION_ICON_SIZE, self.ACTION_ICON_SIZE)
            icon_rect.moveCenter(option.rect.center())
            icon.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter)
            painter.setPen(QColor("#262c34"))
            painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
            painter.restore()
            return
        rect = option.rect.adjusted(6, 9, -6, -9)
        background = QColor("#20242a")
        if column == TransactionTableModel.CATEGORY_COLUMN:
            background = index.data(TransactionTableModel.COLOR_ROLE) or QColor("#34383e")
        painter.setPen(QPen(background.lighter(125), 1))
        painter.setBrush(background)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawRoundedRect(rect, 9, 9)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        icon_rect = QRect(rect.left() + 9, rect.center().y() - 8, 16, 16)
        icon.paint(painter, icon_rect)
        painter.setPen(QColor("#ffffff"))
        text_rect = rect.adjusted(31, 0, -10, 0)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            str(index.data(Qt.ItemDataRole.DisplayRole)),
        )
        if index.data(TransactionTableModel.PENDING_ROLE):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#64a8ff"))
            painter.drawEllipse(rect.right() - 8, rect.top() + 5, 4, 4)
        painter.setPen(QColor("#262c34"))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.restore()


class TransactionTableView(QTableView):
    action_requested = Signal(int, object)

    def __init__(self, model: TransactionTableModel, parent=None):
        super().__init__(parent)
        self.setObjectName("transactionTable")
        self.setModel(model)
        self.setItemDelegate(TransactionItemDelegate(self))
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setMouseTracking(True)
        self.setShowGrid(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWordWrap(False)
        self.setMinimumHeight(360)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(52)
        header = self.horizontalHeader()
        header.setMinimumSectionSize(48)
        header.setFixedHeight(48)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.clicked.connect(self._activate_index)

    def _activate_index(self, index) -> None:
        if index.column() in (
            TransactionTableModel.TYPE_COLUMN,
            TransactionTableModel.CATEGORY_COLUMN,
        ) and index.flags() & Qt.ItemFlag.ItemIsEditable:
            self.edit(index)
            self.clearSelection()
            return
        if index.column() == TransactionTableModel.ACTION_COLUMN:
            self.clearSelection()
            row = index.data(TransactionTableModel.ROW_ROLE)
            point = self.viewport().mapToGlobal(self.visualRect(index).bottomLeft())
            self.action_requested.emit(row.transaction_id, point)

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            index = self.currentIndex()
            if index.isValid():
                QApplication.clipboard().setText(
                    str(index.data(Qt.ItemDataRole.DisplayRole) or "")
                )
                event.accept()
                return
        super().keyPressEvent(event)
