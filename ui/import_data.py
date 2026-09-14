from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
)


class ImportPage(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)

        title = QLabel("Import")

        title.setStyleSheet("""
            font-size: 28px;
            font-weight: 700;
        """)

        layout.addWidget(title)

        layout.addStretch()