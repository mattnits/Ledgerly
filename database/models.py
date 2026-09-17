from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Store a hash of the profile code, never the actual code.
    # NULL means this profile is not locked.
    profile_code_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    color: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )

    accounts: Mapped[list["Account"]] = relationship(
        back_populates="user",
    )

    group_memberships: Mapped[list["GroupMembership"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )

    memberships: Mapped[list["GroupMembership"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )

    accounts: Mapped[list["Account"]] = relationship(
        back_populates="group",
    )


class GroupMembership(Base):
    __tablename__ = "group_memberships"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id"),
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="group_memberships",
    )

    group: Mapped["Group"] = relationship(
        back_populates="memberships",
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "group_id",
            name="uq_group_membership",
        ),
    )


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    # An account belongs to either a user OR a group.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("groups.id"),
        nullable=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    institution: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    account_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    balance: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    balance_as_of: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    user: Mapped["User | None"] = relationship(
        back_populates="accounts",
    )

    group: Mapped["Group | None"] = relationship(
        back_populates="accounts",
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )

    imports: Mapped[list["Import"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            """
            (user_id IS NOT NULL AND group_id IS NULL)
            OR
            (user_id IS NULL AND group_id IS NOT NULL)
            """,
            name="ck_account_single_owner",
        ),
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="category",
    )


class CategoryRule(Base):
    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    description_key: Mapped[str] = mapped_column(String(512), nullable=False)
    description_example: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "description_key", name="uq_category_rule_user_description"),
    )


class Import(Base):
    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"),
        nullable=False,
    )

    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    imported_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )

    account: Mapped["Account"] = relationship(
        back_populates="imports",
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="import_record",
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"),
        nullable=False,
    )

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"),
        nullable=True,
    )

    import_id: Mapped[int | None] = mapped_column(
        ForeignKey("imports.id"),
        nullable=True,
    )

    transaction_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    imported_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
    )

    account: Mapped["Account"] = relationship(
        back_populates="transactions",
    )

    category: Mapped["Category | None"] = relationship(
        back_populates="transactions",
    )

    import_record: Mapped["Import | None"] = relationship(
        back_populates="transactions",
    )
