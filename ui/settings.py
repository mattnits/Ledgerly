from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QFrame,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
    QVBoxLayout,
)

from database.reset import reset_financial_data
from database.user_management import delete_user
from ui.components.page_header import PageHeader
from ui.components.toggle_switch import ToggleSwitch
from ui.preferences import (
    open_fullscreen_enabled,
    save_imported_files_enabled,
    set_open_fullscreen,
    set_save_imported_files,
)
from ui.theme import set_button_icon, set_delete_button_icon
from utils.app_paths import import_archive_label


class SettingsPage(QWidget):
    data_reset = Signal()
    profile_deleted = Signal(str)
    fullscreen_preference_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("settingsPage")
        self.current_user_id: str | None = None
        self.current_user_name = "this profile"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(18)

        layout.addWidget(PageHeader("Settings", "Manage application data and preferences"))

        preferences = QFrame()
        preferences.setObjectName("settingsCard")
        preferences_layout = QVBoxLayout(preferences)
        preferences_layout.setContentsMargins(20, 18, 20, 18)
        preferences_layout.setSpacing(12)
        preferences_title = QLabel("Display")
        preferences_title.setObjectName("sectionTitle")
        preferences_layout.addWidget(preferences_title)

        fullscreen_row = QHBoxLayout()
        fullscreen_copy = QVBoxLayout()
        fullscreen_copy.setSpacing(3)
        fullscreen_label = QLabel("Open in fullscreen")
        fullscreen_label.setObjectName("settingsOptionTitle")
        fullscreen_description = QLabel(
            "Use the entire screen when Finance starts. Turn this off for a windowed app."
        )
        fullscreen_description.setObjectName("mutedLabel")
        fullscreen_description.setWordWrap(True)
        fullscreen_copy.addWidget(fullscreen_label)
        fullscreen_copy.addWidget(fullscreen_description)
        fullscreen_row.addLayout(fullscreen_copy, 1)
        self.fullscreen_toggle = ToggleSwitch()
        self.fullscreen_toggle.setObjectName("fullscreenToggle")
        self.fullscreen_toggle.setAccessibleName("Open in fullscreen")
        self.fullscreen_toggle.setToolTip("Open Finance in fullscreen")
        self.fullscreen_toggle.setChecked(open_fullscreen_enabled())
        self.fullscreen_toggle.toggled.connect(self._set_fullscreen_preference)
        fullscreen_row.addWidget(self.fullscreen_toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        preferences_layout.addLayout(fullscreen_row)
        layout.addWidget(preferences)

        imports = QFrame()
        imports.setObjectName("settingsCard")
        imports_layout = QVBoxLayout(imports)
        imports_layout.setContentsMargins(20, 18, 20, 18)
        imports_layout.setSpacing(12)
        imports_title = QLabel("Statement imports")
        imports_title.setObjectName("sectionTitle")
        imports_layout.addWidget(imports_title)

        save_files_row = QHBoxLayout()
        save_files_copy = QVBoxLayout()
        save_files_copy.setSpacing(3)
        save_files_label = QLabel("Save imported source files")
        save_files_label.setObjectName("settingsOptionTitle")
        save_files_description = QLabel(
            "Default the import dialog to save every selected statement under "
            f"{import_archive_label()}."
        )
        save_files_description.setObjectName("mutedLabel")
        save_files_description.setWordWrap(True)
        save_files_copy.addWidget(save_files_label)
        save_files_copy.addWidget(save_files_description)
        save_files_row.addLayout(save_files_copy, 1)
        self.save_import_files_toggle = ToggleSwitch()
        self.save_import_files_toggle.setObjectName("saveImportFilesToggle")
        self.save_import_files_toggle.setAccessibleName(
            "Save imported source files by default"
        )
        self.save_import_files_toggle.setToolTip(
            "Default new imports to save their source files"
        )
        self.save_import_files_toggle.setChecked(save_imported_files_enabled())
        self.save_import_files_toggle.toggled.connect(
            self._set_save_imported_files_preference
        )
        save_files_row.addWidget(
            self.save_import_files_toggle,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        imports_layout.addLayout(save_files_row)
        layout.addWidget(imports)

        card = QFrame()
        card.setObjectName("settingsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(8)
        title = QLabel("Transaction data")
        title.setObjectName("sectionTitle")
        card_layout.addWidget(title)

        reset_row = QHBoxLayout()
        description = QLabel(
            "Delete all transactions and statement import history. Accounts, "
            "investments, categories, and categorization rules will be kept."
        )
        description.setWordWrap(True)
        description.setObjectName("mutedLabel")
        reset_row.addWidget(description, 1)

        reset_button = QPushButton("Delete Data")
        reset_button.setObjectName("dangerButton")
        reset_button.setToolTip("Delete all transaction and statement import data")
        set_delete_button_icon(reset_button)
        reset_button.clicked.connect(self.confirm_reset)
        reset_row.addWidget(reset_button)
        card_layout.addLayout(reset_row)
        layout.addWidget(card)

        danger = QFrame()
        danger.setObjectName("settingsCard")
        danger_layout = QVBoxLayout(danger)
        danger_layout.setContentsMargins(20, 18, 20, 18)
        danger_layout.setSpacing(8)
        danger_title = QLabel("Danger Zone")
        danger_title.setObjectName("sectionTitle")
        danger_layout.addWidget(danger_title)
        delete_row = QHBoxLayout()
        delete_description = QLabel(
            "Permanently delete your profile and all financial data owned by it."
        )
        delete_description.setWordWrap(True)
        delete_description.setObjectName("mutedLabel")
        delete_row.addWidget(delete_description, 1)
        self.delete_profile_button = QPushButton("Delete My Profile")
        self.delete_profile_button.setObjectName("dangerButton")
        set_button_icon(self.delete_profile_button, "fa6s.trash", size=14)
        self.delete_profile_button.clicked.connect(self.confirm_delete_profile)
        delete_row.addWidget(self.delete_profile_button)
        danger_layout.addLayout(delete_row)
        layout.addWidget(danger)

        layout.addStretch()

    @property
    def open_fullscreen(self) -> bool:
        return self.fullscreen_toggle.isChecked()

    def _set_fullscreen_preference(self, enabled: bool) -> None:
        set_open_fullscreen(enabled)
        self.fullscreen_preference_changed.emit(enabled)

    def _set_save_imported_files_preference(self, enabled: bool) -> None:
        set_save_imported_files(enabled)

    def set_current_user(
        self, user_id: str | None, user_name: str | None = None
    ) -> None:
        self.current_user_id = user_id
        self.current_user_name = user_name or "this profile"
        self.delete_profile_button.setEnabled(user_id is not None)

    def confirm_delete_profile(self) -> None:
        if self.current_user_id is None:
            return
        prompt = (
            f"Delete {self.current_user_name}?\n\nThis permanently deletes transactions, accounts, "
            "import history, investments, savings data, budgets/goals, rules, "
            "custom categories where safe, memberships, and profile settings.\n\n"
            "This cannot be undone. Type DELETE to continue."
        )
        confirmation, accepted = QInputDialog.getText(
            self, "Delete My Profile", prompt
        )
        if not accepted or confirmation != "DELETE":
            return
        user_id = self.current_user_id
        try:
            delete_user(
                user_id,
                user_id,
                allow_self=True,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Profile not deleted", str(exc))
            return
        self.profile_deleted.emit(user_id)

    def confirm_reset(self) -> None:
        answer = QMessageBox.question(
            self,
            "Delete transaction data",
            "Delete all transactions and statement import history for every user? "
            "This cannot be undone. Accounts, investments, categories, and "
            "categorization rules will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            reset_financial_data()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Delete failed",
                f"Could not delete transaction data:\n{exc}",
            )
            return

        self.data_reset.emit()
