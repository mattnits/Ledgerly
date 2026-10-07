from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QAbstractSpinBox, QComboBox


class WheelChangeGuard(QObject):
    """Prevent hover-wheel events from changing form-field values."""

    def eventFilter(self, watched, event) -> bool:
        if (
            event.type() == QEvent.Type.Wheel
            and isinstance(watched, (QComboBox, QAbstractSpinBox))
        ):
            event.accept()
            return True
        return super().eventFilter(watched, event)


def install_wheel_change_guard(app: QApplication) -> WheelChangeGuard:
    """Install the app-wide wheel guard once and retain it for app lifetime."""
    object_name = "financeWheelChangeGuard"
    existing = app.findChild(WheelChangeGuard, object_name)
    if existing is not None:
        return existing

    guard = WheelChangeGuard(app)
    guard.setObjectName(object_name)
    app.installEventFilter(guard)
    return guard
