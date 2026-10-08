from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QAbstractSpinBox,
    QComboBox,
)


def _sync_interactive_cursor(widget: QAbstractButton) -> None:
    widget.setCursor(
        Qt.CursorShape.PointingHandCursor
        if widget.isEnabled()
        else Qt.CursorShape.ArrowCursor
    )


class InteractiveCursorFilter(QObject):
    """Keep an explicitly configured button's cursor in sync with enabled state."""

    def eventFilter(self, watched, event) -> bool:
        if (
            event.type() == QEvent.Type.EnabledChange
            and isinstance(watched, QAbstractButton)
        ):
            _sync_interactive_cursor(watched)
        return super().eventFilter(watched, event)


def apply_interactive_cursor(button: QAbstractButton) -> None:
    """Give a button a pointing cursor only while it is enabled."""
    object_name = "financeInteractiveCursorFilter"
    guard = button.findChild(
        InteractiveCursorFilter,
        object_name,
        Qt.FindChildOption.FindDirectChildrenOnly,
    )
    if guard is None:
        guard = InteractiveCursorFilter(button)
        guard.setObjectName(object_name)
        button.installEventFilter(guard)
    _sync_interactive_cursor(button)


class ApplicationInteractiveCursorFilter(QObject):
    """Apply the cursor convention to every standard button in the application."""

    def eventFilter(self, watched, event) -> bool:
        if isinstance(watched, QAbstractButton) and event.type() in (
            QEvent.Type.EnabledChange,
            QEvent.Type.Polish,
            QEvent.Type.Show,
        ):
            _sync_interactive_cursor(watched)
        return super().eventFilter(watched, event)


def install_interactive_cursor_guard(
    app: QApplication,
) -> ApplicationInteractiveCursorFilter:
    object_name = "financeInteractiveCursorGuard"
    existing = app.findChild(ApplicationInteractiveCursorFilter, object_name)
    if existing is not None:
        return existing
    guard = ApplicationInteractiveCursorFilter(app)
    guard.setObjectName(object_name)
    app.installEventFilter(guard)
    return guard


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
    install_interactive_cursor_guard(app)
    object_name = "financeWheelChangeGuard"
    existing = app.findChild(WheelChangeGuard, object_name)
    if existing is not None:
        return existing

    guard = WheelChangeGuard(app)
    guard.setObjectName(object_name)
    app.installEventFilter(guard)
    return guard
