from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QBoxLayout,
    QCheckBox,
    QColorDialog,
    QDialog,
    QFrame,
    QGridLayout,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.db import SessionLocal
from app.services.groups import create_group, get_group, update_group
from app.models.models import User
from app.services.user_management import create_user, update_group_as_admin, update_user
from app.ui.sidebar import ElidedLabel, avatar_icon
from app.ui.theme import (
    COLORS,
    awesome_icon,
    set_button_icon,
    spaced_text_icon,
    spaced_text_icon_size,
)


PROFILE_COLORS = (
    "#3397f5",
    "#9148e8",
    "#ef4a8b",
    "#ff5b5b",
    "#ff8a34",
    "#ffd04a",
    "#57c978",
    "#2ebcc9",
    "#55a4f2",
    "#6265ed",
    "#a668e5",
    "#8793aa",
)


class ColorSwatchButton(QToolButton):
    color_selected = Signal(str)

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setObjectName("profileColorSwatch")
        self.setProperty("selected", False)
        self.setFixedSize(40, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(color.upper())
        self.setAccessibleName(f"Profile colour {color.upper()}")
        self.clicked.connect(lambda: self.color_selected.emit(self.color))
        self._apply_style()

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self._apply_style()

    def _apply_style(self) -> None:
        border = "3px solid #62acff" if self.property("selected") else "3px solid transparent"
        self.setStyleSheet(f"""
            QToolButton#profileColorSwatch {{
                background: {self.color};
                border: {border};
                border-radius: 20px;
            }}
            QToolButton#profileColorSwatch:hover {{
                border: 3px solid #c4ddf9;
            }}
        """)


class AddUserDialog(QDialog):
    """Responsive modal user-creation form shared by onboarding and the sidebar."""

    user_created = Signal(str)
    user_updated = Signal(str)
    group_created = Signal(int)
    group_updated = Signal(int)

    MINIMUM_WIDTH = 560
    MINIMUM_HEIGHT = 620
    PREFERRED_MAX_WIDTH = 800
    PREFERRED_MAX_HEIGHT = 780
    EDIT_USER_MINIMUM_HEIGHT = 500
    EDIT_USER_PREFERRED_HEIGHT = 540
    EDIT_USER_PREFERRED_WIDTH = 700
    STACKED_CONTENT_WIDTH = 620

    def __init__(
        self,
        parent=None,
        session_factory=SessionLocal,
        *,
        group_id: int | None = None,
        user_id: str | None = None,
        actor_user_id: str | None = None,
    ):
        super().__init__(parent)
        self.session_factory = session_factory
        self.group_id = group_id
        self.user_id = user_id
        self.actor_user_id = actor_user_id
        if group_id is not None and user_id is not None:
            raise ValueError("Only one profile can be edited at a time")
        self.creation_type = "group" if group_id is not None else "user"
        self.selected_color = QColor(PROFILE_COLORS[0])
        self.setObjectName("addUserDialog")
        self.setWindowTitle("Add User")
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self._fit_to_available_screen()

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(12, 12, 12, 12)
        self.card = QFrame()
        self.card.setObjectName("addUserDialogCard")
        outer_layout.addWidget(self.card)
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 7)
        shadow.setColor(QColor(0, 0, 0, 155))
        self.card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(0)
        header = QHBoxLayout()
        header.setSpacing(8)
        icon_frame = QFrame()
        icon_frame.setObjectName("dialogIconFrame")
        icon_frame.setFixedSize(56, 56)
        icon_layout = QVBoxLayout(icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(
            awesome_icon("fa6s.user-plus", color="#56a9ff").pixmap(27, 27)
        )
        icon_layout.addWidget(icon)
        header.addWidget(icon_frame, alignment=Qt.AlignmentFlag.AlignTop)
        heading = QVBoxLayout()
        heading.setSpacing(5)
        self.title_label = QLabel("Add User")
        self.title_label.setObjectName("addUserDialogTitle")
        self.subtitle_label = QLabel(
            "Create a new user to keep transactions separate."
        )
        self.subtitle_label.setObjectName("addUserDialogSubtitle")
        self.subtitle_label.setWordWrap(True)
        heading.addWidget(self.title_label)
        heading.addWidget(self.subtitle_label)
        header.addLayout(heading, 1)
        self.close_button = QToolButton()
        self.close_button.setObjectName("addUserDialogClose")
        self.close_button.setFixedSize(30, 30)
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setToolTip("Close")
        self.close_button.setAccessibleName("Close add user dialog")
        set_button_icon(
            self.close_button,
            "fa6s.xmark",
            color=COLORS["text_muted"],
            active_color=COLORS["text"],
            size=17,
        )
        self.close_button.clicked.connect(self.reject)
        header.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)
        layout.addSpacing(16)

        self.type_selector = QWidget()
        self.type_selector.setObjectName("profileTypeSelector")
        self.type_selector.setMinimumHeight(46)
        self.type_selector.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        type_layout = QHBoxLayout(self.type_selector)
        type_layout.setContentsMargins(4, 4, 4, 4)
        type_layout.setSpacing(4)
        self.user_button = QPushButton("User")
        self.group_button = QPushButton("Group")
        self.type_button_group = QButtonGroup(self)
        self.type_button_group.setExclusive(True)
        for button, object_name in (
            (self.user_button, "userTypeButton"),
            (self.group_button, "groupTypeButton"),
        ):
            button.setObjectName(object_name)
            button.setCheckable(True)
            button.setMinimumHeight(38)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.type_button_group.addButton(button)
            type_layout.addWidget(button, 1)
        self.user_button.clicked.connect(lambda: self.set_creation_type("user"))
        self.group_button.clicked.connect(lambda: self.set_creation_type("group"))
        layout.addWidget(self.type_selector)
        layout.addSpacing(18)

        self.content_scroll = QScrollArea()
        self.content_scroll.setObjectName("addProfileContentScroll")
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.content_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.content_widget = QWidget()
        self.content_widget.setObjectName("addProfileContent")
        self.content_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.content_widget.setLayout(self.content_layout)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(22)
        self.content_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.form_layout = QVBoxLayout()
        self.form_layout.setSpacing(0)
        self.form_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.name_label = QLabel("Name")
        self.name_label.setObjectName("addUserFieldLabel")
        self.name_input = QLineEdit()
        self.name_input.setObjectName("addUserNameInput")
        self.name_input.setPlaceholderText("Enter a name (e.g. Alex)")
        self.name_input.setMaxLength(100)
        self.name_input.setFixedHeight(40)
        self.name_input.setAccessibleName("Name")
        self.name_label.setBuddy(self.name_input)
        self.name_input.textChanged.connect(self.update_preview)
        self.form_layout.addWidget(self.name_label)
        self.form_layout.addSpacing(7)
        self.form_layout.addWidget(self.name_input)
        self.form_layout.addSpacing(20)
        self.color_label = QLabel("Profile Colour")
        self.color_label.setObjectName("addUserFieldLabel")
        self.form_layout.addWidget(self.color_label)
        self.form_layout.addSpacing(10)

        palette = QGridLayout()
        palette.setContentsMargins(0, 0, 0, 0)
        palette.setHorizontalSpacing(12)
        palette.setVerticalSpacing(12)
        self.color_swatches: list[ColorSwatchButton] = []
        for index, color in enumerate(PROFILE_COLORS):
            swatch = ColorSwatchButton(color)
            swatch.color_selected.connect(self.select_color)
            palette.addWidget(swatch, index // 6, index % 6)
            self.color_swatches.append(swatch)
        self.color_button = self.color_swatches[0]
        self.color_label.setBuddy(self.color_button)
        self.form_layout.addLayout(palette)
        self.form_layout.addSpacing(18)

        self.members_widget = QWidget()
        self.members_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        members_layout = QVBoxLayout(self.members_widget)
        members_layout.setContentsMargins(0, 0, 0, 0)
        members_layout.setSpacing(7)
        self.members_label = QLabel("Members")
        self.members_label.setObjectName("addUserFieldLabel")
        members_layout.addWidget(self.members_label)
        self.members_scroll = QScrollArea()
        self.members_scroll.setObjectName("groupMembersScroll")
        self.members_scroll.setWidgetResizable(True)
        self.members_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.members_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.members_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.members_scroll.setMinimumHeight(120)
        self.members_scroll.setMaximumHeight(260)
        self.members_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.members_list = QWidget()
        self.members_list.setObjectName("groupMembersList")
        self.members_list.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.members_list_layout = QVBoxLayout(self.members_list)
        self.members_list_layout.setSizeConstraint(
            QLayout.SizeConstraint.SetMinAndMaxSize
        )
        self.members_list_layout.setContentsMargins(8, 7, 8, 7)
        self.members_list_layout.setSpacing(4)
        self.member_checkboxes: dict[str, QCheckBox] = {}
        for user in self._load_users():
            checkbox = QCheckBox(user["name"])
            checkbox.setObjectName("groupMemberChoice")
            checkbox.setIcon(spaced_text_icon(
                avatar_icon(user["name"], user["color"], 28), 28
            ))
            checkbox.setIconSize(spaced_text_icon_size(28))
            checkbox.setMinimumHeight(42)
            checkbox.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            checkbox.toggled.connect(self.update_preview)
            checkbox.setAccessibleName(f"Include {user['name']} in group")
            self.member_checkboxes[user["id"]] = checkbox
            self.members_list_layout.addWidget(checkbox)
        self.members_list_layout.addStretch()
        self.members_scroll.setWidget(self.members_list)
        members_layout.addWidget(self.members_scroll, 1)
        self.form_layout.addWidget(self.members_widget)
        self.form_layout.addStretch()
        self.content_layout.addLayout(self.form_layout, 2)

        self.preview_card = QFrame()
        self.preview_card.setObjectName("addUserPreviewCard")
        self.preview_card.setMinimumWidth(150)
        self.preview_card.setMaximumWidth(220)
        self.preview_card.setMinimumHeight(270)
        self.preview_card.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        preview_layout = QVBoxLayout(self.preview_card)
        preview_layout.setContentsMargins(18, 16, 18, 20)
        preview_title = QLabel("Preview")
        preview_title.setObjectName("addUserPreviewTitle")
        preview_layout.addWidget(preview_title)
        preview_layout.addStretch()
        self.color_preview = QLabel()
        self.color_preview.setObjectName("addUserColorPreview")
        self.color_preview.setFixedSize(76, 76)
        self.color_preview.setAccessibleName("Selected profile colour")
        preview_layout.addWidget(
            self.color_preview, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        preview_layout.addSpacing(12)
        self.preview_name = ElidedLabel("New user")
        self.preview_name.setObjectName("addUserPreviewName")
        self.preview_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_name.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        preview_layout.addWidget(self.preview_name)
        self.preview_type = QLabel("Personal")
        self.preview_type.setObjectName("addUserPreviewType")
        self.preview_type.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_type.setWordWrap(True)
        self.preview_type.setMinimumHeight(30)
        preview_layout.addWidget(self.preview_type)
        preview_layout.addStretch()
        self.content_layout.addWidget(self.preview_card, 1)
        self.content_scroll.setWidget(self.content_widget)
        layout.addWidget(self.content_scroll, 1)
        layout.addSpacing(20)

        self.footer = QWidget()
        self.footer.setObjectName("addUserFooter")
        footer = QHBoxLayout(self.footer)
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(12)
        footer.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("addUserCancelButton")
        self.cancel_button.setMinimumSize(98, 40)
        self.cancel_button.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self.cancel_button.clicked.connect(self.reject)
        self.add_user_button = QPushButton("Add User")
        self.add_user_button.setObjectName("primaryButton")
        self.add_user_button.setMinimumSize(138, 40)
        self.add_user_button.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self.add_user_button.setDefault(True)
        set_button_icon(
            self.add_user_button,
            "fa6s.user-plus",
            color="#ffffff",
            active_color="#ffffff",
            size=16,
        )
        self.add_user_button.clicked.connect(self.add_user)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.add_user_button)
        layout.addWidget(self.footer)

        self.setStyleSheet(self._stylesheet())
        self.set_creation_type(self.creation_type)
        if self.group_id is not None:
            self.type_selector.hide()
            self._load_group()
        elif self.user_id is not None:
            self.type_selector.hide()
            self._load_user()
        self._apply_content_direction()
        self.name_input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _load_users(self) -> list[dict[str, str]]:
        from sqlalchemy import select
        with self.session_factory() as session:
            return [
                {"id": user.id, "name": user.name, "color": user.color}
                for user in session.scalars(select(User).order_by(User.created_at, User.id))
            ]

    def _load_group(self) -> None:
        group = get_group(self.group_id, session_factory=self.session_factory)
        if group is None:
            raise ValueError("Group no longer exists")
        self.name_input.setText(group["name"])
        self.selected_color = QColor(group["color"])
        for user_id in group["member_ids"]:
            checkbox = self.member_checkboxes.get(user_id)
            if checkbox is not None:
                checkbox.setChecked(True)
        self.update_preview()

    def _load_user(self) -> None:
        with self.session_factory() as session:
            user = session.get(User, self.user_id)
            if user is None:
                raise ValueError("User no longer exists")
            self.name_input.setText(user.name)
            self.selected_color = QColor(user.color)
        editing_self = self.actor_user_id == self.user_id
        self.title_label.setText("Edit Profile" if editing_self else "Edit User")
        self.subtitle_label.setText(
            "Update your name and profile colour."
            if editing_self
            else "Update this user's name and profile colour."
        )
        self.add_user_button.setText("Save User")
        set_button_icon(
            self.add_user_button,
            "fa6s.check",
            color="#ffffff",
            active_color="#ffffff",
            size=15,
        )
        self.update_preview()

    def set_creation_type(self, creation_type: str) -> None:
        if creation_type not in {"user", "group"}:
            raise ValueError("Unknown profile type")
        self.creation_type = creation_type
        is_group = creation_type == "group"
        self.user_button.setChecked(not is_group)
        self.group_button.setChecked(is_group)
        self.members_widget.setVisible(is_group)
        self.title_label.setText(
            "Edit Group" if self.group_id is not None
            else "Edit User" if self.user_id is not None
            else ("Add Group" if is_group else "Add User")
        )
        self.subtitle_label.setText(
            "Combine multiple users into one shared financial view."
            if is_group
            else "Create a new user to keep transactions separate."
        )
        self.name_label.setText("Group Name" if is_group else "Name")
        self.name_input.setPlaceholderText(
            "Enter a group name (e.g. Household)"
            if is_group
            else "Enter a name (e.g. Alex)"
        )
        button_text = (
            "Save Group" if self.group_id is not None
            else "Save User" if self.user_id is not None
            else ("Add Group" if is_group else "Add User")
        )
        self.add_user_button.setText(button_text)
        set_button_icon(
            self.add_user_button,
            "fa6s.check" if self.user_id is not None or self.group_id is not None
            else "fa6s.user-plus" if not is_group
            else "fa6s.users",
            color="#ffffff",
            active_color="#ffffff",
            size=15,
        )
        self.preview_type.setText("Group • 0 members" if is_group else "Personal")
        self.update_preview()

    def _preferred_width(self) -> int:
        parent_width = self.parentWidget().width() if self.parentWidget() else 700
        if self.user_id is not None:
            return max(
                self.MINIMUM_WIDTH,
                min(self.EDIT_USER_PREFERRED_WIDTH, int(parent_width * 0.68)),
            )
        return max(
            self.MINIMUM_WIDTH,
            min(self.PREFERRED_MAX_WIDTH, int(parent_width * 0.68)),
        )

    def _preferred_height(self) -> int:
        parent_height = self.parentWidget().height() if self.parentWidget() else 800
        if self.user_id is not None:
            return max(
                self.EDIT_USER_MINIMUM_HEIGHT,
                min(self.EDIT_USER_PREFERRED_HEIGHT, int(parent_height * 0.78)),
            )
        return max(
            self.MINIMUM_HEIGHT,
            min(self.PREFERRED_MAX_HEIGHT, int(parent_height * 0.90)),
        )

    def _fit_to_available_screen(self) -> None:
        screen = self.screen()
        available = screen.availableGeometry() if screen is not None else None
        maximum_width = (
            max(480, available.width() - 32)
            if available is not None
            else self.PREFERRED_MAX_WIDTH
        )
        maximum_height = (
            max(520, available.height() - 16)
            if available is not None
            else self.PREFERRED_MAX_HEIGHT
        )
        self.setMaximumSize(maximum_width, maximum_height)
        minimum_height = (
            self.EDIT_USER_MINIMUM_HEIGHT
            if self.user_id is not None
            else self.MINIMUM_HEIGHT
        )
        self.setMinimumSize(
            min(self.MINIMUM_WIDTH, maximum_width),
            min(minimum_height, maximum_height),
        )
        self.resize(
            min(self._preferred_width(), maximum_width),
            min(self._preferred_height(), maximum_height),
        )
        self._apply_content_direction()

    def _apply_content_direction(self) -> None:
        if not hasattr(self, "content_layout"):
            return
        stacked = self.width() < self.STACKED_CONTENT_WIDTH
        self.content_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if stacked
            else QBoxLayout.Direction.LeftToRight
        )
        self.preview_card.setMaximumWidth(16777215 if stacked else 220)
        self.preview_card.setMaximumHeight(300 if stacked else 16777215)

    def select_color(self, color: str) -> None:
        selected = QColor(color)
        if not selected.isValid():
            return
        self.selected_color = selected
        self.update_preview()

    def open_color_picker(self) -> None:
        """Keep custom-colour support available to programmatic callers."""
        color = QColorDialog.getColor(
            self.selected_color, self, "Choose Profile Colour"
        )
        if color.isValid():
            self.selected_color = color
            self.update_preview()

    def update_color_preview(self) -> None:
        """Backward-compatible alias used by existing integrations."""
        self.update_preview()

    def update_preview(self) -> None:
        fallback = "New group" if self.creation_type == "group" else "New user"
        name = self.name_input.text().strip() or fallback
        color = self.selected_color.name()
        self.color_preview.setPixmap(avatar_icon(
            name, color, 76, profile_type=self.creation_type
        ).pixmap(76, 76))
        self.color_preview.setProperty("profileType", self.creation_type)
        self.color_preview.setToolTip(color.upper())
        self.preview_name.setText(name)
        if self.creation_type == "group":
            count = len(self.selected_member_ids())
            self.preview_type.setText(
                f"Group • {count} member{'s' if count != 1 else ''}"
            )
        for swatch in self.color_swatches:
            swatch.set_selected(swatch.color.casefold() == color.casefold())

    def add_user(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            label = "group name" if self.creation_type == "group" else "name"
            QMessageBox.warning(self, "Missing Name", f"Please enter a {label}.")
            self.name_input.setFocus()
            return

        if self.creation_type == "group":
            self._save_group(name)
            return

        self.add_user_button.setEnabled(False)
        try:
            if self.user_id is None:
                user_id = create_user(
                    name, self.selected_color.name(),
                    session_factory=self.session_factory,
                )
            else:
                if self.actor_user_id is None:
                    raise ValueError("The current user is required to edit a profile")
                update_user(
                    self.actor_user_id,
                    self.user_id,
                    name,
                    self.selected_color.name(),
                    session_factory=self.session_factory,
                )
                user_id = self.user_id
        except Exception as exc:
            self.add_user_button.setEnabled(True)
            QMessageBox.critical(
                self, "Error", f"Could not create user:\n{exc}"
            )
            return

        self.name_input.clear()
        self.accept()
        if self.user_id is None:
            self.user_created.emit(user_id)
        else:
            self.user_updated.emit(user_id)

    def selected_member_ids(self) -> tuple[str, ...]:
        return tuple(
            user_id
            for user_id, checkbox in self.member_checkboxes.items()
            if checkbox.isChecked()
        )

    def _save_group(self, name: str) -> None:
        member_ids = self.selected_member_ids()
        if not member_ids:
            QMessageBox.warning(
                self, "Missing Members", "Select at least one group member."
            )
            return
        self.add_user_button.setEnabled(False)
        try:
            if self.group_id is None:
                group_id = create_group(
                    name,
                    self.selected_color.name(),
                    member_ids,
                    session_factory=self.session_factory,
                )
            else:
                group_id = self.group_id
                if self.actor_user_id is None:
                    update_group(
                        group_id,
                        name,
                        self.selected_color.name(),
                        member_ids,
                        session_factory=self.session_factory,
                    )
                else:
                    update_group_as_admin(
                        self.actor_user_id,
                        group_id,
                        name,
                        self.selected_color.name(),
                        member_ids,
                        session_factory=self.session_factory,
                    )
        except Exception as exc:
            self.add_user_button.setEnabled(True)
            QMessageBox.critical(self, "Error", f"Could not save group:\n{exc}")
            return
        self.accept()
        if self.group_id is None:
            self.group_created.emit(group_id)
        else:
            self.group_updated.emit(group_id)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API spelling
        self._fit_to_available_screen()
        super().showEvent(event)
        self._center_on_parent()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API spelling
        super().resizeEvent(event)
        self._apply_content_direction()

    def _center_on_parent(self) -> None:
        parent = self.parentWidget()
        target = parent.window().frameGeometry() if parent else self.screen().availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(target.center())
        available = self.screen().availableGeometry()
        x = max(available.left(), min(frame.left(), available.right() - frame.width() + 1))
        y = max(available.top(), min(frame.top(), available.bottom() - frame.height() + 1))
        self.move(x, y)

    @staticmethod
    def _stylesheet() -> str:
        return f"""
            QDialog#addUserDialog {{ background: transparent; }}
            QFrame#addUserDialogCard {{
                background: #111820;
                border: 1px solid #344351;
                border-radius: 16px;
            }}
            QLabel#addUserDialogTitle {{
                color: {COLORS['text']}; font-size: 24px; font-weight: 750;
            }}
            QLabel#addUserDialogSubtitle {{
                color: #aebbd0; font-size: 14px;
            }}
            QLabel#addUserFieldLabel, QLabel#addUserPreviewTitle {{
                color: #eef1f5; font-size: 13px; font-weight: 500;
            }}
            QToolButton#addUserDialogClose {{
                background: transparent; border: none; border-radius: 7px;
            }}
            QToolButton#addUserDialogClose:hover {{ background: #252c34; }}
            QLineEdit#addUserNameInput {{
                background: #171d24;
                border: 1px solid #36414d;
                border-radius: 9px;
                min-height: 38px;
                max-height: 38px;
                padding: 0 13px;
            }}
            QLineEdit#addUserNameInput:focus {{ border-color: #398cff; }}
            QWidget#profileTypeSelector {{
                background: #0c1218;
                border: 1px solid #34404c;
                border-radius: 10px;
            }}
            QPushButton#userTypeButton, QPushButton#groupTypeButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 7px;
                color: {COLORS['text_muted']};
                font-size: 13px;
                font-weight: 600;
                padding: 0 16px;
                outline: none;
            }}
            QPushButton#userTypeButton:hover:!checked,
            QPushButton#groupTypeButton:hover:!checked {{
                background: #18222d;
                color: {COLORS['text']};
            }}
            QPushButton#userTypeButton:checked,
            QPushButton#groupTypeButton:checked {{
                background: #245b94;
                border-color: #3478bd;
                color: #ffffff;
            }}
            QPushButton#userTypeButton:focus,
            QPushButton#groupTypeButton:focus {{
                border-color: #3478bd;
            }}
            QScrollArea#groupMembersScroll {{
                background: #0e141a;
                border: 1px solid #34404c;
                border-radius: 9px;
            }}
            QScrollArea#groupMembersScroll > QWidget > QWidget#groupMembersList {{
                background: #0e141a;
                border: none;
            }}
            QScrollArea#addProfileContentScroll,
            QScrollArea#addProfileContentScroll > QWidget > QWidget#addProfileContent {{
                background: transparent;
                border: none;
            }}
            QCheckBox#groupMemberChoice {{
                color: {COLORS['text']};
                spacing: 10px;
                padding: 5px 8px;
                border: 1px solid transparent;
                border-radius: 7px;
            }}
            QCheckBox#groupMemberChoice:hover {{
                background: #17212b;
                border-color: #293847;
            }}
            QScrollBar:vertical {{
                width: 8px;
                margin: 5px 2px 5px 0;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                min-height: 28px;
                background: #465565;
                border-radius: 4px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QFrame#addUserPreviewCard {{
                background: #0e141a;
                border: 1px solid #2f3944;
                border-radius: 11px;
            }}
            QLabel#addUserPreviewName {{
                color: {COLORS['text']}; font-size: 15px; font-weight: 650;
            }}
            QLabel#addUserPreviewType {{
                color: {COLORS['text_muted']}; font-size: 12px;
            }}
            QPushButton#addUserCancelButton {{
                min-height: 38px; max-height: 38px; padding: 0 18px;
            }}
            QPushButton#primaryButton {{
                min-height: 38px; max-height: 38px; padding: 0 18px;
            }}
        """


# Keep the old import name working for callers while the UI is now a dialog.
AddUserPage = AddUserDialog
