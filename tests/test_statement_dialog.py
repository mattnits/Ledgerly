import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtCore import QCoreApplication, QEvent, QPoint
from PySide6.QtWidgets import QApplication, QDialog

from app.ui.widgets.file_selection import FileSelection
from app.ui.dialogs.file_upload_dialog import FileUploadDialog
from app.utils.constants import SUPPORTED_PARSE_TYPES


class StatementDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        root = Path(__file__).resolve().parent.parent
        self.amex = root / "README.md"
        self.td = root / "app" / "__main__.py"

    def test_multiple_files_and_per_file_parser_selection_are_preserved(self):
        selection = FileSelection()
        selection.set_files([str(self.amex), str(self.td)])
        selection.file_rows[0].parse_type.setCurrentText(
            SUPPORTED_PARSE_TYPES.AMEX.value
        )
        selection.file_rows[1].parse_type.setCurrentText(
            SUPPORTED_PARSE_TYPES.TD_CREDIT.value
        )

        self.assertEqual(selection.get_files(), [str(self.amex), str(self.td)])
        self.assertEqual(
            selection.get_file_parse_types(),
            [
                (str(self.amex), SUPPORTED_PARSE_TYPES.AMEX.value),
                (str(self.td), SUPPORTED_PARSE_TYPES.TD_CREDIT.value),
            ],
        )

    def test_ready_file_row_stays_compact(self):
        dialog = FileUploadDialog()
        dialog.file_selection.set_files([str(self.amex)])
        dialog.show()
        self.app.processEvents()

        row = dialog.file_selection.file_rows[0]
        self.assertLess(row.height(), dialog.file_selection.file_list.height() // 2)
        self.assertLessEqual(row.height(), 100)
        dialog.close()

    def test_remove_only_changes_pending_queue_and_keeps_original_file(self):
        selection = FileSelection()
        selection.set_files([str(self.amex), str(self.td)])

        self.assertFalse(selection.file_rows[0].remove_button.icon().isNull())
        selection.file_rows[0].remove_button.click()
        self.app.processEvents()

        self.assertTrue(self.amex.exists())
        self.assertEqual(selection.get_files(), [str(self.td)])
        self.assertEqual(
            selection.get_file_parse_types(),
            [(str(self.td), SUPPORTED_PARSE_TYPES.TD_DEBIT.value)],
        )

    def test_failed_and_ready_rows_show_status_and_summary(self):
        selection = FileSelection()
        selection.set_files([str(self.amex), str(self.td)])
        selection.show_errors([(str(self.amex), "Columns do not match")])

        failed, ready = selection.file_rows
        self.assertTrue(failed.property("failed"))
        self.assertEqual(failed.status_label.text(), "Failed")
        self.assertEqual(failed.status_detail.text(), "Columns do not match")
        self.assertTrue(failed.status_detail.wordWrap())
        self.assertFalse(ready.property("failed"))
        self.assertEqual(ready.status_label.text(), "Ready")
        self.assertFalse(selection.error_summary.isHidden())
        self.assertEqual(
            selection.error_summary.title.text(), "1 file failed to import"
        )

    def test_removing_failed_files_updates_and_hides_error_summary(self):
        selection = FileSelection()
        selection.set_files([str(self.amex), str(self.td)])
        selection.show_errors([
            (str(self.amex), "First error"),
            (str(self.td), "Second error"),
        ])

        selection.remove_file(str(self.amex))
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertEqual(
            selection.error_summary.title.text(), "1 file failed to import"
        )
        self.assertEqual(selection.error_summary.detail.text(), "Second error")

        selection.remove_file(str(self.td))
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertTrue(selection.error_summary.isHidden())

    def test_date_range_toggle_controls_both_inputs(self):
        selection = FileSelection()
        self.assertFalse(selection.file_list.isHidden())
        self.assertFalse(selection.empty_state.isHidden())
        self.assertEqual(
            selection.empty_title.text(), "No statement files selected"
        )
        self.assertFalse(selection.start_date.isEnabled())
        self.assertFalse(selection.end_date.isEnabled())
        selection.limit_date_range.setChecked(True)
        self.assertTrue(selection.start_date.isEnabled())
        self.assertTrue(selection.end_date.isEnabled())

    def test_import_button_tracks_queue_and_emits_only_when_enabled(self):
        dialog = FileUploadDialog()
        submitted = QSignalSpy(dialog.submitted)
        self.assertFalse(dialog.submit_button.isEnabled())

        dialog.file_selection.set_files([str(self.amex), str(self.td)])
        self.assertTrue(dialog.submit_button.isEnabled())
        dialog.file_selection.remove_file(str(self.amex))
        self.assertEqual(dialog.get_files(), [str(self.td)])
        dialog.submit_button.click()
        self.assertEqual(submitted.count(), 1)

        dialog.file_selection.remove_file(str(self.td))
        self.assertFalse(dialog.submit_button.isEnabled())

    def test_save_files_is_one_batch_toggle_and_modal_changes_are_not_saved(self):
        with (
            patch(
                "app.ui.widgets.file_selection.save_imported_files_enabled",
                return_value=True,
            ),
            patch(
                "app.ui.preferences.set_save_imported_files"
            ) as save_preference,
        ):
            dialog = FileUploadDialog()
            dialog.file_selection.set_files([str(self.amex), str(self.td)])

            self.assertTrue(dialog.should_save_source_files())
            self.assertEqual(
                len(dialog.file_selection.findChildren(
                    type(dialog.file_selection.save_files_toggle)
                )),
                1,
            )
            dialog.file_selection.save_files_toggle.click()

            self.assertFalse(dialog.should_save_source_files())
            save_preference.assert_not_called()
            dialog.close()

    def test_date_section_and_footer_stay_anchored_when_files_are_added(self):
        dialog = FileUploadDialog()
        dialog.show()
        self.app.processEvents()
        empty_date_y = dialog.file_selection.date_range_card.mapTo(
            dialog, QPoint(0, 0)
        ).y()
        empty_import_y = dialog.submit_button.mapTo(dialog, QPoint(0, 0)).y()

        dialog.file_selection.set_files([str(self.amex), str(self.td)])
        self.app.processEvents()

        self.assertEqual(
            dialog.file_selection.date_range_card.mapTo(
                dialog, QPoint(0, 0)
            ).y(),
            empty_date_y,
        )
        self.assertEqual(
            dialog.submit_button.mapTo(dialog, QPoint(0, 0)).y(),
            empty_import_y,
        )
        dialog.close()

    def test_cancel_rejects_dialog_without_submitting(self):
        dialog = FileUploadDialog()
        submitted = QSignalSpy(dialog.submitted)
        dialog.show()
        dialog.cancel_button.click()
        self.app.processEvents()

        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        self.assertEqual(submitted.count(), 0)


if __name__ == "__main__":
    unittest.main()
