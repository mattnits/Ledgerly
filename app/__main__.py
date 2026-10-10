import sys

from PySide6.QtCore import QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen

from app.core.paths import is_packaged, prepare_app_data_dir


def create_splash() -> QSplashScreen:
    """Create a lightweight splash that can be painted before app imports finish."""
    pixmap = QPixmap(520, 280)
    # Leave the area outside the rounded card transparent. An opaque pixmap
    # background makes the frameless window's square corners visible.
    pixmap.fill(Qt.GlobalColor.transparent)

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
    painter.drawText(QRectF(116, 57, 340, 42), "Ledgerly")

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
    splash.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    splash.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
    splash.setAutoFillBackground(False)
    # Some Windows compositors still draw the native splash surface as an
    # opaque rectangle even when its pixmap has an alpha channel. Clip the
    # actual window to the pixmap's non-transparent pixels as a backstop.
    splash.setMask(pixmap.mask())
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


def ask_to_retry_database(error: Exception) -> bool:
    """Explain a recoverable database startup problem without backend details."""
    message = QMessageBox()
    message.setIcon(QMessageBox.Icon.Warning)
    message.setWindowTitle("Database unavailable")
    message.setText("Ledgerly could not safely open this database.")
    message.setInformativeText(
        f"{error}\n\n"
        "To switch databases manually, close every Ledgerly window first and "
        "replace the complete database backup. You can correct the file now and "
        "retry without restarting Ledgerly."
    )
    message.setStandardButtons(
        QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Close
    )
    message.setDefaultButton(QMessageBox.StandardButton.Retry)
    return message.exec() == QMessageBox.StandardButton.Retry


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Ledgerly")

    splash = create_splash()
    splash.show()
    set_splash_status(app, splash, "Starting Ledgerly...")

    try:
        if is_packaged():
            set_splash_status(app, splash, "Setting up local storage...")
            prepare_app_data_dir()

        # Keep these imports after the first paint. Importing the full UI pulls
        # in every page and icon dependency, which otherwise leaves the first
        # native window blank while Python finishes loading them.
        from app.core.db import (
            DatabaseSetupError,
            prepare_database,
            reset_database_connections,
        )
        # Make normal shutdown release SQLite/WAL sidecar handles promptly so
        # a closed app is immediately safe to back up or switch manually.
        app.aboutToQuit.connect(reset_database_connections)

        set_splash_status(app, splash, "Preparing your database...")
        while True:
            try:
                prepare_database()
                break
            except DatabaseSetupError as error:
                # Release Windows file handles before asking the user to swap
                # or repair the file. Otherwise the retry dialog itself could
                # prevent a manual replacement.
                reset_database_connections()
                splash.hide()
                if not ask_to_retry_database(error):
                    return
                splash.show()
                set_splash_status(app, splash, "Checking your database...")

        set_splash_status(app, splash, "Loading your dashboard...")
        from app.ui.widgets.input_behavior import install_wheel_change_guard
        from app.ui.shell import ShellWindow
        from app.ui.theme import apply_theme

        apply_theme(app)
        install_wheel_change_guard(app)
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
            window.show_with_saved_window_mode()
            # Keep the splash above the first native paint. Closing it on the
            # following event-loop turn avoids exposing an unpainted frame.
            QTimer.singleShot(0, finish_reveal)

        window.startup_ready.connect(reveal_window)
        if window.is_startup_ready:
            QTimer.singleShot(0, reveal_window)
        else:
            set_splash_status(app, splash, "Finishing startup...")
    except Exception as error:
        splash.close()
        if is_packaged():
            QMessageBox.critical(
                None,
                "Ledgerly could not start",
                f"Ledgerly could not finish setup.\n\n{error}",
            )
            sys.exit(1)
        raise

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
