from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from database.categories import add_category, delete_category, list_categories
from ui.components.generic_dialog import GenericDialog
from ui.components.generic_table import GenericTable
from ui.components.page_header import PageHeader
from utils.constants import CATEGORIES_LABEL


class CategoriesPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)

        add_button = QPushButton("Add Category")
        add_button.clicked.connect(self.open_add_dialog)
        layout.addWidget(PageHeader(CATEGORIES_LABEL, action_button=add_button))

        self.table = GenericTable(("Name", "Color", "Type", "Action"))
        layout.addWidget(self.table)
        self.reload()

    def reload(self):
        rows = []
        for category_id, name, color, is_default in list_categories():
            color_label = QLabel(f"●  {color}")
            color_label.setStyleSheet(f"color: {color}; padding-left: 14px;")
            if is_default:
                action = "Protected"
            else:
                action = QPushButton("Delete")
                action.clicked.connect(
                    lambda checked=False, item_id=category_id, item_name=name:
                    self.confirm_delete(item_id, item_name)
                )
            rows.append((name, color_label, "Default" if is_default else "Custom", action))
        self.table.set_rows(rows)

    def open_add_dialog(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(QLabel("Name"))
        name_input = QLineEdit()
        name_input.setMaxLength(100)
        name_input.setPlaceholderText("Category name")
        layout.addWidget(name_input)
        layout.addWidget(QLabel("Color"))

        color = QColor("#64748b")
        color_row = QHBoxLayout()
        color_preview = QLabel()
        color_preview.setFixedSize(32, 32)
        color_button = QPushButton("Choose Color")

        def update_preview():
            color_preview.setStyleSheet(
                f"background: {color.name()}; border-radius: 8px;"
            )

        def choose_color():
            selected = QColorDialog.getColor(color, dialog, "Choose Category Color")
            if selected.isValid():
                color.setNamedColor(selected.name())
                update_preview()

        color_button.clicked.connect(choose_color)
        color_row.addWidget(color_preview)
        color_row.addWidget(color_button)
        color_row.addStretch()
        layout.addLayout(color_row)
        layout.addStretch()

        dialog = GenericDialog("Add Category", content, self)
        update_preview()

        def submit():
            try:
                add_category(name_input.text(), color.name())
            except ValueError as exc:
                QMessageBox.warning(dialog, "Invalid Category", str(exc))
            except Exception as exc:
                QMessageBox.critical(dialog, "Error", f"Could not add category:\n{exc}")
            else:
                dialog.accept()
                self.reload()

        dialog.submitted.connect(submit)
        dialog.exec()

    def confirm_delete(self, category_id: int, name: str):
        answer = QMessageBox.question(
            self,
            "Delete Category",
            f"Delete '{name}'? Transactions using it will become uncategorized.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_category(category_id)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not delete category:\n{exc}")
        else:
            self.reload()
