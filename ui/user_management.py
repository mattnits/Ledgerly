from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from database.db import SessionLocal
from database.user_management import (
    delete_group,
    delete_user,
    leave_group,
    management_snapshot,
    set_admin,
)
from ui.components.page_header import PageHeader
from ui.sidebar import ElidedLabel, avatar_icon
from ui.theme import (
    COLORS,
    awesome_icon,
    set_button_icon,
    set_delete_button_icon,
    set_icon_only_button,
)


def _display_date(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%b %d, %Y").replace(" 0", " ")


class UserManagementPage(QWidget):
    """Responsive, role-aware local user and group administration."""

    edit_user_requested = Signal(str)
    edit_group_requested = Signal(int)
    add_profile_requested = Signal()
    profiles_changed = Signal()

    COMPACT_WIDTH = 760
    NARROW_WIDTH = 610
    USER_ACTION_WIDTH = 126
    GROUP_ACTION_WIDTH = 82

    def __init__(self, *, session_factory=SessionLocal):
        super().__init__()
        self.session_factory = session_factory
        self.current_user_id: str | None = None
        self.current_user_is_admin = False
        self._top_is_stacked: bool | None = None
        self._user_rows: list[QWidget] = []
        self._group_rows: list[QWidget] = []
        self._user_group_widgets: list[QWidget] = []
        self._user_created_widgets: list[QWidget] = []
        self._group_created_widgets: list[QWidget] = []
        self._user_grids: list[QGridLayout] = []
        self._group_grids: list[QGridLayout] = []
        self.setObjectName("userManagementPage")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(16)

        self.add_profile_button = QPushButton("Add User or Group")
        self.add_profile_button.setObjectName("pageActionButton")
        set_button_icon(
            self.add_profile_button,
            "fa6s.plus",
            color="#ffffff",
            active_color="#ffffff",
            size=14,
        )
        self.add_profile_button.clicked.connect(self.add_profile_requested.emit)
        outer.addWidget(PageHeader(
            "User Management",
            "Manage users, groups and permissions.",
            self.add_profile_button,
        ))

        self.scroll = QScrollArea()
        self.scroll.setObjectName("userManagementScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.content = QWidget()
        self.content.setObjectName("userManagementContent")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 8, 0)
        self.content_layout.setSpacing(14)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll, 1)
        self.setStyleSheet(self._stylesheet())

    def set_current_user(self, user_id: str | None) -> None:
        self.current_user_id = user_id
        self.reload()

    def reload(self) -> None:
        self.current_user_is_admin = False
        self.add_profile_button.setEnabled(False)
        self.add_profile_button.setToolTip(
            "Only Admins can add users or groups."
        )
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._top_is_stacked = None
        self._user_rows = []
        self._group_rows = []
        self._user_group_widgets = []
        self._user_created_widgets = []
        self._group_created_widgets = []
        self._user_grids = []
        self._group_grids = []

        if self.current_user_id is None:
            self.content_layout.addWidget(self._empty_card("No current user."))
            return
        try:
            snapshot = management_snapshot(
                self.current_user_id, session_factory=self.session_factory
            )
        except ValueError:
            self.content_layout.addWidget(
                self._empty_card("The current user no longer exists.")
            )
            return

        current = snapshot["current_user"]
        self.current_user_is_admin = bool(current["is_admin"])
        self.add_profile_button.setEnabled(self.current_user_is_admin)
        self.add_profile_button.setToolTip(
            "" if self.current_user_is_admin
            else "Only Admins can add users or groups."
        )
        self.content_layout.addWidget(
            self._overview_card(current, snapshot["memberships"])
        )
        self.users_card = self._users_card(snapshot["users"])
        self.groups_card = self._groups_card(snapshot["groups"])
        self.users_card.setEnabled(self.current_user_is_admin)
        self.groups_card.setEnabled(self.current_user_is_admin)
        self.users_card.setToolTip(
            "" if self.current_user_is_admin
            else "Only Admins can manage users."
        )
        self.groups_card.setToolTip(
            "" if self.current_user_is_admin
            else "Only Admins can manage groups."
        )
        self.content_layout.addWidget(self.users_card)
        self.content_layout.addWidget(self.groups_card)
        self.content_layout.addStretch()
        self._apply_responsive_layout()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _empty_card(self, message: str) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        label = QLabel(message)
        label.setObjectName("emptyLabel")
        layout.addWidget(label)
        return card

    @staticmethod
    def _card() -> QFrame:
        card = QFrame()
        card.setObjectName("managementCard")
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        return card

    def _section_heading(
        self,
        title: str,
        subtitle: str,
        icon_name: str,
    ) -> QWidget:
        widget = QWidget()
        widget.setObjectName("managementSectionHeading")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(
            awesome_icon(icon_name, color="#b8c2d0").pixmap(22, 22)
        )
        icon.setFixedSize(26, 26)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("managementSectionTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("managementSectionSubtitle")
        subtitle_label.setWordWrap(True)
        text.addWidget(title_label)
        text.addWidget(subtitle_label)
        layout.addLayout(text, 1)
        return widget

    def _overview_card(self, user: dict, groups: list[dict]) -> QFrame:
        card = self._card()
        self.overview_grid = QGridLayout(card)
        self.overview_grid.setContentsMargins(18, 16, 18, 16)
        self.overview_grid.setHorizontalSpacing(18)
        self.overview_grid.setVerticalSpacing(14)
        self.profile_panel = self._profile_panel(user)
        self.memberships_panel = self._memberships_panel(groups)
        self.overview_divider = QFrame()
        self.overview_divider.setObjectName("managementDivider")
        return card

    def _profile_panel(self, user: dict) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._section_heading(
            "User Profile",
            "This is the user account used for management permissions.",
            "fa6s.user",
        ))

        detail = QHBoxLayout()
        detail.setContentsMargins(4, 2, 4, 0)
        detail.setSpacing(8)
        avatar = QLabel()
        avatar.setFixedSize(60, 60)
        avatar.setPixmap(
            avatar_icon(user["name"], user["color"], 60).pixmap(60, 60)
        )
        detail.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(6)
        name_row = QHBoxLayout()
        name_row.setSpacing(7)
        name = ElidedLabel(user["name"])
        name.setObjectName("managementProfileName")
        self.profile_name_label = name
        name.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        name_row.addWidget(name)
        if user["is_admin"]:
            star = QLabel()
            star.setPixmap(
                awesome_icon("fa6s.star", color="#e0b84f").pixmap(14, 14)
            )
            star.setToolTip("Admin")
            name_row.addWidget(star)
            badge = QLabel("Admin")
            badge.setObjectName("adminBadge")
            name_row.addWidget(badge)
        name_row.addStretch()
        text.addLayout(name_row)
        subtitle = QLabel("Personal")
        subtitle.setObjectName("managementMuted")
        text.addWidget(subtitle)
        edit = QPushButton("Edit Profile")
        edit.setObjectName("secondaryActionButton")
        edit.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        set_button_icon(edit, "fa6s.pen", size=13)
        edit.clicked.connect(lambda: self.edit_user_requested.emit(user["id"]))
        text.addWidget(edit, alignment=Qt.AlignmentFlag.AlignLeft)
        detail.addLayout(text, 1)
        layout.addLayout(detail)
        layout.addStretch()
        return panel

    def _memberships_panel(self, groups: list[dict]) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._section_heading(
            "Groups You Belong To",
            "These groups include your data.",
            "fa6s.user-group",
        ))
        if not groups:
            empty = QLabel("You are not a member of any groups.")
            empty.setObjectName("emptyLabel")
            empty.setWordWrap(True)
            layout.addWidget(empty)
            layout.addStretch()
            return panel
        for group in groups:
            row = QFrame()
            row.setObjectName("membershipRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 8, 10, 8)
            row_layout.setSpacing(8)
            avatar = QLabel()
            avatar.setFixedSize(36, 36)
            avatar.setPixmap(avatar_icon(
                group["name"], group["color"], 36, profile_type="group"
            ).pixmap(36, 36))
            row_layout.addWidget(avatar)
            text = QVBoxLayout()
            text.setSpacing(1)
            name = ElidedLabel(group["name"])
            name.setObjectName("managementRowName")
            text.addWidget(name)
            subtitle = QLabel(
                f"Group • {group['member_count']} "
                f"member{'s' if group['member_count'] != 1 else ''}"
            )
            subtitle.setObjectName("managementSmallMuted")
            text.addWidget(subtitle)
            row_layout.addLayout(text, 1)
            leave = QPushButton("Leave Group")
            leave.setObjectName("compactDangerButton")
            set_button_icon(
                leave,
                "fa6s.arrow-right-from-bracket",
                color="#ff8f94",
                active_color="#ffb0b4",
                size=12,
            )
            leave.clicked.connect(
                lambda checked=False, group_id=group["id"], name=group["name"]:
                self._leave_group(group_id, name)
            )
            row_layout.addWidget(leave)
            layout.addWidget(row)
        layout.addStretch()
        return panel

    def _users_card(self, users: list[dict]) -> QFrame:
        card = self._card()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(12, 14, 12, 10)
        outer.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(6, 0, 6, 0)
        header.addWidget(self._section_heading(
            "All Users",
            "Manage user accounts and permissions.",
            "fa6s.users",
        ), 1)
        self.user_search = QLineEdit()
        self.user_search.setObjectName("managementSearch")
        self.user_search.setPlaceholderText("Search users…")
        self.user_search.setClearButtonEnabled(True)
        self.user_search.setMaximumWidth(300)
        self.user_search.setMinimumWidth(170)
        self.user_search.setFixedHeight(36)
        self.user_search.addAction(
            awesome_icon("fa6s.magnifying-glass", color=COLORS["text_dim"]),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.user_search.textChanged.connect(
            lambda value: self._filter_rows(self._user_rows, value)
        )
        header.addWidget(self.user_search)
        count = QLabel(f"{len(users)} user{'s' if len(users) != 1 else ''}")
        count.setObjectName("managementCount")
        header.addWidget(count)
        outer.addLayout(header)

        table = QFrame()
        table.setObjectName("managementTable")
        table_layout = QVBoxLayout(table)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        heading, widgets = self._user_table_header()
        self._user_group_widgets.append(widgets[0])
        self._user_created_widgets.append(widgets[1])
        table_layout.addWidget(heading)
        admin_count = sum(1 for user in users if user["is_admin"])
        for user in users:
            row = self._user_row(user, admin_count)
            table_layout.addWidget(row)
            self._user_rows.append(row)
        outer.addWidget(table)
        return card

    def _user_table_header(self) -> tuple[QFrame, tuple[QWidget, QWidget]]:
        row = QFrame()
        row.setObjectName("managementTableHeader")
        grid = self._user_grid(row)
        name = self._header_label("Name")
        role = self._header_label("Role")
        groups = self._header_label("Groups")
        created = self._header_label("Created")
        actions = self._header_label("Actions", Qt.AlignmentFlag.AlignCenter)
        for column, widget in enumerate((name, role, groups, created, actions)):
            grid.addWidget(widget, 0, column)
        return row, (groups, created)

    def _user_row(self, user: dict, admin_count: int) -> QFrame:
        row = QFrame()
        row.setObjectName("managementTableRow")
        row.setProperty(
            "searchText",
            " ".join((user["name"], *user.get("group_names", ()))).casefold(),
        )
        grid = self._user_grid(row)

        identity = QWidget()
        identity_layout = QHBoxLayout(identity)
        identity_layout.setContentsMargins(0, 0, 0, 0)
        identity_layout.setSpacing(8)
        avatar = QLabel()
        avatar.setFixedSize(32, 32)
        avatar.setPixmap(
            avatar_icon(user["name"], user["color"], 32).pixmap(32, 32)
        )
        identity_layout.addWidget(avatar)
        name = ElidedLabel(user["name"])
        name.setObjectName("managementRowName")
        name.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        identity_layout.addWidget(name)
        if user["is_admin"]:
            star = QLabel()
            star.setPixmap(
                awesome_icon("fa6s.star", color="#e0b84f").pixmap(12, 12)
            )
            star.setToolTip("Admin")
            identity_layout.addWidget(star)
        identity_layout.addStretch()
        grid.addWidget(identity, 0, 0)

        role = QLabel("Admin" if user["is_admin"] else "User")
        role.setObjectName("adminBadge" if user["is_admin"] else "userBadge")
        role.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        grid.addWidget(role, 0, 1, alignment=Qt.AlignmentFlag.AlignLeft)

        groups = ElidedLabel(", ".join(user.get("group_names", ())) or "—")
        groups.setObjectName("managementMuted")
        grid.addWidget(groups, 0, 2)
        self._user_group_widgets.append(groups)

        created = QLabel(_display_date(user.get("created_at")))
        created.setObjectName("managementMuted")
        grid.addWidget(created, 0, 3)
        self._user_created_widgets.append(created)

        actions = self._user_actions(user, admin_count)
        grid.addWidget(actions, 0, 4, alignment=Qt.AlignmentFlag.AlignRight)
        return row

    def _user_actions(self, user: dict, admin_count: int) -> QWidget:
        actions = QWidget()
        actions.setFixedWidth(self.USER_ACTION_WIDTH)
        layout = QHBoxLayout(actions)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        if user["id"] == self.current_user_id:
            placeholder = QLabel("—")
            placeholder.setObjectName("managementMuted")
            layout.addStretch()
            layout.addWidget(placeholder)
            return actions

        edit = QPushButton("Edit user")
        edit.setObjectName("tableIconButton")
        set_icon_only_button(
            edit,
            "fa6s.pen",
            tooltip=f"Edit {user['name']}",
            icon_size=13,
            button_size=32,
        )
        edit.clicked.connect(
            lambda checked=False, user_id=user["id"]:
            self.edit_user_requested.emit(user_id)
        )
        layout.addWidget(edit)

        role = QPushButton()
        role.setObjectName("tableIconButton")
        role_label = "Remove Admin" if user["is_admin"] else "Make Admin"
        set_icon_only_button(
            role,
            "fa6s.user-minus" if user["is_admin"] else "fa6s.user-shield",
            tooltip=f"{role_label}: {user['name']}",
            color="#d0aa50" if user["is_admin"] else "#87aee8",
            active_color="#f3ca62" if user["is_admin"] else "#a9c9f5",
            icon_size=14,
            button_size=32,
        )
        role.setEnabled(not (user["is_admin"] and admin_count <= 1))
        role.clicked.connect(
            lambda checked=False, item=user: self._change_role(item)
        )
        layout.addWidget(role)

        remove = QPushButton("Delete user")
        remove.setObjectName("dangerButton")
        set_delete_button_icon(remove, size=13)
        remove.setFixedSize(32, 32)
        remove.setToolTip(f"Delete {user['name']}")
        remove.clicked.connect(
            lambda checked=False, item=user: self._delete_user(item)
        )
        layout.addWidget(remove)
        return actions

    def _groups_card(self, groups: list[dict]) -> QFrame:
        card = self._card()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(12, 14, 12, 10)
        outer.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(6, 0, 6, 0)
        header.addWidget(self._section_heading(
            "Groups",
            "Manage groups and their members.",
            "fa6s.user-group",
        ), 1)
        self.group_search = QLineEdit()
        self.group_search.setObjectName("managementSearch")
        self.group_search.setPlaceholderText("Search groups…")
        self.group_search.setClearButtonEnabled(True)
        self.group_search.setMaximumWidth(300)
        self.group_search.setMinimumWidth(170)
        self.group_search.setFixedHeight(36)
        self.group_search.addAction(
            awesome_icon("fa6s.magnifying-glass", color=COLORS["text_dim"]),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.group_search.textChanged.connect(
            lambda value: self._filter_rows(self._group_rows, value)
        )
        header.addWidget(self.group_search)
        count = QLabel(f"{len(groups)} group{'s' if len(groups) != 1 else ''}")
        count.setObjectName("managementCount")
        header.addWidget(count)
        outer.addLayout(header)

        table = QFrame()
        table.setObjectName("managementTable")
        table_layout = QVBoxLayout(table)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        heading, created_header = self._group_table_header()
        self._group_created_widgets.append(created_header)
        table_layout.addWidget(heading)
        if not groups:
            empty = QLabel("No groups have been created.")
            empty.setObjectName("emptyLabel")
            empty.setContentsMargins(12, 18, 12, 18)
            table_layout.addWidget(empty)
        for group in groups:
            row = self._group_row(group)
            table_layout.addWidget(row)
            self._group_rows.append(row)
        outer.addWidget(table)
        return card

    def _group_table_header(self) -> tuple[QFrame, QWidget]:
        row = QFrame()
        row.setObjectName("managementTableHeader")
        grid = self._group_grid(row)
        name = self._header_label("Name")
        members = self._header_label("Members")
        created = self._header_label("Created")
        actions = self._header_label("Actions", Qt.AlignmentFlag.AlignCenter)
        for column, widget in enumerate((name, members, created, actions)):
            grid.addWidget(widget, 0, column)
        return row, created

    def _group_row(self, group: dict) -> QFrame:
        row = QFrame()
        row.setObjectName("managementTableRow")
        row.setProperty(
            "searchText",
            " ".join((group["name"], *group.get("member_names", ()))).casefold(),
        )
        grid = self._group_grid(row)
        identity = QWidget()
        identity_layout = QHBoxLayout(identity)
        identity_layout.setContentsMargins(0, 0, 0, 0)
        identity_layout.setSpacing(8)
        avatar = QLabel()
        avatar.setFixedSize(32, 32)
        avatar.setPixmap(avatar_icon(
            group["name"], group["color"], 32, profile_type="group"
        ).pixmap(32, 32))
        identity_layout.addWidget(avatar)
        name = ElidedLabel(group["name"])
        name.setObjectName("managementRowName")
        identity_layout.addWidget(name, 1)
        grid.addWidget(identity, 0, 0)

        members = ElidedLabel(", ".join(group.get("member_names", ())) or "No members")
        members.setObjectName("managementMuted")
        grid.addWidget(members, 0, 1)

        created = QLabel(_display_date(group.get("created_at")))
        created.setObjectName("managementMuted")
        grid.addWidget(created, 0, 2)
        self._group_created_widgets.append(created)

        actions = QWidget()
        actions.setFixedWidth(self.GROUP_ACTION_WIDTH)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(4)
        edit = QPushButton("Edit group")
        edit.setObjectName("tableIconButton")
        set_icon_only_button(
            edit,
            "fa6s.pen",
            tooltip=f"Edit {group['name']} and manage members",
            icon_size=13,
            button_size=32,
        )
        edit.clicked.connect(
            lambda checked=False, group_id=group["id"]:
            self.edit_group_requested.emit(group_id)
        )
        actions_layout.addWidget(edit)
        delete_button = QPushButton("Delete group")
        delete_button.setObjectName("dangerButton")
        set_delete_button_icon(delete_button, size=13)
        delete_button.setFixedSize(32, 32)
        delete_button.setToolTip(f"Delete {group['name']}")
        delete_button.clicked.connect(
            lambda checked=False, item=group: self._delete_group(item)
        )
        actions_layout.addWidget(delete_button)
        grid.addWidget(actions, 0, 3, alignment=Qt.AlignmentFlag.AlignRight)
        return row

    @staticmethod
    def _header_label(
        text: str,
        alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
    ) -> QLabel:
        label = QLabel(text)
        label.setObjectName("managementTableHeading")
        label.setAlignment(alignment | Qt.AlignmentFlag.AlignVCenter)
        return label

    def _user_grid(self, parent: QWidget) -> QGridLayout:
        grid = QGridLayout(parent)
        grid.setContentsMargins(12, 7, 12, 7)
        grid.setHorizontalSpacing(14)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 3)
        grid.setColumnStretch(3, 2)
        grid.setColumnMinimumWidth(1, 84)
        grid.setColumnMinimumWidth(3, 108)
        grid.setColumnMinimumWidth(4, self.USER_ACTION_WIDTH)
        self._user_grids.append(grid)
        return grid

    def _group_grid(self, parent: QWidget) -> QGridLayout:
        grid = QGridLayout(parent)
        grid.setContentsMargins(12, 7, 12, 7)
        grid.setHorizontalSpacing(14)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 4)
        grid.setColumnStretch(2, 2)
        grid.setColumnMinimumWidth(2, 108)
        grid.setColumnMinimumWidth(3, self.GROUP_ACTION_WIDTH)
        self._group_grids.append(grid)
        return grid

    @staticmethod
    def _filter_rows(rows: list[QWidget], value: str) -> None:
        query = value.strip().casefold()
        for row in rows:
            row.setVisible(not query or query in str(row.property("searchText")))

    def _apply_responsive_layout(self) -> None:
        if not hasattr(self, "overview_grid"):
            return
        # The viewport can still report its pre-show fallback size while the page
        # is being rebuilt. The page width is stable during shell resizes.
        viewport_width = max(0, self.width() - 64)
        stacked = viewport_width < self.COMPACT_WIDTH
        if self._top_is_stacked != stacked:
            for widget in (
                self.profile_panel,
                self.memberships_panel,
                self.overview_divider,
            ):
                self.overview_grid.removeWidget(widget)
            if stacked:
                self.overview_divider.setFrameShape(QFrame.Shape.HLine)
                self.overview_grid.addWidget(self.profile_panel, 0, 0)
                self.overview_grid.addWidget(self.overview_divider, 1, 0)
                self.overview_grid.addWidget(self.memberships_panel, 2, 0)
                self.overview_grid.setColumnStretch(0, 1)
                self.overview_grid.setColumnStretch(2, 0)
            else:
                self.overview_divider.setFrameShape(QFrame.Shape.VLine)
                self.overview_grid.addWidget(self.profile_panel, 0, 0)
                self.overview_grid.addWidget(self.overview_divider, 0, 1)
                self.overview_grid.addWidget(self.memberships_panel, 0, 2)
                self.overview_grid.setColumnStretch(0, 1)
                self.overview_grid.setColumnStretch(2, 1)
            self._top_is_stacked = stacked

        hide_secondary = viewport_width < self.COMPACT_WIDTH
        hide_groups = viewport_width < self.NARROW_WIDTH
        for widget in self._user_created_widgets:
            widget.setVisible(not hide_secondary)
        for widget in self._group_created_widgets:
            widget.setVisible(not hide_secondary)
        for widget in self._user_group_widgets:
            widget.setVisible(not hide_groups)
        for grid in self._user_grids:
            grid.setColumnStretch(0, 4 if hide_secondary else 3)
            grid.setColumnStretch(2, 0 if hide_groups else 3)
            grid.setColumnStretch(3, 0 if hide_secondary else 2)
        for grid in self._group_grids:
            grid.setColumnStretch(0, 4 if hide_secondary else 3)
            grid.setColumnStretch(1, 5 if hide_secondary else 4)
            grid.setColumnStretch(2, 0 if hide_secondary else 2)

    def _leave_group(self, group_id: int, name: str) -> None:
        answer = QMessageBox.question(
            self,
            "Leave group",
            f"Leave {name}? Your financial data will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            leave_group(
                self.current_user_id, group_id, session_factory=self.session_factory
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not leave group", str(exc))
            return
        self.profiles_changed.emit()
        self.reload()

    def _change_role(self, user: dict) -> None:
        make_admin = not user["is_admin"]
        action = "Make Admin" if make_admin else "Remove Admin"
        detail = (
            "Admins can manage users and groups."
            if make_admin else
            "This user will no longer be able to manage users and groups."
        )
        answer = QMessageBox.question(
            self,
            action,
            f"{action} for {user['name']}?\n\n{detail}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            set_admin(
                self.current_user_id,
                user["id"],
                make_admin,
                session_factory=self.session_factory,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Role not changed", str(exc))
            return
        self.profiles_changed.emit()
        self.reload()

    def _delete_user(self, user: dict) -> None:
        prompt = (
            f"Delete {user['name']}?\n\nThis permanently deletes their accounts, "
            "transactions, imports, investments, savings data, budgets, rules, "
            "custom categories where safe, memberships, and profile settings.\n\n"
            "Type DELETE to continue."
        )
        confirmation, accepted = QInputDialog.getText(self, "Delete user", prompt)
        if not accepted or confirmation != "DELETE":
            return
        try:
            delete_user(
                self.current_user_id,
                user["id"],
                session_factory=self.session_factory,
            )
        except Exception as exc:
            QMessageBox.warning(self, "User not deleted", str(exc))
            return
        self.profiles_changed.emit()
        self.reload()

    def _delete_group(self, group: dict) -> None:
        answer = QMessageBox.question(
            self,
            "Delete group",
            f"Delete {group['name']}?\n\nOnly the group and its membership links "
            "will be removed. Member-owned accounts, transactions, investments, "
            "budgets, and savings data will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_group(
                self.current_user_id,
                group["id"],
                session_factory=self.session_factory,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Group not deleted", str(exc))
            return
        self.profiles_changed.emit()
        self.reload()

    @staticmethod
    def _stylesheet() -> str:
        return f"""
            QScrollArea#userManagementScroll,
            QWidget#userManagementContent {{
                background: transparent;
                border: none;
            }}
            QFrame#managementCard {{
                background: #131920;
                border: 1px solid #2d3742;
                border-radius: 12px;
            }}
            QWidget#managementSectionHeading {{ background: transparent; }}
            QLabel#managementSectionTitle {{
                color: {COLORS['text']};
                font-size: 14px;
                font-weight: 700;
            }}
            QLabel#managementSectionSubtitle {{
                color: {COLORS['text_muted']};
                font-size: 11px;
            }}
            QLabel#managementProfileName {{
                color: {COLORS['text']};
                font-size: 17px;
                font-weight: 700;
            }}
            QLabel#managementRowName {{
                color: {COLORS['text']};
                font-size: 12px;
                font-weight: 600;
            }}
            QLabel#managementMuted {{
                color: {COLORS['text_muted']};
                font-size: 12px;
            }}
            QLabel#managementSmallMuted, QLabel#managementCount {{
                color: {COLORS['text_dim']};
                font-size: 10px;
            }}
            QLabel#adminBadge, QLabel#userBadge {{
                border-radius: 5px;
                padding: 3px 7px;
                font-size: 10px;
            }}
            QLabel#adminBadge {{
                color: #94c8ff;
                background: #132c4c;
                border: 1px solid #22528a;
            }}
            QLabel#userBadge {{
                color: #bac3cd;
                background: #222a33;
                border: 1px solid #35414d;
            }}
            QFrame#managementDivider {{
                color: #2b3540;
                background: #2b3540;
                border: none;
            }}
            QFrame#membershipRow {{
                background: #151c24;
                border: 1px solid #27333f;
                border-radius: 9px;
            }}
            QPushButton#compactDangerButton {{
                color: #ff8f94;
                background: #171d24;
                border: 1px solid #33404d;
                border-radius: 7px;
                min-height: 28px;
                padding: 3px 9px;
                font-size: 10px;
            }}
            QPushButton#compactDangerButton:hover {{
                color: #ffb1b5;
                background: #2c1b22;
                border-color: #65404a;
            }}
            QLineEdit#managementSearch {{
                background: #10161d;
                border: 1px solid #2e3a47;
                border-radius: 8px;
                padding: 0 10px;
                font-size: 11px;
            }}
            QFrame#managementTable {{
                background: #11171e;
                border: 1px solid #222e39;
                border-radius: 9px;
            }}
            QFrame#managementTableHeader {{
                background: #18202a;
                border: none;
                border-bottom: 1px solid #26323e;
            }}
            QLabel#managementTableHeading {{
                color: #b7c1cc;
                font-size: 10px;
                font-weight: 600;
            }}
            QFrame#managementTableRow {{
                background: transparent;
                border: none;
                border-bottom: 1px solid #242e38;
                min-height: 48px;
            }}
            QFrame#managementTableRow:hover {{ background: #161e27; }}
            QFrame#managementTableRow QPushButton#tableIconButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 7px;
            }}
            QFrame#managementTableRow QPushButton#tableIconButton:hover {{
                background: #232d38;
                border-color: #354351;
            }}
        """
