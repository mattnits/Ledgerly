import sys

from PySide6.QtCore import QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen


def create_splash() -> QSplashScreen:
    """Create a lightweight splash that can be painted before app imports finish."""
    pixmap = QPixmap(520, 280)
    pixmap.fill(QColor("#0d0f12"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#303740"), 1))
    painter.setBrush(QColor("#171b20"))
    painter.drawRoundedRect(QRectF(1, 1, 518, 278), 18, 18)

    painter.setPen(QColor("#1677ff"))
    painter.setBrush(QColor("#1677ff"))
    painter.drawRoundedRect(QRectF(48, 62, 48, 48), 12, 12)

    mark_font = QFont()
    mark_font.setPixelSize(27)
    mark_font.setBold(True)
    painter.setFont(mark_font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(
        QRectF(48, 62, 48, 48),
        Qt.AlignmentFlag.AlignCenter,
        "$",
    )

    title_font = QFont()
    title_font.setPixelSize(30)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.setPen(QColor("#f2f4f7"))
    painter.drawText(QRectF(116, 57, 340, 42), "Finance")

    subtitle_font = QFont()
    subtitle_font.setPixelSize(13)
    painter.setFont(subtitle_font)
    painter.setPen(QColor("#a7afb9"))
    painter.drawText(QRectF(118, 99, 340, 28), "Your financial overview")
    painter.end()

    flags = (
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
    )
    splash = QSplashScreen(pixmap, flags)
    splash.setObjectName("startupSplash")
    return splash


def set_splash_status(
    app: QApplication,
    splash: QSplashScreen,
    message: str,
) -> None:
    """Update the splash and immediately let the platform paint it."""
    splash.showMessage(
        message,
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        QColor("#a7afb9"),
    )
    app.processEvents()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Finance")

    splash = create_splash()
    splash.show()
    set_splash_status(app, splash, "Starting Finance...")

    try:
        # Keep these imports after the first paint. Importing the full UI pulls
        # in every page and icon dependency, which otherwise leaves the first
        # native window blank while Python finishes loading them.
        from database.db import ensure_categories, init_db

        set_splash_status(app, splash, "Preparing your database...")
        init_db()
        ensure_categories()

        set_splash_status(app, splash, "Loading your dashboard...")
        from ui.shell import ShellWindow
        from ui.theme import apply_theme

        apply_theme(app)
        window = ShellWindow()

        revealed = False

        def finish_reveal() -> None:
            splash.finish(window)
            window.raise_()
            window.activateWindow()

        def reveal_window() -> None:
            nonlocal revealed
            if revealed:
                return
            revealed = True
            window.show()
            # Keep the splash above the first native paint. Closing it on the
            # following event-loop turn avoids exposing an unpainted frame.
            QTimer.singleShot(0, finish_reveal)

        window.startup_ready.connect(reveal_window)
        if window.is_startup_ready:
            QTimer.singleShot(0, reveal_window)
        else:
            set_splash_status(app, splash, "Finishing startup...")
    except Exception:
        splash.close()
        raise

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
