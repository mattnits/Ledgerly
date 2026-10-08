from app.ui.widgets.file_selection import FileSelection
from app.ui.dialogs.generic_dialog import GenericDialog
from app.utils.constants import ADD_STATMENT_LABEL


class FileUploadDialog(GenericDialog):

    def __init__(self, parent=None, *, save_import_default: bool | None = None):
        self.file_selection = FileSelection(
            save_import_default=save_import_default
        )
        super().__init__(
            ADD_STATMENT_LABEL,
            self.file_selection,
            parent,
            submit_label="Import",
            subtitle="Import transaction files from your bank or credit card.",
            icon_name="fa6s.file-arrow-up",
        )
        self.resize(940, 720)
        self.setMinimumSize(760, 560)
        self.submit_button.setEnabled(False)
        self.file_selection.queue_changed.connect(self.submit_button.setEnabled)

    def get_files(self):
        return self.file_selection.get_files()

    def get_file_parse_types(self) -> list[tuple[str, str]]:
        return self.file_selection.get_file_parse_types()

    def get_date_range(self):
        return self.file_selection.get_date_range()

    def should_save_source_files(self) -> bool:
        return self.file_selection.should_save_source_files()

    def show_errors(self, errors: list[tuple[str, str]]) -> None:
        self.file_selection.show_errors(errors)

    def show_classification_summary(self, summary) -> None:
        self.subtitle_label.setText(
            f"{summary.parsed} rows parsed · {summary.added} new · "
            f"{summary.definite_duplicates_skipped} duplicates skipped · "
            f"{summary.possible_duplicates} need review"
        )
        self.subtitle_label.setVisible(True)
