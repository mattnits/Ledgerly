from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import selectinload

from database.db import SessionLocal
from database.groups import update_group
from database.models import (
    Account,
    Category,
    CategoryRule,
    Group,
    GroupMembership,
    Import,
    InvestmentAccount,
    InvestmentSnapshot,
    MonthlyCategoryBudget,
    SavingsGoal,
    SavingsSnapshot,
    Transaction,
    User,
)


class AuthorizationError(PermissionError):
    pass


class LastAdminError(ValueError):
    pass


class GroupHasOwnedDataError(ValueError):
    pass


def _require_user(session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise ValueError("User no longer exists")
    return user


def _require_admin(session, actor_user_id: str) -> User:
    actor = _require_user(session, actor_user_id)
    if not actor.is_admin:
        raise AuthorizationError("Only Admins can perform this action.")
    return actor


def _admin_count(session) -> int:
    return int(session.scalar(select(func.count(User.id)).where(User.is_admin)) or 0)


def create_user(name: str, color: str, *, session_factory=SessionLocal) -> str:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Name is required")
    with session_factory.begin() as session:
        is_first_user = not bool(session.scalar(select(User.id).limit(1)))
        user = User(
            name=clean_name,
            color=color,
            profile_code_hash=None,
            is_admin=is_first_user,
        )
        session.add(user)
        session.flush()
        return user.id


def update_user(
    actor_user_id: str,
    user_id: str,
    name: str,
    color: str,
    *,
    session_factory=SessionLocal,
) -> None:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Name is required")
    with session_factory.begin() as session:
        actor = _require_user(session, actor_user_id)
        target = _require_user(session, user_id)
        if actor.id != target.id and not actor.is_admin:
            raise AuthorizationError("Only Admins can edit another user.")
        target.name = clean_name
        target.color = color


def set_admin(
    actor_user_id: str,
    user_id: str,
    is_admin: bool,
    *,
    session_factory=SessionLocal,
) -> None:
    with session_factory.begin() as session:
        _require_admin(session, actor_user_id)
        target = _require_user(session, user_id)
        if target.is_admin and not is_admin and _admin_count(session) <= 1:
            raise LastAdminError(
                "This user is the only Admin. Promote another user first."
            )
        target.is_admin = bool(is_admin)


def leave_group(
    user_id: str,
    group_id: int,
    *,
    session_factory=SessionLocal,
) -> None:
    with session_factory.begin() as session:
        _require_user(session, user_id)
        session.execute(delete(GroupMembership).where(
            GroupMembership.user_id == user_id,
            GroupMembership.group_id == group_id,
        ))


def update_group_as_admin(
    actor_user_id: str,
    group_id: int,
    name: str,
    color: str,
    member_ids,
    *,
    session_factory=SessionLocal,
) -> None:
    with session_factory() as session:
        _require_admin(session, actor_user_id)
    update_group(group_id, name, color, member_ids, session_factory=session_factory)


def delete_group(
    actor_user_id: str,
    group_id: int,
    *,
    session_factory=SessionLocal,
) -> None:
    """Delete an aggregation-only group without deleting financial records."""
    with session_factory.begin() as session:
        _require_admin(session, actor_user_id)
        group = session.get(Group, group_id)
        if group is None:
            raise ValueError("Group no longer exists")

        owned_models = (
            Account,
            InvestmentAccount,
            SavingsGoal,
            SavingsSnapshot,
            MonthlyCategoryBudget,
        )
        has_direct_data = any(
            session.scalar(
                select(model.id).where(model.group_id == group_id).limit(1)
            )
            is not None
            for model in owned_models
        )
        if has_direct_data:
            raise GroupHasOwnedDataError(
                "This group directly owns financial data and cannot be deleted "
                "without choosing where that data should go. No data was changed."
            )

        session.execute(delete(GroupMembership).where(
            GroupMembership.group_id == group_id
        ))
        session.delete(group)


def management_snapshot(current_user_id: str, *, session_factory=SessionLocal) -> dict:
    with session_factory() as session:
        current = _require_user(session, current_user_id)
        memberships = session.scalars(
            select(Group)
            .join(GroupMembership, GroupMembership.group_id == Group.id)
            .where(GroupMembership.user_id == current_user_id)
            .options(selectinload(Group.memberships))
            .order_by(Group.name)
        ).all()
        result = {
            "current_user": {
                "id": current.id, "name": current.name, "color": current.color,
                "is_admin": current.is_admin,
            },
            "memberships": [
                {"id": group.id, "name": group.name, "color": group.color,
                 "member_count": len(group.memberships)}
                for group in memberships
            ],
            "users": [],
            "groups": [],
        }
        users = session.scalars(
            select(User)
            .options(
                selectinload(User.group_memberships)
                .selectinload(GroupMembership.group)
            )
            .order_by(User.created_at, User.id)
        ).all()
        result["users"] = [
            {
                "id": user.id,
                "name": user.name,
                "color": user.color,
                "is_admin": user.is_admin,
                "created_at": user.created_at,
                "group_names": sorted(
                    membership.group.name
                    for membership in user.group_memberships
                ),
            }
            for user in users
        ]
        groups = session.scalars(
            select(Group)
            .options(selectinload(Group.memberships).selectinload(GroupMembership.user))
            .order_by(Group.created_at, Group.id)
        ).all()
        result["groups"] = [
            {
                "id": group.id,
                "name": group.name,
                "color": group.color,
                "member_ids": [item.user_id for item in group.memberships],
                "member_names": [item.user.name for item in group.memberships],
                "member_count": len(group.memberships),
                "created_at": group.created_at,
            }
            for group in groups
        ]
        return result


def delete_user(
    actor_user_id: str,
    user_id: str,
    *,
    allow_self: bool = False,
    session_factory=SessionLocal,
) -> None:
    """Atomically delete one user's owned data without touching group-owned data."""
    with session_factory.begin() as session:
        actor = _require_user(session, actor_user_id)
        target = _require_user(session, user_id)
        if actor.id == target.id:
            if not allow_self:
                raise AuthorizationError("Delete your own profile from Settings.")
        elif not actor.is_admin:
            raise AuthorizationError("Only Admins can delete another user.")
        if target.is_admin and _admin_count(session) <= 1:
            raise LastAdminError(
                "You are the only Admin. Promote another user to Admin before "
                "deleting this profile."
            )

        account_ids = select(Account.id).where(Account.user_id == user_id)
        investment_ids = select(InvestmentAccount.id).where(
            InvestmentAccount.user_id == user_id
        )
        session.execute(delete(CategoryRule).where(CategoryRule.user_id == user_id))
        session.execute(update(CategoryRule).where(
            CategoryRule.account_id.in_(account_ids)
        ).values(account_id=None))
        session.execute(delete(Transaction).where(Transaction.account_id.in_(account_ids)))
        session.execute(delete(Import).where(Import.account_id.in_(account_ids)))
        session.execute(delete(Account).where(Account.user_id == user_id))
        session.execute(delete(InvestmentSnapshot).where(
            InvestmentSnapshot.investment_account_id.in_(investment_ids)
        ))
        session.execute(delete(InvestmentAccount).where(
            InvestmentAccount.user_id == user_id
        ))
        session.execute(delete(SavingsSnapshot).where(SavingsSnapshot.user_id == user_id))
        session.execute(delete(SavingsGoal).where(SavingsGoal.user_id == user_id))
        session.execute(delete(MonthlyCategoryBudget).where(
            MonthlyCategoryBudget.user_id == user_id
        ))
        session.execute(delete(GroupMembership).where(GroupMembership.user_id == user_id))

        owned_categories = session.scalars(select(Category).where(
            Category.created_by_user_id == user_id,
            Category.is_system.is_(False),
        )).all()
        for category in owned_categories:
            referenced = any((
                session.scalar(select(Transaction.id).where(
                    Transaction.category_id == category.id
                ).limit(1)),
                session.scalar(select(CategoryRule.id).where(
                    CategoryRule.category_id == category.id
                ).limit(1)),
                session.scalar(select(MonthlyCategoryBudget.id).where(
                    MonthlyCategoryBudget.category_id == category.id
                ).limit(1)),
            ))
            if referenced:
                category.created_by_user_id = None
            else:
                session.delete(category)
        session.delete(target)
