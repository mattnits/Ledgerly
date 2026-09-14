import sys

from PySide6.QtWidgets import QApplication

from ui.shell import ShellWindow


def main():

    app = QApplication(sys.argv)

    window = ShellWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()