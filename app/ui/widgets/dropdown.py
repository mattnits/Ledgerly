"""Shared list popup for Ledgerly's QComboBox-based selectors."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFrame, QListView, QStyle,
    QSizePolicy, QStyledItemDelegate, QToolTip, QVBoxLayout, QWidget,
)

from app.ui.theme import (
    DROPDOWN, DROPDOWN_MAX_ROWS, DROPDOWN_POPUP_STYLE, DROPDOWN_ROW_HEIGHT,
)


class DropdownItemDelegate(QStyledItemDelegate):
    """Uniform, elided rows without native menu checks or menu spacing."""

    ROW_HEIGHT = DROPDOWN_ROW_HEIGHT

    @staticmethod
    def content_width(index, metrics) -> int:
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        icon_width = 24 if isinstance(icon, QIcon) and not icon.isNull() else 0
        return metrics.horizontalAdvance(text) + 24 + icon_width

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        width = self.content_width(index, option.fontMetrics)
        view = self.parent()
        if isinstance(view, QListView):
            # QListView otherwise lays out long rows wider than its viewport,
            # even with horizontal scrolling disabled, defeating elision.
            width = min(width, view.viewport().width())
        return QSize(
            width,
            max(self.ROW_HEIGHT, option.fontMetrics.height() + 12),
        )

    @staticmethod
    def _text_rect(rect, index):
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        inset = 36 if isinstance(icon, QIcon) and not icon.isNull() else 12
        return rect.adjusted(inset, 0, -12, 0)

    def paint(self, painter, option, index) -> None:
        enabled = bool(index.flags() & Qt.ItemFlag.ItemIsEnabled)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        background = DROPDOWN['background']
        if enabled:
            background = DROPDOWN['selected'] if selected else DROPDOWN['hover'] if hovered else background
        painter.save()
        painter.setClipRect(option.rect)
        painter.fillRect(option.rect, QColor(background))
        painter.setFont(option.font)
        painter.setPen(QColor(DROPDOWN['text'] if enabled else DROPDOWN['muted']))
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QIcon) and not icon.isNull():
            icon.paint(
                painter, QRect(option.rect.left() + 12, option.rect.center().y() - 8, 16, 16),
                Qt.AlignmentFlag.AlignCenter,
                QIcon.Mode.Normal if enabled else QIcon.Mode.Disabled,
            )
        text_rect = self._text_rect(option.rect, index)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        painter.drawText(
            text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            option.fontMetrics.elidedText(text, Qt.TextElideMode.ElideRight, max(0, text_rect.width())),
        )
        painter.restore()

    def helpEvent(self, event, view, option, index) -> bool:  # noqa: N802
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        tooltip = index.data(Qt.ItemDataRole.ToolTipRole)
        if not tooltip and option.fontMetrics.horizontalAdvance(text) > self._text_rect(option.rect, index).width():
            tooltip = text
        if tooltip:
            QToolTip.showText(event.globalPos(), str(tooltip), view)
        else:
            QToolTip.hideText()
        return True


class LedgerlyComboBox(QComboBox):
    """Keep QComboBox values/signals, with a floating list owned by the control.

    The view shares the combo's model, but is never placed in Qt's private menu
    container. That avoids native scroller bands and scroll-area clipping.
    Closed field sizing continues to be supplied by the existing form layouts.
    """

    def __init__(self, parent: QWidget | None = None, *, compact: bool = False) -> None:
        super().__init__(parent)
        self.setProperty("dropdownDensity", "compact" if compact else "standard")
        self.setMaxVisibleItems(DROPDOWN_MAX_ROWS)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._popup_window = QFrame(
            self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self._popup_window.setObjectName("ledgerlyDropdownPopup")
        self._popup_window.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._popup_window.setStyleSheet(DROPDOWN_POPUP_STYLE)
        self._popup_window.installEventFilter(self)
        layout = QVBoxLayout(self._popup_window)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._list = QListView(self._popup_window)
        self._list.setObjectName("ledgerlyDropdownList")
        # QAbstractScrollArea's native minimum hint reserves scrollbar height
        # even for one item. The popup's row calculation owns both dimensions.
        self._list.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._list.setModel(self.model())
        self._list.selectionModel().currentChanged.connect(self._highlight_popup_index)
        self._list.setModelColumn(self.modelColumn())
        self._list.setUniformItemSizes(True)
        self._list.setSpacing(0)
        self._list.setMouseTracking(True)
        self._list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        self._list.setItemDelegate(DropdownItemDelegate(self._list))
        self._list.installEventFilter(self)
        self._list.viewport().installEventFilter(self)
        self._list.clicked.connect(self._activate_popup_index)
        layout.addWidget(self._list)
        self._app_filter_installed = False
        self._sync_cursor()

    def view(self) -> QListView:
        return self._list

    def setModel(self, model) -> None:  # noqa: N802
        super().setModel(model)
        if hasattr(self, "_list"):
            self._list.setModel(model)
            self._list.selectionModel().currentChanged.connect(self._highlight_popup_index)

    def setModelColumn(self, column) -> None:  # noqa: N802
        super().setModelColumn(column)
        if hasattr(self, "_list"):
            self._list.setModelColumn(column)

    def setRootModelIndex(self, index) -> None:  # noqa: N802
        super().setRootModelIndex(index)
        if hasattr(self, "_list"):
            self._list.setRootIndex(index)

    def popup_row_height(self) -> int:
        return max(DROPDOWN_ROW_HEIGHT, QFontMetrics(self._list.font()).height() + 12)

    def showPopup(self) -> None:  # noqa: N802
        if not self.isEnabled() or not self.count():
            return
        # A common popup font keeps compact fields and standard fields at the
        # same row density. Pixel sizes here are Qt logical, DPI-scaled units.
        font = QFont(self.font())
        font.setPixelSize(13)
        self._list.setFont(font)
        self._hovered_index = None
        self._list.setRootIndex(self.rootModelIndex())
        self._list.setCurrentIndex(self.model().index(self.currentIndex(), self.modelColumn(), self.rootModelIndex()))
        self._position_popup()
        self._popup_window.show()
        if not self._app_filter_installed:
            QApplication.instance().installEventFilter(self)
            self._app_filter_installed = True
        self._popup_window.raise_()
        self._list.setFocus(Qt.FocusReason.PopupFocusReason)
        self._list.scrollTo(self._list.currentIndex(), QAbstractItemView.ScrollHint.EnsureVisible)

    def hidePopup(self) -> None:  # noqa: N802
        self._popup_window.hide()
        super().hidePopup()

    def _highlight_popup_index(self, index, _previous=None) -> None:
        if self._popup_window.isVisible() and index.isValid():
            if index.flags() & Qt.ItemFlag.ItemIsEnabled:
                self.highlighted.emit(index.row())
                self.textHighlighted.emit(str(index.data() or ""))

    def _activate_popup_index(self, index) -> None:
        if not index.isValid() or not index.flags() & Qt.ItemFlag.ItemIsEnabled or not index.flags() & Qt.ItemFlag.ItemIsSelectable:
            return
        self.setCurrentIndex(index.row())
        self.hidePopup()
        self.setFocus(Qt.FocusReason.PopupFocusReason)
        self.activated.emit(index.row())
        self.textActivated.emit(self.currentText())

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space, Qt.Key.Key_F4) or (
            event.key() == Qt.Key.Key_Down and event.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            self.showPopup()
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange:
            self._sync_cursor()
            if not self.isEnabled():
                self.hidePopup()

    def _sync_cursor(self) -> None:
        cursor = Qt.CursorShape.PointingHandCursor if self.isEnabled() else Qt.CursorShape.ArrowCursor
        self.setCursor(cursor)
        self._list.viewport().setCursor(cursor)
        self._list.verticalScrollBar().setCursor(Qt.CursorShape.ArrowCursor)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if not hasattr(self, "_list"):
            return super().eventFilter(watched, event)
        if self._popup_window.isVisible() and event.type() == QEvent.Type.MouseButtonPress:
            point = event.globalPosition().toPoint()
            if not self._popup_window.frameGeometry().contains(point):
                self.hidePopup()
                # A second click on the field closes it, without reopening.
                return self.rect().contains(self.mapFromGlobal(point))
        if event.type() == QEvent.Type.ApplicationDeactivate:
            self.hidePopup()
        if watched is self._list.viewport() and event.type() == QEvent.Type.MouseMove:
            index = self._list.indexAt(event.position().toPoint())
            enabled = index.isValid() and bool(index.flags() & Qt.ItemFlag.ItemIsEnabled)
            watched.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor)
            if index != getattr(self, "_hovered_index", None):
                self._hovered_index = index
                self._highlight_popup_index(index)
        if watched is self._list and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F4):
                self.hidePopup()
                self.setFocus(Qt.FocusReason.PopupFocusReason)
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                self._activate_popup_index(self._list.currentIndex())
                return True
            if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                self.hidePopup()
                self.setFocus(Qt.FocusReason.PopupFocusReason)
                self.focusNextPrevChild(event.key() == Qt.Key.Key_Tab)
                return True
        if watched is self._popup_window and event.type() == QEvent.Type.Hide:
            if self._app_filter_installed:
                QApplication.instance().removeEventFilter(self)
                self._app_filter_installed = False
            # Reset QComboBox's pressed state after outside-click dismissal.
            super().hidePopup()
            self.update()
        return super().eventFilter(watched, event)

    def _position_popup(self) -> None:
        available = self.screen().availableGeometry()
        top = self.mapToGlobal(QPoint(0, 0))
        bottom = top.y() + self.height()
        row_height = self.popup_row_height()
        desired_rows = min(self.count(), max(1, self.maxVisibleItems()))
        desired_height = desired_rows * row_height + 2
        gap = 4
        below = max(0, available.bottom() + 1 - bottom - gap)
        above = max(0, top.y() - available.top() - gap)
        opens_above = desired_height > below and (desired_height <= above or above > below)
        space = above if opens_above else below
        rows = min(desired_rows, max(1, (space - 2) // row_height))
        height = min(rows * row_height + 2, available.height())
        metrics = QFontMetrics(self._list.font())
        content_width = max(
            DropdownItemDelegate.content_width(
                self.model().index(row, self.modelColumn(), self.rootModelIndex()), metrics,
            )
            for row in range(self.count())
        ) + 2
        if self.count() > rows:
            content_width += 10
        # Permit modest growth for readable names, but bound pathological text.
        width = min(available.width(), max(self.width(), min(content_width, max(420, self.width() + 120))))
        x = max(available.left(), min(top.x(), available.right() - width + 1))
        y = top.y() - gap - height if opens_above else bottom + gap
        y = max(available.top(), min(y, available.bottom() - height + 1))
        self._popup_window.setGeometry(x, y, width, height)
        self._popup_window.layout().activate()
        self._list.doItemsLayout()

