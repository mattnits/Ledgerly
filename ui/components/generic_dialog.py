from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)


class GenericDialog(QDialog):
    submitted = Signal()

    def __init__(
        self,
        title: str,
        content: QWidget,
        parent=None,
        *,
        submit_label: str = "Submit",
    ):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(500, 350)

        layout = QVBoxLayout(self)

        title_label = QLabel(title)
        layout.addWidget(title_label)

        layout.addWidget(content, 1)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel")
        submit_button = QPushButton(submit_label)

        button_layout.addWidget(cancel_button)
        button_layout.addWidget(submit_button)

        layout.addLayout(button_layout)

        cancel_button.clicked.connect(self.reject)
        submit_button.clicked.connect(self._submit)

    def _submit(self):
        self.submitted.emit()
