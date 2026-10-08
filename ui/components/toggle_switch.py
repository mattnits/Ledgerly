from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton, QWidget


class ToggleSwitch(QAbstractButton):
    """Small accessible on/off switch shared by settings and dialogs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(46, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#326ee8" if self.isChecked() else "#343b45"))
        painter.drawRoundedRect(QRectF(0, 0, 46, 26), 13, 13)
        painter.setBrush(QColor("#ffffff" if self.isChecked() else "#b7bec8"))
        handle_left = 23 if self.isChecked() else 3
        painter.drawEllipse(QRectF(handle_left, 3, 20, 20))
