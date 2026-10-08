from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class Spinner(QWidget):
    """Small dependency-free animated spinner for local loading states."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(42, 42)
        self._timer = QTimer(self)
        self._timer.setInterval(70)
        self._timer.timeout.connect(self._advance)

    def start(self) -> None:
        self._timer.start()
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _advance(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._angle)
        radius = min(self.width(), self.height()) / 2 - 7
        for index in range(12):
            color = QColor("#4c9dff")
            color.setAlpha(45 + index * 17)
            painter.setPen(QPen(color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(0, int(-radius), 0, int(-radius + 7))
            painter.rotate(30)


class LoadingOverlay(QWidget):
    """Reusable non-modal loading/error state constrained to one content panel."""

    def __init__(self, target: QWidget):
        super().__init__(target)
        self._target = target
        self.setObjectName("loadingOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        target.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)
        self.spinner = Spinner(self)
        self.label = QLabel("Loading...")
        self.label.setObjectName("loadingMessage")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.retry_button = QPushButton("Retry")
        self.retry_button.setObjectName("loadingRetryButton")
        self.retry_button.setFixedWidth(100)
        self.retry_button.hide()
        layout.addWidget(self.spinner, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.retry_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setStyleSheet("""
            QWidget#loadingOverlay {
                background: rgba(23, 27, 32, 245);
                border: 1px solid #303740;
                border-radius: 14px;
            }
            QLabel#loadingMessage {
                color: #c8cdd4;
                font-size: 14px;
            }
            QPushButton#loadingRetryButton {
                color: #ffffff;
                background: #2878d0;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
            }
            QPushButton#loadingRetryButton:hover { background: #338be7; }
        """)
        self.hide()

    @property
    def retry_requested(self):
        return self.retry_button.clicked

    def eventFilter(self, watched, event) -> bool:
        if watched is self._target and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
        ):
            self.setGeometry(self._target.rect())
        return super().eventFilter(watched, event)

    def show_loading(self, message: str = "Loading...") -> None:
        self.setGeometry(self._target.rect())
        self.label.setText(message)
        self.retry_button.hide()
        self.spinner.start()
        self.show()
        self.raise_()

    def show_error(self, message: str) -> None:
        self.setGeometry(self._target.rect())
        self.spinner.stop()
        self.label.setText(message)
        self.retry_button.show()
        self.show()
        self.raise_()

    def hide_loading(self) -> None:
        self.spinner.stop()
        self.hide()
