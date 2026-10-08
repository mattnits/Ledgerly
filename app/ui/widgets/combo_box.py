from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QFrame, QWidget


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
        self._configure_popup_surface()
        QTimer.singleShot(0, self._configure_popup_surface)

    def _configure_popup_surface(self) -> None:
        view = self.view()
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setLineWidth(0)
        view.setMidLineWidth(0)
        view.setContentsMargins(0, 0, 0, 0)
        view.viewport().setContentsMargins(0, 0, 0, 0)
        view.viewport().setAutoFillBackground(False)

        popup = view.window()
        if popup is self:
            return
        self._configure_popup_scrollers(popup)
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
        """Remove the opaque bands Qt places above and below long popups."""
        for child in popup.findChildren(
            QWidget,
            options=Qt.FindChildOption.FindDirectChildrenOnly,
        ):
            if child.metaObject().className() != "QComboBoxPrivateScroller":
                continue
            child.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            child.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            child.setAutoFillBackground(False)
            child.setStyleSheet("background: transparent; border: none;")
