from pathlib import Path

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QStyle, QWidget

from utils.constants import SUPPORTED_PARSE_TYPES


class FileRow(QWidget):
    def __init__(self, filename: str, parent=None):
        super().__init__(parent)

        self.filename = filename

        layout = QHBoxLayout(self)
        self.error_icon = QLabel()
        self.error_icon.setPixmap(
            self.style().standardIcon(QStyle.SP_MessageBoxCritical).pixmap(16, 16)
        )
        self.error_icon.hide()
        layout.addWidget(self.error_icon)
        layout.addWidget(QLabel(Path(filename).name))
        layout.addStretch()

        self.parse_type = QComboBox()
        self.parse_type.addItems(SUPPORTED_PARSE_TYPES)
        layout.addWidget(self.parse_type)

    def get_parse_type(self) -> str:
        return self.parse_type.currentText()

    def set_error(self, message: str | None) -> None:
        self.error_icon.setToolTip(message or "")
        self.error_icon.setVisible(bool(message))
