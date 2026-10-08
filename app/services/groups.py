from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.core.db import SessionLocal
from app.models.models import Group, GroupMembership, User


def _normalized_member_ids(member_ids: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(member_id) for member_id in member_ids))


def _validate_group_values(session, name: str, member_ids: Iterable[str]):
    clean_name = name.strip()
    clean_ids = _normalized_member_ids(member_ids)
    if not clean_name:
        raise ValueError("Group name is required")
    if not clean_ids:
        raise ValueError("Select at least one member")
    existing = set(session.scalars(select(User.id).where(User.id.in_(clean_ids))))
    if existing != set(clean_ids):
        raise ValueError("One or more selected users no longer exist")
    return clean_name, clean_ids


def create_group(
    name: str,
    color: str,
    member_ids: Iterable[str],
    *,
    session_factory=SessionLocal,
) -> int:
    """Create a group and all memberships in one transaction."""

    with session_factory.begin() as session:
        clean_name, clean_ids = _validate_group_values(session, name, member_ids)
        group = Group(name=clean_name, color=color)
        session.add(group)
        session.flush()
        session.add_all(
            GroupMembership(group_id=group.id, user_id=user_id)
            for user_id in clean_ids
        )
        session.flush()
        return group.id


def update_group(
    group_id: int,
    name: str,
    color: str,
    member_ids: Iterable[str],
    *,
    session_factory=SessionLocal,
) -> None:
    """Replace membership links without touching users or their financial data."""

    with session_factory.begin() as session:
        group = session.get(Group, group_id)
        if group is None:
            raise ValueError("Group no longer exists")
        clean_name, clean_ids = _validate_group_values(session, name, member_ids)
        group.name = clean_name
        group.color = color
        existing = {
            membership.user_id: membership
            for membership in group.memberships
        }
        selected = set(clean_ids)
        for user_id, membership in existing.items():
            if user_id not in selected:
                session.delete(membership)
        session.add_all(
            GroupMembership(group_id=group.id, user_id=user_id)
            for user_id in clean_ids
            if user_id not in existing
        )


def get_group(group_id: int, *, session_factory=SessionLocal) -> dict | None:
    with session_factory() as session:
        group = session.scalar(
            select(Group)
            .options(selectinload(Group.memberships))
            .where(Group.id == group_id)
        )
        if group is None:
            return None
        return {
            "id": group.id,
            "name": group.name,
            "color": group.color,
            "member_ids": tuple(membership.user_id for membership in group.memberships),
        }


def remove_membership(
    group_id: int,
    user_id: str,
    *,
    session_factory=SessionLocal,
) -> None:
    with session_factory.begin() as session:
        session.execute(
            delete(GroupMembership).where(
                GroupMembership.group_id == group_id,
                GroupMembership.user_id == user_id,
            )
        )
