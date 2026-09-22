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

DEFAULT_CATEGORY_COLORS = {
    "Transport": "#3b82f6",
    "Food": "#f97316",
    "Groceries": "#22c55e",
    "Shopping": "#a855f7",
    "Entertainment": "#ec4899",
    "Subscriptions": "#6366f1",
    "Income": "#10b981",
    "Health & Fitness": "#14b8a6",
    "Bills & Utilities": "#eab308",
    "E-Transfer": "#06b6d4",
    "Investing": "#0a8b19",
    "Exclude": "#64748b",
    "Deleted": "#6b7280",
}
DEFAULT_CATEGORIES = tuple(DEFAULT_CATEGORY_COLORS)
DELETED_CATEGORY_NAME = "Deleted"
DASHBOARD_HIDDEN_CATEGORY_NAMES = ("deleted", "exclude", "excluded")
