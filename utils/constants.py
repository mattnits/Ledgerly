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
