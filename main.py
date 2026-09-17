import sys

from PySide6.QtWidgets import QApplication

from database.db import ensure_categories, init_db
from ui.shell import ShellWindow


def main():
    init_db()
    ensure_categories()

    app = QApplication(sys.argv)

    window = ShellWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
