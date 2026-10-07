from ui.components.file_selection import FileSelection
from ui.components.generic_dialog import GenericDialog
from utils.constants import ADD_STATMENT_LABEL


class FileUploadDialog(GenericDialog):

    def __init__(self, parent=None):
        self.file_selection = FileSelection()
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

    def show_errors(self, errors: list[tuple[str, str]]) -> None:
        self.file_selection.show_errors(errors)
