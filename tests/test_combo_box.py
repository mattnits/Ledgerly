import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QWidget

from app.ui.widgets.combo_box import AppComboBox
from app.ui.widgets.date_dropdown import DateDropdown


class AppComboBoxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_popup_has_no_native_frame_or_outer_margins(self):
        combo = AppComboBox()
        combo.addItems(("First", "Second", "Third"))
        view = combo.view()
        popup = view.window()

        self.assertEqual(view.frameShape(), QFrame.Shape.NoFrame)
        self.assertTrue(view.contentsMargins().isNull())
        self.assertTrue(view.viewport().contentsMargins().isNull())
        self.assertTrue(popup.property("cleanComboPopup"))
        self.assertTrue(
            popup.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        )
        self.assertFalse(popup.autoFillBackground())

    def test_date_dropdown_uses_the_same_clean_popup_base(self):
        combo = DateDropdown()

        self.assertIsInstance(combo, AppComboBox)
        self.assertEqual(combo.view().frameShape(), QFrame.Shape.NoFrame)
        margins = combo.view().contentsMargins()
        self.assertLessEqual(max(
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
        ), 1)

    def test_long_popups_have_transparent_edge_scrollers(self):
        combo = DateDropdown()
        combo.addItems(f"Month {index}" for index in range(30))
        combo.resize(260, 42)
        combo.show()
        combo.showPopup()
        self.app.processEvents()

        popup = combo.view().window()
        scrollers = [
            child
            for child in popup.findChildren(
                QWidget,
                options=Qt.FindChildOption.FindDirectChildrenOnly,
            )
            if child.metaObject().className() == "QComboBoxPrivateScroller"
        ]
        self.assertTrue(scrollers)
        for scroller in scrollers:
            self.assertTrue(
                scroller.testAttribute(
                    Qt.WidgetAttribute.WA_TranslucentBackground
                )
            )
            self.assertTrue(
                scroller.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
            )
            self.assertFalse(scroller.autoFillBackground())
            self.assertIn("background: transparent", scroller.styleSheet())

        combo.hidePopup()
        combo.close()


if __name__ == "__main__":
    unittest.main()
