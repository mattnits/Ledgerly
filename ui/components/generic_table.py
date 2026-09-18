from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)


class GenericTable(QTableWidget):
    def __init__(self, columns: Sequence[str], rows: Sequence[Sequence[str | QWidget]] = (), parent=None):
        super().__init__(0, len(columns), parent)
        self.setHorizontalHeaderLabels(list(columns))
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWordWrap(False)
        self.setFrameShape(QTableWidget.Shape.NoFrame)
        self.setMinimumHeight(360)

        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(37)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setMinimumSectionSize(96)
        self.horizontalHeader().setFixedHeight(44)
        self.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        self.setStyleSheet("""
            QTableWidget {
                background: #1f2329;
                alternate-background-color: #22262d;
                color: #cbd4e1;
                border: none;
                font-size: 12px;
                selection-background-color: #283a50;
                selection-color: #eef5ff;
            }
            QHeaderView::section {
                background: #23272e;
                color: #dce4ef;
                border: none;
                border-bottom: 1px solid #343a43;
                padding: 10px 14px;
                font-weight: 700;
            }
            QTableWidget::item {
                padding: 0 14px;
                border-bottom: 1px solid #313740;
            }
            QScrollBar:vertical {
                background: #1f2329;
                width: 9px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #4b5563;
                border-radius: 4px;
                min-height: 24px;
            }
        """)
        self.set_rows(rows)

    def set_rows(self, rows: Sequence[Sequence[str | QWidget]]) -> None:
        self.setRowCount(0)
        self.append_rows(rows)

    def append_rows(self, rows: Sequence[Sequence[str | QWidget]]) -> None:
        for cells in rows:
            if len(cells) != self.columnCount():
                raise ValueError("Row length must match the number of columns")
            row_number = self.rowCount()
            self.insertRow(row_number)
            for column_number, cell in enumerate(cells):
                if isinstance(cell, QWidget):
                    self.setCellWidget(row_number, column_number, cell)
                else:
                    item = QTableWidgetItem(str(cell))
                    if column_number == 0:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                    self.setItem(row_number, column_number, item)
