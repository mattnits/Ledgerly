from enum import StrEnum

ADD_STATMENT_LABEL = "Add Statement(s)"

DASHBOARD_LABEL = "Dashboard"
TRANSACTIONS_LABEL = "Transactions"
ACCOUNTS_LABEL = "Accounts"
CATEGORIES_LABEL = "Categories"
SETTINGS_LABEL = "Settings"

DASHBOARD_PAGE = "dashboard"
TRANSACTIONS_PAGE = "transactions"
ACCOUNTS_PAGE = "accounts"
CATEGORIES_PAGE = "categories"
SETTINGS_PAGE = "settings"

class SUPPORTED_PARSE_TYPES(StrEnum):
    TD_DEBIT = "TD Debit",
    TD_CREDIT = "TD Credit",
    AMEX = "Amex",


class TransactionType(StrEnum):
    EXPENSE = "EXPENSE"
    INCOME = "INCOME"
    E_TRANSFER = "E_TRANSFER"
    TRANSFER = "TRANSFER"
    CREDIT_CARD_PAYMENT = "CREDIT_CARD_PAYMENT"
    REFUND_REIMBURSEMENT = "REFUND_REIMBURSEMENT"
    SAVINGS = "SAVINGS"
    INVESTMENT = "INVESTMENT"


class MatchType(StrEnum):
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    EXACT = "exact"


class ClassificationSource(StrEnum):
    MANUAL = "manual"
    RULE = "rule"
    DEFAULT = "default"


TRANSACTION_TYPE_LABELS = {
    TransactionType.EXPENSE: "Expense",
    TransactionType.INCOME: "Income",
    TransactionType.E_TRANSFER: "E-Transfer",
    TransactionType.TRANSFER: "Transfer",
    TransactionType.CREDIT_CARD_PAYMENT: "Credit Card Payment",
    TransactionType.REFUND_REIMBURSEMENT: "Refund / Reimbursement",
    TransactionType.SAVINGS: "Savings",
    TransactionType.INVESTMENT: "Investment",
}

CATEGORY_OPTIONAL_TRANSACTION_TYPES = frozenset({
    TransactionType.E_TRANSFER,
    TransactionType.TRANSFER,
    TransactionType.CREDIT_CARD_PAYMENT,
    TransactionType.REFUND_REIMBURSEMENT,
    TransactionType.SAVINGS,
    TransactionType.INVESTMENT,
})

CATEGORY_FREE_TRANSACTION_TYPES = frozenset({
    TransactionType.E_TRANSFER,
    TransactionType.TRANSFER,
    TransactionType.CREDIT_CARD_PAYMENT,
    TransactionType.SAVINGS,
    TransactionType.INVESTMENT,
})

INCOME_CATEGORY_NAMES = frozenset({"Salary", "Other Income"})

DEFAULT_CATEGORY_COLORS = {
    "Food": "#f97316",
    "Groceries": "#22c55e",
    "Housing": "#8b5cf6",
    "Bills & Utilities": "#eab308",
    "Transportation": "#3b82f6",
    "Entertainment": "#ec4899",
    "Travel": "#0ea5e9",
    "Shopping": "#a855f7",
    "Subscriptions": "#6366f1",
    "Health & Fitness": "#14b8a6",
    "Gifts": "#f43f5e",
    "Other": "#64748b",
    "Salary": "#10b981",
    "Other Income": "#34d399",
}
DEFAULT_CATEGORIES = tuple(DEFAULT_CATEGORY_COLORS)
