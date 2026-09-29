import sys

from PySide6.QtWidgets import QApplication

from database.db import ensure_categories, init_db
from ui.shell import ShellWindow
from ui.theme import apply_theme


def main():
    init_db()
    ensure_categories()

    app = QApplication(sys.argv)
    apply_theme(app)

    window = ShellWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
