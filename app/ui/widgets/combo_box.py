from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)


class AppComboBox(QComboBox):
    """Combo box whose popup has no native frame or stray edge bands."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._configure_popup_surface()

    def setView(self, item_view: QAbstractItemView) -> None:  # noqa: N802
        super().setView(item_view)
        self._configure_popup_surface()

    def showPopup(self) -> None:  # noqa: N802
        self._configure_popup_surface()
        super().showPopup()
        # Qt lays out its private edge scrollers while opening the popup, so
        # clean them once immediately and again after that layout completes.
        self._finalize_popup_surface()
        QTimer.singleShot(0, self._finalize_popup_surface)

    def _finalize_popup_surface(self) -> None:
        self._configure_popup_surface()
        view = self.view()
        popup = view.window()
        if popup is self or not popup.isVisible() or view.height() <= 0:
            return

        # QComboBoxPrivateContainer reserves platform menu margins even after
        # its arrow scrollers are hidden. Those transparent margins become
        # solid black bands on some Windows compositors, so size the popup to
        # the list surface itself. Preserve the lower edge when Qt opens the
        # popup above the field near the bottom of the screen.
        popup_geometry = popup.geometry()
        target_height = view.height()
        field_top = self.mapToGlobal(self.rect().topLeft()).y()
        target_y = popup_geometry.y()
        if popup_geometry.y() < field_top:
            target_y = popup_geometry.bottom() - target_height + 1
        popup.setGeometry(
            popup_geometry.x(),
            target_y,
            popup_geometry.width(),
            target_height,
        )
        view.setGeometry(0, 0, popup_geometry.width(), target_height)

    def _configure_popup_surface(self) -> None:
        view = self.view()
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setLineWidth(0)
        view.setMidLineWidth(0)
        view.setContentsMargins(0, 0, 0, 0)
        view.viewport().setContentsMargins(0, 0, 0, 0)
        view.viewport().setAutoFillBackground(False)
        view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        popup = view.window()
        if popup is self:
            return
        popup.setContentsMargins(0, 0, 0, 0)
        self._configure_popup_scrollers(popup)
        if popup.layout() is not None:
            popup.layout().setContentsMargins(0, 0, 0, 0)
            popup.layout().setSpacing(0)
        if popup.property("cleanComboPopupConfigured"):
            return
        popup.setProperty("cleanComboPopupConfigured", True)
        popup.setProperty("cleanComboPopup", True)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        popup.setAutoFillBackground(False)
        popup.setWindowFlags(
            popup.windowFlags() | Qt.WindowType.NoDropShadowWindowHint
        )
        popup.setStyleSheet(
            popup.styleSheet()
            + """
                QWidget[cleanComboPopup="true"] {
                    background: transparent;
                    border: none;
                }
            """
        )

    @staticmethod
    def _configure_popup_scrollers(popup: QWidget) -> None:
        """Remove Qt's opaque arrow bands from every combo popup.

        Long lists remain scrollable through their standard vertical scrollbar,
        the mouse wheel, touchpad gestures, and keyboard navigation.
        """
        for child in popup.findChildren(QWidget):
            if child.metaObject().className() != "QComboBoxPrivateScroller":
                continue
            child.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            child.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            child.setAutoFillBackground(False)
            child.setFixedHeight(0)
            child.setVisible(False)
            child.setStyleSheet(
                "background: transparent; border: none; image: none; "
                "min-height: 0; max-height: 0; margin: 0; padding: 0;"
            )


class _CompactPopupDelegate(QStyledItemDelegate):
    ROW_HEIGHT = 32

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        size = super().sizeHint(option, index)
        size.setHeight(self.ROW_HEIGHT)
        return size


class FramelessPopupComboBox(AppComboBox):
    """Combo box with an owned popup and no platform scroller bands."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        view = self.view()
        view.setItemDelegate(_CompactPopupDelegate(view))
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)

        self._popup_window = QFrame(
            self,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self._popup_window.setObjectName("framelessComboPopup")
        self._popup_window.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground, True
        )
        self._popup_window.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, False
        )
        popup_layout = QVBoxLayout(self._popup_window)
        popup_layout.setContentsMargins(0, 0, 0, 0)
        popup_layout.setSpacing(0)
        popup_layout.addWidget(view)
        view.clicked.connect(self._activate_popup_index)
        view.installEventFilter(self)
        self._popup_window.setStyleSheet("""
            QFrame#framelessComboPopup {
                background: #20242a;
                border: none;
            }
            QFrame#framelessComboPopup QAbstractItemView {
                color: #e5e7ea;
                background: #20242a;
                border: 1px solid #3a4048;
                padding: 0;
                margin: 0;
                outline: none;
                selection-color: #ffffff;
                selection-background-color: #287df0;
            }
            QFrame#framelessComboPopup QScrollBar:vertical {
                width: 10px;
                margin: 3px 2px 3px 0;
                background: transparent;
            }
            QFrame#framelessComboPopup QScrollBar::handle:vertical {
                min-height: 28px;
                background: #59616d;
                border-radius: 4px;
            }
            QFrame#framelessComboPopup QScrollBar::add-line:vertical,
            QFrame#framelessComboPopup QScrollBar::sub-line:vertical,
            QFrame#framelessComboPopup QScrollBar::add-page:vertical,
            QFrame#framelessComboPopup QScrollBar::sub-page:vertical {
                height: 0;
                background: transparent;
                border: none;
            }
        """)

    def showPopup(self) -> None:  # noqa: N802
        if self.count() == 0:
            return
        current = self.model().index(self.currentIndex(), self.modelColumn())
        if current.isValid():
            self.view().setCurrentIndex(current)
        self._position_popup()
        self._popup_window.show()
        self._popup_window.raise_()
        self.view().setFocus(Qt.FocusReason.PopupFocusReason)
        QTimer.singleShot(0, self._position_popup)

    def hidePopup(self) -> None:  # noqa: N802
        self._popup_window.hide()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.view() and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.hidePopup()
                self.setFocus(Qt.FocusReason.PopupFocusReason)
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._activate_popup_index(self.view().currentIndex())
                return True
        return super().eventFilter(watched, event)

    def _activate_popup_index(self, index) -> None:
        if not index.isValid():
            return
        self.setCurrentIndex(index.row())
        self.activated.emit(index.row())
        self.hidePopup()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def _position_popup(self) -> None:
        if self.count() == 0:
            return
        view = self.view()
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        row_height = _CompactPopupDelegate.ROW_HEIGHT
        desired_rows = min(self.count(), self.maxVisibleItems())
        desired_height = desired_rows * row_height + 2
        screen = self.screen()
        if screen is None:
            return
        available = screen.availableGeometry()
        field_top_left = self.mapToGlobal(self.rect().topLeft())
        field_bottom_right = self.mapToGlobal(self.rect().bottomRight())
        popup_gap = 4
        space_below = available.bottom() - field_bottom_right.y() - popup_gap
        space_above = field_top_left.y() - available.top() - popup_gap
        if desired_height <= space_below:
            opens_above = False
        elif desired_height <= space_above:
            opens_above = True
        else:
            opens_above = space_above > space_below
        available_height = space_above if opens_above else space_below
        fitting_rows = max(1, (available_height - 2) // row_height)
        target_rows = min(desired_rows, fitting_rows)
        target_height = target_rows * row_height + 2
        scrollbar_width = (
            view.verticalScrollBar().sizeHint().width()
            if self.count() > target_rows
            else 0
        )
        target_width = min(
            available.width(),
            max(
                self.width(),
                view.minimumWidth(),
                view.sizeHintForColumn(self.modelColumn())
                + scrollbar_width
                + 24,
            ),
        )
        target_x = min(
            max(field_top_left.x(), available.left()),
            available.right() - target_width + 1,
        )
        target_y = (
            field_top_left.y() - popup_gap - target_height
            if opens_above
            else field_bottom_right.y() + popup_gap + 1
        )
        self._popup_window.setGeometry(
            target_x,
            target_y,
            target_width,
            target_height,
        )
        if self._popup_window.layout() is not None:
            self._popup_window.layout().activate()
        current = self.model().index(self.currentIndex(), self.modelColumn())
        if current.isValid():
            view.scrollTo(current, QAbstractItemView.ScrollHint.EnsureVisible)
