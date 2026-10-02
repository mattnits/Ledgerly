from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from ui.theme import set_button_icon


class GenericDialog(QDialog):
    submitted = Signal()

    def __init__(
        self,
        title: str,
        content: QWidget,
        parent=None,
        *,
        submit_label: str = "Submit",
        subtitle: str | None = None,
    ):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(500, 350)
        self.setObjectName("genericDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(18)

        heading_layout = QVBoxLayout()
        heading_layout.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("dialogTitle")
        heading_layout.addWidget(self.title_label)

        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setObjectName("dialogSubtitle")
            self.subtitle_label.setWordWrap(True)
            heading_layout.addWidget(self.subtitle_label)
        layout.addLayout(heading_layout)

        layout.addWidget(content, 1)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.submit_button = QPushButton(submit_label)
        self.submit_button.setObjectName("primaryButton")
        set_button_icon(self.cancel_button, "fa6s.xmark", size=15)
        set_button_icon(
            self.submit_button,
            "fa6s.check",
            color="#ffffff",
            active_color="#ffffff",
            size=15,
        )

        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.submit_button)

        layout.addLayout(button_layout)

        self.cancel_button.clicked.connect(self.reject)
        self.submit_button.clicked.connect(self._submit)

    def _submit(self):
        self.submitted.emit()
