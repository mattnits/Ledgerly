import re
import unicodedata

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from database.models import Account, Category, CategoryRule, Transaction
from utils.constants import DELETED_CATEGORY_NAME


def normalize_description(description: str) -> str:
    text = unicodedata.normalize("NFKC", description).casefold()
    text = re.sub(r"['’]", "", text)
    text = re.sub(r"[^\w]+", " ", text)
    return " ".join(text.split())


def category_rules_for_user(session: Session, user_id: str) -> dict[str, int]:
    return dict(session.execute(
        select(CategoryRule.description_key, CategoryRule.category_id)
        .where(CategoryRule.user_id == user_id)
    ).all())


def save_category_rule(
    session: Session,
    user_id: str,
    description: str,
    category_id: int | None,
) -> None:
    key = normalize_description(description)
    if not key:
        return

    rule = session.scalar(
        select(CategoryRule).where(
            CategoryRule.user_id == user_id,
            CategoryRule.description_key == key,
        )
    )
    if category_id is None:
        if rule is not None:
            session.delete(rule)
    elif rule is None:
        session.add(CategoryRule(
            user_id=user_id,
            description_key=key,
            description_example=description,
            category_id=category_id,
        ))
    else:
        rule.category_id = category_id
        rule.description_example = description


def categorize_matching_transactions(
    session: Session,
    user_id: str,
    description: str,
    category_id: int | None,
) -> None:
    key = normalize_description(description)
    if not key:
        return

    descriptions = session.scalars(
        select(Transaction.description)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == user_id)
        .distinct()
    )
    matches = [value for value in descriptions if normalize_description(value) == key]
    account_ids = select(Account.id).where(Account.user_id == user_id)
    deleted_category_id = session.scalar(
        select(Category.id).where(Category.name == DELETED_CATEGORY_NAME)
    )
    for start in range(0, len(matches), 500):
        statement = (
            update(Transaction)
            .where(
                Transaction.account_id.in_(account_ids),
                Transaction.description.in_(matches[start:start + 500]),
            )
            .values(category_id=category_id)
            .execution_options(synchronize_session=False)
        )
        if deleted_category_id is not None:
            statement = statement.where(or_(
                Transaction.category_id.is_(None),
                Transaction.category_id != deleted_category_id,
            ))
        session.execute(statement)
