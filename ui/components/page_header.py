from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class PageHeader(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str | None = None,
        action_button: QPushButton | None = None,
        centered: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)

        heading = QVBoxLayout()
        heading.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("pageTitle")
        heading.addWidget(self.title_label)

        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setObjectName("pageSubtitle")
            self.subtitle_label.setWordWrap(True)
            heading.addWidget(self.subtitle_label)

        if centered:
            self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if subtitle:
                self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            layout.addLayout(heading, 1)

        if centered:
            layout.addStretch()
            layout.addLayout(heading)
            layout.addStretch()

        if action_button is not None:
            layout.addWidget(action_button, alignment=Qt.AlignmentFlag.AlignVCenter)

    def set_subtitle(self, subtitle: str) -> None:
        if hasattr(self, "subtitle_label"):
            self.subtitle_label.setText(subtitle)
