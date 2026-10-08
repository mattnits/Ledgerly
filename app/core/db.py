from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.paths import app_data_dir
from app.utils.constants import DEFAULT_CATEGORY_COLORS


DB_PATH = app_data_dir() / "finance.db"


class Base(DeclarativeBase):
    pass


engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=True,
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def init_db(db_engine=engine):
    # Import models so SQLAlchemy registers them with Base.metadata.
    from app.models import models

    Base.metadata.create_all(bind=db_engine)


def ensure_categories(db_engine=engine) -> None:
    from app.models.models import Category

    Category.__table__.create(bind=db_engine, checkfirst=True)
    with Session(db_engine) as session, session.begin():
        existing = {
            category.name: category
            for category in session.scalars(
                select(Category).where(Category.name.in_(DEFAULT_CATEGORY_COLORS))
            )
        }
        for name, color in DEFAULT_CATEGORY_COLORS.items():
            if name in existing:
                existing[name].color = color
                existing[name].is_default = True
                existing[name].is_system = True
                existing[name].created_by_user_id = None
            else:
                session.add(Category(
                    name=name, color=color, is_default=True, is_system=True,
                    created_by_user_id=None,
                ))


def user_exists() -> bool:
    from app.models.models import User

    with SessionLocal() as session:
        return session.scalar(
            select(User.id).limit(1)
        ) is not None


def get_users() -> list[dict[str, str]]:
    from app.models.models import User

    with SessionLocal() as session:
        users = session.scalars(
            select(User).order_by(User.created_at, User.id)
        ).all()

        return [
            {
                "id": user.id,
                "name": user.name,
                "color": user.color,
                "is_admin": user.is_admin,
            }
            for user in users
        ]


def get_profiles(
    session_factory=SessionLocal,
    current_user_id: str | None = None,
) -> list[dict]:
    """Return switcher-ready user and group profiles with typed keys."""
    from sqlalchemy import func
    from app.models.models import Group, GroupMembership, User

    with session_factory() as session:
        users = session.scalars(select(User).order_by(User.created_at, User.id)).all()
        group_query = (
            select(Group, func.count(GroupMembership.id))
            .outerjoin(GroupMembership)
            .group_by(Group.id)
            .order_by(Group.created_at, Group.id)
        )
        if current_user_id is not None:
            current = session.get(User, current_user_id)
            if current is not None and not current.is_admin:
                group_query = group_query.where(Group.id.in_(
                    select(GroupMembership.group_id).where(
                        GroupMembership.user_id == current_user_id
                    )
                ))
        groups = session.execute(group_query).all()
        return [
            {
                "key": f"user:{user.id}",
                "type": "user",
                "id": user.id,
                "name": user.name,
                "color": user.color,
                "subtitle": "Personal",
                "is_admin": user.is_admin,
            }
            for user in users
        ] + [
            {
                "key": f"group:{group.id}",
                "type": "group",
                "id": group.id,
                "name": group.name,
                "color": group.color,
                "member_count": member_count,
                "subtitle": f"Group • {member_count} member{'s' if member_count != 1 else ''}",
            }
            for group, member_count in groups
        ]
