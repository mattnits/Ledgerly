import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QPushButton,
    QSpinBox,
)

from ui.input_behavior import install_wheel_change_guard


def send_wheel(widget, vertical_delta: int) -> None:
    event = QWheelEvent(
        QPointF(5, 5),
        QPointF(5, 5),
        QPoint(0, 0),
        QPoint(0, vertical_delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    QApplication.sendEvent(widget, event)


class WheelChangeGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.guard = install_wheel_change_guard(cls.app)

    def test_installation_is_idempotent(self):
        self.assertIs(install_wheel_change_guard(self.app), self.guard)

    def test_regular_combo_box_ignores_wheel_changes(self):
        combo = QComboBox()
        combo.addItems(("First", "Second", "Third"))
        combo.setCurrentIndex(1)

        send_wheel(combo, 120)
        send_wheel(combo, -120)

        self.assertEqual(combo.currentIndex(), 1)

    def test_date_edit_ignores_wheel_changes(self):
        editor = QDateEdit(QDate(2026, 9, 15))
        editor.setCurrentSection(QDateEdit.Section.DaySection)
        editor.setFocus()

        send_wheel(editor, 120)
        send_wheel(editor, -120)

        self.assertEqual(editor.date(), QDate(2026, 9, 15))

    def test_spin_boxes_are_also_protected(self):
        spin = QSpinBox()
        spin.setRange(0, 10)
        spin.setValue(5)

        send_wheel(spin, 120)
        send_wheel(spin, -120)

        self.assertEqual(spin.value(), 5)

    def test_popup_view_is_not_blocked_by_the_field_guard(self):
        combo = QComboBox()
        combo.addItems(str(index) for index in range(20))
        event = QWheelEvent(
            QPointF(5, 5),
            QPointF(5, 5),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )

        self.assertFalse(self.guard.eventFilter(combo.view().viewport(), event))

    def test_button_cursor_tracks_enabled_state(self):
        button = QPushButton("Action")
        button.show()
        self.app.processEvents()
        self.assertEqual(
            button.cursor().shape(), Qt.CursorShape.PointingHandCursor
        )

        button.setEnabled(False)
        self.app.processEvents()
        self.assertEqual(button.cursor().shape(), Qt.CursorShape.ArrowCursor)

        button.setEnabled(True)
        self.app.processEvents()
        self.assertEqual(
            button.cursor().shape(), Qt.CursorShape.PointingHandCursor
        )


if __name__ == "__main__":
    unittest.main()
