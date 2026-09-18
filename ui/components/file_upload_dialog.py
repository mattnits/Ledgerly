from ui.components.file_selection import FileSelection
from ui.components.generic_dialog import GenericDialog
from utils.constants import ADD_STATMENT_LABEL


class FileUploadDialog(GenericDialog):

    def __init__(self, parent=None):
        self.file_selection = FileSelection()
        super().__init__(ADD_STATMENT_LABEL, self.file_selection, parent)

    def get_files(self):
        return self.file_selection.get_files()

    def get_file_parse_types(self) -> list[tuple[str, str]]:
        return self.file_selection.get_file_parse_types()

    def show_errors(self, errors: list[tuple[str, str]]) -> None:
        self.file_selection.show_errors(errors)
