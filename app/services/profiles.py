from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sqlalchemy import Select, or_, select

from app.models.models import Account, GroupMembership


class ProfileType(str, Enum):
    USER = "user"
    GROUP = "group"


@dataclass(frozen=True)
class ProfileContext:
    """Identifies the selected profile without overloading a user id."""

    profile_type: ProfileType
    profile_id: str | int

    @classmethod
    def user(cls, user_id: str) -> "ProfileContext":
        return cls(ProfileType.USER, user_id)

    @classmethod
    def group(cls, group_id: int) -> "ProfileContext":
        return cls(ProfileType.GROUP, group_id)

    @classmethod
    def from_key(cls, key: str) -> "ProfileContext":
        profile_type, separator, raw_id = key.partition(":")
        if not separator or not raw_id:
            raise ValueError("Invalid profile key")
        if profile_type == ProfileType.USER.value:
            return cls.user(raw_id)
        if profile_type == ProfileType.GROUP.value:
            return cls.group(int(raw_id))
        raise ValueError("Invalid profile type")

    @property
    def key(self) -> str:
        return f"{self.profile_type.value}:{self.profile_id}"

    @property
    def user_id(self) -> str | None:
        return str(self.profile_id) if self.profile_type is ProfileType.USER else None

    @property
    def group_id(self) -> int | None:
        return int(self.profile_id) if self.profile_type is ProfileType.GROUP else None


def validate_owner(user_id: str | None, group_id: int | None) -> None:
    if (user_id is None) == (group_id is None):
        raise ValueError("Provide exactly one owner: user_id or group_id")


def member_user_ids(group_id: int) -> Select:
    return select(GroupMembership.user_id).where(
        GroupMembership.group_id == group_id
    )


def visible_account_scope(user_id: str | None, group_id: int | None):
    """SQL expression for accounts visible to a user or aggregate group view."""

    validate_owner(user_id, group_id)
    if user_id is not None:
        return Account.user_id == user_id
    return or_(
        Account.group_id == group_id,
        Account.user_id.in_(member_user_ids(group_id)),
    )


def direct_owner_scope(model, user_id: str | None, group_id: int | None):
    """SQL expression for data owned by the selected profile itself."""

    validate_owner(user_id, group_id)
    return model.user_id == user_id if user_id is not None else model.group_id == group_id


def visible_owner_scope(model, user_id: str | None, group_id: int | None):
    """Scope owner-bearing records to a user or group plus all its members."""

    validate_owner(user_id, group_id)
    if user_id is not None:
        return model.user_id == user_id
    return or_(
        model.group_id == group_id,
        model.user_id.in_(member_user_ids(group_id)),
    )
