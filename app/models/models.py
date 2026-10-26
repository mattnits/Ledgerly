from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.utils.constants import ClassificationSource, MatchType, TransactionType


def _transaction_type_column(nullable: bool = False):
    return mapped_column(
        SqlEnum(
            TransactionType,
            name="transaction_type",
            native_enum=False,
            length=32,
            create_constraint=False,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=nullable,
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
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

    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
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

    savings_goals: Mapped[list["SavingsGoal"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    long_term_savings_goals: Mapped[list["LongTermSavingsGoal"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    category_budgets: Mapped[list["MonthlyCategoryBudget"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    investment_accounts: Mapped[list["InvestmentAccount"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    savings_snapshots: Mapped[list["SavingsSnapshot"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    category_rules: Mapped[list["CategoryRule"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
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

    color: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        default="#3397f5",
        server_default="#3397f5",
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

    savings_goals: Mapped[list["SavingsGoal"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    long_term_savings_goals: Mapped[list["LongTermSavingsGoal"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    category_budgets: Mapped[list["MonthlyCategoryBudget"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    investment_accounts: Mapped[list["InvestmentAccount"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    savings_snapshots: Mapped[list["SavingsSnapshot"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class GroupMembership(Base):
    __tablename__ = "group_memberships"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    user_id: Mapped[str] = mapped_column(
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
        Index("ix_group_memberships_group_id", "group_id"),
    )


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    # An account belongs to either a user OR a group.
    user_id: Mapped[str | None] = mapped_column(
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
        Index("ix_accounts_user_id", "user_id"),
        Index("ix_accounts_group_id", "group_id"),
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
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#64748b")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="category",
        foreign_keys="Transaction.category_id",
    )
    category_rules: Mapped[list["CategoryRule"]] = relationship(
        back_populates="category",
    )


class CategoryRule(Base):
    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=True,
    )
    description_key: Mapped[str] = mapped_column(String(512), nullable=False)
    description_example: Mapped[str] = mapped_column(String(255), nullable=False)
    match_type: Mapped[MatchType] = mapped_column(
        SqlEnum(
            MatchType,
            name="rule_match_type",
            native_enum=False,
            length=16,
            create_constraint=False,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=MatchType.EXACT,
    )
    transaction_type: Mapped[TransactionType | None] = _transaction_type_column(nullable=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped["User"] = relationship(back_populates="category_rules")
    account: Mapped["Account | None"] = relationship()
    category: Mapped["Category | None"] = relationship(back_populates="category_rules")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "description_key",
            "account_id",
            name="uq_category_rule_user_description_account",
        ),
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

    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
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
    transaction_type: Mapped[TransactionType | None] = _transaction_type_column(nullable=True)
    classification_source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ClassificationSource.DEFAULT.value,
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    import_id: Mapped[int | None] = mapped_column(
        ForeignKey("imports.id"),
        nullable=True,
    )

    source_transaction_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    dedupe_fingerprint: Mapped[str | None] = mapped_column(
        String(64),
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
        foreign_keys=[category_id],
    )

    import_record: Mapped["Import | None"] = relationship(
        back_populates="transactions",
    )

    __table_args__ = (
        Index(
            "ux_transactions_active_account_source_id",
            "account_id",
            "source_transaction_id",
            unique=True,
            sqlite_where=text(
                "source_transaction_id IS NOT NULL AND is_deleted = 0"
            ),
        ),
        Index(
            "ix_transactions_dedupe_fingerprint",
            "dedupe_fingerprint",
        ),
        Index(
            "ix_transactions_account_deleted_date",
            "account_id",
            "is_deleted",
            "transaction_date",
        ),
    )


class _OwnedMonthlyMixin:
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)


class SavingsGoal(_OwnedMonthlyMixin, Base):
    __tablename__ = "savings_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    user: Mapped["User | None"] = relationship(back_populates="savings_goals")
    group: Mapped["Group | None"] = relationship(back_populates="savings_goals")

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND group_id IS NULL) OR "
            "(user_id IS NULL AND group_id IS NOT NULL)",
            name="ck_savings_goal_single_owner",
        ),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_savings_goal_month"),
        UniqueConstraint("user_id", "year", "month", name="uq_user_savings_goal_month"),
        UniqueConstraint("group_id", "year", "month", name="uq_group_savings_goal_month"),
        Index(
            "ux_user_savings_goal_month_nonnull",
            "user_id", "year", "month",
            unique=True,
            sqlite_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "ux_group_savings_goal_month_nonnull",
            "group_id", "year", "month",
            unique=True,
            sqlite_where=text("group_id IS NOT NULL"),
        ),
    )


class MonthlyCategoryBudget(_OwnedMonthlyMixin, Base):
    __tablename__ = "monthly_category_budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    applies_to_future: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    category: Mapped["Category"] = relationship()
    user: Mapped["User | None"] = relationship(back_populates="category_budgets")
    group: Mapped["Group | None"] = relationship(back_populates="category_budgets")

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND group_id IS NULL) OR "
            "(user_id IS NULL AND group_id IS NOT NULL)",
            name="ck_category_budget_single_owner",
        ),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_category_budget_month"),
        UniqueConstraint(
            "user_id", "category_id", "year", "month",
            name="uq_user_category_budget_month",
        ),
        UniqueConstraint(
            "group_id", "category_id", "year", "month",
            name="uq_group_category_budget_month",
        ),
        Index(
            "ux_user_category_budget_month_nonnull",
            "user_id", "category_id", "year", "month",
            unique=True,
            sqlite_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "ux_group_category_budget_month_nonnull",
            "group_id", "category_id", "year", "month",
            unique=True,
            sqlite_where=text("group_id IS NOT NULL"),
        ),
    )


class LongTermSavingsGoal(Base):
    """A manually tracked goal, separate from the calculated monthly target."""

    __tablename__ = "long_term_savings_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    user: Mapped["User | None"] = relationship(back_populates="long_term_savings_goals")
    group: Mapped["Group | None"] = relationship(back_populates="long_term_savings_goals")

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND group_id IS NULL) OR "
            "(user_id IS NULL AND group_id IS NOT NULL)",
            name="ck_long_term_goal_single_owner",
        ),
        CheckConstraint("target_amount > 0", name="ck_long_term_goal_positive_target"),
        CheckConstraint("current_amount >= 0", name="ck_long_term_goal_nonnegative_current"),
    )


class InvestmentAccount(Base):
    __tablename__ = "investment_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True)
    institution: Mapped[str] = mapped_column(String(100), nullable=False)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_number_last7: Mapped[str | None] = mapped_column(String(7), nullable=True)
    account_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_work_related: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    employer_matching_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    employer_match_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 4), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User | None"] = relationship(back_populates="investment_accounts")
    group: Mapped["Group | None"] = relationship(back_populates="investment_accounts")
    snapshots: Mapped[list["InvestmentSnapshot"]] = relationship(
        back_populates="investment_account",
        cascade="all, delete-orphan",
        order_by="InvestmentSnapshot.snapshot_datetime",
    )
    work_rrsp_contributions: Mapped[list["WorkRRSPContribution"]] = relationship(
        back_populates="investment_account",
        cascade="all, delete-orphan",
        order_by="WorkRRSPContribution.contribution_date",
    )

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND group_id IS NULL) OR "
            "(user_id IS NULL AND group_id IS NOT NULL)",
            name="ck_investment_account_single_owner",
        ),
        CheckConstraint(
            "account_number_last7 IS NULL OR "
            "length(account_number_last7) BETWEEN 1 AND 7",
            name="ck_investment_account_last7",
        ),
        CheckConstraint(
            "employer_match_percent IS NULL OR employer_match_percent >= 0",
            name="ck_investment_account_match_percent",
        ),
        Index("ix_investment_accounts_user_id", "user_id"),
        Index("ix_investment_accounts_group_id", "group_id"),
    )


class InvestmentSnapshot(Base):
    __tablename__ = "investment_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    investment_account_id: Mapped[int] = mapped_column(
        ForeignKey("investment_accounts.id"), nullable=False
    )
    snapshot_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    contribution_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )

    investment_account: Mapped["InvestmentAccount"] = relationship(
        back_populates="snapshots"
    )

    __table_args__ = (
        UniqueConstraint(
            "investment_account_id",
            "snapshot_datetime",
            name="uq_investment_snapshot_account_datetime",
        ),
        CheckConstraint(
            "total_value >= 0", name="ck_investment_snapshot_nonnegative_value"
        ),
    )


class WorkRRSPContribution(Base):
    """A paystub-sourced Work RRSP contribution and its saved employer match."""

    __tablename__ = "work_rrsp_contributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    investment_account_id: Mapped[int] = mapped_column(
        ForeignKey("investment_accounts.id", ondelete="CASCADE"), nullable=False
    )
    contribution_date: Mapped[date] = mapped_column(Date, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    employee_contribution: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    employer_match: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_contribution: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    investment_account: Mapped["InvestmentAccount"] = relationship(
        back_populates="work_rrsp_contributions"
    )

    __table_args__ = (
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_work_rrsp_month"),
        CheckConstraint(
            "employee_contribution >= 0", name="ck_work_rrsp_employee_nonnegative"
        ),
        CheckConstraint(
            "employer_match >= 0", name="ck_work_rrsp_employer_nonnegative"
        ),
        CheckConstraint(
            "total_contribution >= 0", name="ck_work_rrsp_total_nonnegative"
        ),
        Index(
            "ix_work_rrsp_contributions_account_date",
            "investment_account_id",
            "contribution_date",
        ),
        Index("ix_work_rrsp_contributions_year_month", "year", "month"),
    )


class SavingsSnapshot(Base):
    __tablename__ = "savings_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_saved_this_month: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_savings_balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    user: Mapped["User | None"] = relationship(back_populates="savings_snapshots")
    group: Mapped["Group | None"] = relationship(back_populates="savings_snapshots")

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND group_id IS NULL) OR "
            "(user_id IS NULL AND group_id IS NOT NULL)",
            name="ck_savings_snapshot_single_owner",
        ),
        UniqueConstraint("user_id", "snapshot_date", name="uq_user_savings_snapshot"),
        UniqueConstraint("group_id", "snapshot_date", name="uq_group_savings_snapshot"),
    )
