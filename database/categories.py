from sqlalchemy import delete, select, update

from database.db import SessionLocal
from database.models import Category, CategoryRule, Transaction


def list_categories() -> list[tuple[int, str, str, bool]]:
    with SessionLocal() as session:
        categories = session.scalars(
            select(Category).order_by(Category.is_default.desc(), Category.name)
        ).all()
        return [(item.id, item.name, item.color, item.is_default) for item in categories]


def add_category(name: str, color: str) -> None:
    name = name.strip()
    if not name:
        raise ValueError("Enter a category name.")
    if len(name) > 100:
        raise ValueError("Category names must be at most 100 characters.")
    if len(color) != 7 or color[0] != "#" or any(
        digit not in "0123456789abcdefABCDEF" for digit in color[1:]
    ):
        raise ValueError("Choose a valid category color.")

    with SessionLocal.begin() as session:
        names = session.scalars(select(Category.name)).all()
        if any(existing.casefold() == name.casefold() for existing in names):
            raise ValueError("A category with that name already exists.")
        session.add(Category(name=name, color=color, is_default=False))


def delete_category(category_id: int) -> None:
    with SessionLocal.begin() as session:
        category = session.get(Category, category_id)
        if category is None:
            raise ValueError("Category no longer exists.")
        if category.is_default:
            raise ValueError("Default categories cannot be deleted.")
        session.execute(
            update(Transaction).where(Transaction.category_id == category_id)
            .values(category_id=None)
        )
        session.execute(
            update(Transaction).where(Transaction.previous_category_id == category_id)
            .values(previous_category_id=None)
        )
        session.execute(
            delete(CategoryRule).where(CategoryRule.category_id == category_id)
        )
        session.delete(category)
