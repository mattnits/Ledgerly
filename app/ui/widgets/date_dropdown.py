from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)


class DateDropdownItemDelegate(QStyledItemDelegate):
    """Paint date choices without the platform's selected-item checkmark."""

    ROW_HEIGHT = 38

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        row_rect = option.rect.adjusted(4, 2, -4, -2)
        if selected:
            painter.setBrush(QColor("#4468f2"))
            painter.setPen(QColor("#5d7cff"))
            painter.drawRoundedRect(row_rect, 7, 7)
        elif hovered:
            painter.setBrush(QColor("#282e36"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(row_rect, 7, 7)

        icon_rect = QRect(row_rect.left() + 10, row_rect.center().y() - 8, 16, 16)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QIcon) and not icon.isNull():
            mode = QIcon.Mode.Selected if selected else QIcon.Mode.Normal
            icon.paint(
                painter,
                icon_rect,
                Qt.AlignmentFlag.AlignCenter,
                mode,
                QIcon.State.Off,
            )

        painter.setPen(QColor("#ffffff" if selected else "#e5e8ee"))
        painter.setFont(option.font)
        text_rect = row_rect.adjusted(38, 0, -10, 0)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            str(index.data(Qt.ItemDataRole.DisplayRole) or ""),
        )
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        size = super().sizeHint(option, index)
        size.setHeight(self.ROW_HEIGHT)
        return size


class DateDropdown(QComboBox):
    """A compact dark date selector with a calendar-led popup list."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dateDropdown")
        self.setIconSize(QSize(16, 16))
        self.setMinimumHeight(40)

        popup = QListView(self)
        popup.setObjectName("dateDropdownList")
        popup.setMouseTracking(True)
        popup.setUniformItemSizes(True)
        popup.setSpacing(0)
        popup.setItemDelegate(DateDropdownItemDelegate(popup))
        self.setView(popup)

        # QComboBox wraps custom views in a platform popup window. On Windows,
        # that wrapper otherwise paints an opaque grey rectangle around the
        # rounded list, so leave it transparent and let the list draw itself.
        popup_container = popup.window()
        popup_container.setObjectName("dateDropdownPopup")
        popup_container.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        popup_container.setWindowFlags(
            popup_container.windowFlags()
            | Qt.WindowType.NoDropShadowWindowHint
        )
        popup_container.setAutoFillBackground(False)
        popup_container.setStyleSheet("""
            QFrame#dateDropdownPopup {
                background: transparent;
                border: none;
            }
        """)

        self.setStyleSheet("""
            QComboBox#dateDropdown {
                color: #e8ebf1;
                background: #171b21;
                border: 1px solid #343c48;
                border-radius: 9px;
                padding: 8px 34px 8px 12px;
                font-size: 13px;
            }
            QComboBox#dateDropdown:hover {
                background: #1c2128;
                border-color: #465161;
            }
            QComboBox#dateDropdown:focus { border-color: #4c76ff; }
            QComboBox#dateDropdown::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 32px;
                border: none;
                background: transparent;
            }
            QListView#dateDropdownList {
                color: #e5e8ee;
                background: #171b21;
                border: 1px solid #343c48;
                border-radius: 9px;
                padding: 4px;
                outline: none;
            }
        """)
