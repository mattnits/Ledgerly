from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import calendar
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select

from database.db import SessionLocal
from database.finance_services import (
    BudgetProgress,
    MonthlyFinancialSummary,
    combine_financial_summaries,
    summarize_transaction_rows,
)
from database.investments import (
    get_monthly_contribution_summary,
    get_total_contribution_summary,
)
from database.models import (
    Account,
    Category,
    GroupMembership,
    InvestmentAccount,
    InvestmentSnapshot,
    MonthlyCategoryBudget,
    SavingsGoal,
    SavingsSnapshot,
    Transaction,
    User,
)
from database.profiles import (
    direct_owner_scope,
    validate_owner,
    visible_account_scope,
    visible_owner_scope,
)
from database.transactions import get_transaction_months
from utils.constants import TransactionType


INCOME_ACCOUNT_COLORS = (
    "#63dba0", "#35bdd0", "#9cc85b", "#5f7cff", "#4fd1a5", "#8ccf78",
)
SPENDING_ACCOUNT_COLORS = (
    "#f16f88", "#e05b68", "#f2a84b", "#cf78dc",
    "#ef7aa8", "#bd6a80", "#a66bff", "#e8895c",
)
NET_E_TRANSFER_COLOR = "#a66bff"


@dataclass(frozen=True)
class ChartSeries:
    name: str
    color: str
    values: tuple[Decimal, ...]


@dataclass(frozen=True)
class CategorySpending:
    name: str
    color: str
    amount: Decimal


@dataclass(frozen=True)
class AccountSpending:
    name: str
    amount: Decimal


@dataclass(frozen=True)
class PersonBreakdown:
    name: str
    income: Decimal
    spending: Decimal


@dataclass(frozen=True)
class RecentTransaction:
    description: str
    account_name: str
    transaction_date: date
    amount: Decimal
    category_color: str


@dataclass(frozen=True)
class DashboardData:
    period_label: str
    month_labels: tuple[str, ...]
    regular_income: Decimal
    other_income: Decimal
    e_transfer_received: Decimal
    e_transfer_sent: Decimal
    e_transfer_net: Decimal
    e_transfer_income_adjustment: Decimal
    gross_expense_spending: Decimal
    reimbursements: Decimal
    e_transfer_spending_adjustment: Decimal
    total_income: Decimal
    total_spending: Decimal
    account_spending: tuple[AccountSpending, ...]
    person_breakdown: tuple[PersonBreakdown, ...]
    manual_investing_total: Decimal
    investing_total: Decimal
    savings_goal: Decimal | None
    cash_savings_actual: Decimal
    work_rrsp_employee: Decimal
    employer_rrsp_match: Decimal
    savings_actual: Decimal
    savings_balance: Decimal | None
    budget_progress: tuple[BudgetProgress, ...]
    portfolio_value: Decimal
    portfolio_baseline_value: Decimal | None
    investment_month_labels: tuple[str, ...]
    investment_value_series: tuple[Decimal, ...]
    previous_income: Decimal | None
    previous_spending: Decimal | None
    income_series: tuple[ChartSeries, ...]
    spending_series: tuple[ChartSeries, ...]
    cash_flow_income: tuple[Decimal, ...]
    cash_flow_spending: tuple[Decimal, ...]
    category_spending: tuple[CategorySpending, ...]
    recent_transactions: tuple[RecentTransaction, ...]

    @property
    def additional_income(self) -> Decimal:
        return self.other_income

    @property
    def income_total(self) -> Decimal:
        return self.total_income

    @property
    def gross_spending(self) -> Decimal:
        return self.gross_expense_spending

    @property
    def spending_total(self) -> Decimal:
        return self.total_spending

    @property
    def previous_portfolio_value(self) -> Decimal | None:
        """Backward-compatible alias for the portfolio comparison baseline."""
        return self.portfolio_baseline_value


@dataclass(frozen=True)
class _TransactionData:
    transaction_date: date
    description: str
    amount: Decimal
    transaction_type: TransactionType
    account_id: int
    account_name: str
    account_user_id: str | None
    category_id: int | None
    category_name: str | None
    category_color: str | None


@dataclass(frozen=True)
class _InvestmentData:
    account_id: int
    snapshot_datetime: datetime
    account_name: str
    institution: str
    contribution_amount: Decimal | None
    total_value: Decimal


def _month_before(month: tuple[int, int]) -> tuple[int, int]:
    year, month_number = month
    return year - (month_number == 1), (month_number - 2) % 12 + 1


def _month_sequence(
    first: tuple[int, int],
    last: tuple[int, int],
) -> list[tuple[int, int]]:
    result = []
    year, month = first
    while (year, month) <= last:
        result.append((year, month))
        year, month = year + (month == 12), month % 12 + 1
    return result


def _income_source(item: _TransactionData) -> str | None:
    if item.transaction_type != TransactionType.INCOME:
        return None
    name = (item.category_name or "").strip().casefold()
    if name == "salary":
        return "salary"
    if name == "other income":
        return "other"
    return None


def _period_totals(
    transactions: list[_TransactionData],
    month: tuple[int, int],
) -> tuple[Decimal, Decimal]:
    selected = [
        item for item in transactions
        if (item.transaction_date.year, item.transaction_date.month) == month
    ]
    summary = _summarize(selected)
    return summary.total_income, summary.total_spending


def _summarize(transactions: list[_TransactionData]) -> MonthlyFinancialSummary:
    return summarize_transaction_rows(
        (item.amount, item.transaction_type, item.category_name)
        for item in transactions
    )


def _summarize_by_month(
    transactions: list[_TransactionData],
) -> MonthlyFinancialSummary:
    grouped: defaultdict[tuple[int, int], list[_TransactionData]] = defaultdict(list)
    for item in transactions:
        grouped[(item.transaction_date.year, item.transaction_date.month)].append(item)
    return combine_financial_summaries(_summarize(items) for items in grouped.values())


def get_dashboard_months(
    user_id: str | None,
    session_factory=SessionLocal,
    *,
    group_id: int | None = None,
) -> set[tuple[int, int]]:
    """Include months that have transactions or explicit goal/budget changes."""
    months = get_transaction_months(
        user_id,
        session_factory,
        group_id=group_id,
    )
    if user_id is None and group_id is None:
        return months
    validate_owner(user_id, group_id)
    with session_factory() as session:
        goal_months = session.execute(
            select(SavingsGoal.year, SavingsGoal.month).where(
                direct_owner_scope(SavingsGoal, user_id, group_id)
            )
        ).all()
        budget_months = session.execute(
            select(MonthlyCategoryBudget.year, MonthlyCategoryBudget.month).where(
                direct_owner_scope(MonthlyCategoryBudget, user_id, group_id)
            )
        ).all()
    configured_months = set(goal_months) | set(budget_months)
    months.update(configured_months)
    if configured_months:
        today = date.today()
        months.add((today.year, today.month))
    return months


def get_dashboard_data(
    user_id: str | None,
    period: str,
    selected_month: tuple[int, int],
    session_factory=SessionLocal,
    *,
    group_id: int | None = None,
) -> DashboardData:
    if period not in ("monthly", "all"):
        raise ValueError(f"Unsupported dashboard period: {period}")

    rows = []
    account_rows: list[tuple[int, str]] = []
    member_rows: list[tuple[str, str]] = []
    investment_rows: list[_InvestmentData] = []
    savings_goal_rows: list[tuple[int, int, Decimal]] = []
    savings_rows: list[
        tuple[date, Decimal, Decimal | None, str | None, int | None]
    ] = []
    budget_rows: list[tuple[int, str, int, int, Decimal]] = []
    if user_id is not None or group_id is not None:
        validate_owner(user_id, group_id)
        with session_factory() as session:
            account_rows = list(session.execute(
                select(Account.id, Account.name)
                .where(visible_account_scope(user_id, group_id))
                .order_by(Account.id)
            ).all())
            if group_id is not None:
                member_rows = list(session.execute(
                    select(User.id, User.name)
                    .join(GroupMembership, GroupMembership.user_id == User.id)
                    .where(GroupMembership.group_id == group_id)
                    .order_by(User.name, User.id)
                ).all())
            rows = session.execute(
                select(
                    Transaction.transaction_date,
                    Transaction.description,
                    Transaction.amount,
                    Transaction.transaction_type,
                    Account.id,
                    Account.name,
                    Account.user_id,
                    Category.id,
                    Category.name,
                    Category.color,
                )
                .join(Account, Transaction.account_id == Account.id)
                .outerjoin(Category, Transaction.category_id == Category.id)
                .where(
                    visible_account_scope(user_id, group_id),
                    Transaction.is_deleted.is_(False),
                )
                .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
            ).all()
            investment_rows = [
                _InvestmentData(*row)
                for row in session.execute(
                    select(
                        InvestmentAccount.id,
                        InvestmentSnapshot.snapshot_datetime,
                        InvestmentAccount.account_name,
                        InvestmentAccount.institution,
                        InvestmentSnapshot.contribution_amount,
                        InvestmentSnapshot.total_value,
                    )
                    .join(InvestmentAccount)
                    .where(
                        visible_owner_scope(InvestmentAccount, user_id, group_id),
                        InvestmentAccount.is_active.is_(True),
                    )
                ).all()
            ]
            savings_goal_rows = list(session.execute(
                select(
                    SavingsGoal.year,
                    SavingsGoal.month,
                    SavingsGoal.target_amount,
                ).where(direct_owner_scope(SavingsGoal, user_id, group_id))
            ).all())
            savings_rows = list(session.execute(
                select(
                    SavingsSnapshot.snapshot_date,
                    SavingsSnapshot.amount_saved_this_month,
                    SavingsSnapshot.total_savings_balance,
                    SavingsSnapshot.user_id,
                    SavingsSnapshot.group_id,
                )
                .where(visible_owner_scope(SavingsSnapshot, user_id, group_id))
                .order_by(SavingsSnapshot.snapshot_date)
            ).all())
            budget_rows = list(session.execute(
                select(
                    MonthlyCategoryBudget.category_id,
                    Category.name,
                    MonthlyCategoryBudget.year,
                    MonthlyCategoryBudget.month,
                    MonthlyCategoryBudget.target_amount,
                )
                .join(Category, MonthlyCategoryBudget.category_id == Category.id)
                .where(direct_owner_scope(MonthlyCategoryBudget, user_id, group_id))
                .order_by(Category.name)
            ).all())

    transactions = [_TransactionData(*row) for row in rows]
    today = date.today()

    if period == "monthly":
        timeline = _month_sequence((selected_month[0], 1), selected_month)
        selected = [
            item for item in transactions
            if (item.transaction_date.year, item.transaction_date.month) == selected_month
        ]
        previous_income, previous_spending = _period_totals(
            transactions, _month_before(selected_month)
        )
        period_label = date(*selected_month, 1).strftime("%B %Y")
    else:
        transaction_months = [
            (item.transaction_date.year, item.transaction_date.month)
            for item in transactions
        ]
        current_month = (today.year, today.month)
        timeline = _month_sequence(
            min(transaction_months, default=current_month),
            max(transaction_months, default=current_month),
        )
        selected = transactions
        previous_income = previous_spending = None
        period_label = "All time"

    one_year = len({year for year, _ in timeline}) == 1
    month_labels = tuple(
        date(year, month, 1).strftime("%b" if one_year else "%b %y")
        for year, month in timeline
    )
    timeline_index = {month: index for index, month in enumerate(timeline)}

    income_accounts: dict[int, tuple[str, list[Decimal]]] = {}
    spending_accounts: dict[int, tuple[str, list[Decimal]]] = {}
    cash_flow_income = [Decimal() for _ in timeline]
    cash_flow_spending = [Decimal() for _ in timeline]
    e_transfer_by_month: defaultdict[tuple[int, int], Decimal] = defaultdict(Decimal)

    for item in transactions:
        index = timeline_index.get((item.transaction_date.year, item.transaction_date.month))
        if index is None:
            continue
        if item.transaction_type == TransactionType.E_TRANSFER:
            e_transfer_by_month[
                (item.transaction_date.year, item.transaction_date.month)
            ] += item.amount
        elif _income_source(item) is not None:
            _, values = income_accounts.setdefault(
                item.account_id,
                (item.account_name, [Decimal() for _ in timeline]),
            )
            values[index] += item.amount
            cash_flow_income[index] += item.amount
        elif item.transaction_type in (
            TransactionType.EXPENSE,
            TransactionType.REFUND_REIMBURSEMENT,
        ):
            _, values = spending_accounts.setdefault(
                item.account_id,
                (item.account_name, [Decimal() for _ in timeline]),
            )
            amount = (
                abs(item.amount)
                if item.transaction_type == TransactionType.EXPENSE
                else -item.amount
            )
            values[index] += amount
            cash_flow_spending[index] += amount

    e_transfer_income_values = [Decimal() for _ in timeline]
    e_transfer_spending_values = [Decimal() for _ in timeline]
    for month, net in e_transfer_by_month.items():
        index = timeline_index[month]
        if net > 0:
            e_transfer_income_values[index] = net
            cash_flow_income[index] += net
        elif net < 0:
            e_transfer_spending_values[index] = -net
            cash_flow_spending[index] += -net
    if any(e_transfer_income_values):
        income_accounts[-1] = ("Net E-Transfers", e_transfer_income_values)
    if any(e_transfer_spending_values):
        spending_accounts[-1] = ("Net E-Transfers", e_transfer_spending_values)

    def make_series(
        grouped: dict[int, tuple[str, list[Decimal]]],
        colors: tuple[str, ...],
    ) -> tuple[ChartSeries, ...]:
        return tuple(
            ChartSeries(name, colors[index % len(colors)], tuple(values))
            for index, (_, (name, values)) in enumerate(
                sorted(grouped.items(), key=lambda value: (value[1][0].casefold(), value[0]))
            )
            if any(values)
        )

    summary = (
        _summarize(selected)
        if period == "monthly"
        else _summarize_by_month(selected)
    )

    transactions_by_user: defaultdict[
        str, list[_TransactionData]
    ] = defaultdict(list)
    for item in selected:
        if item.account_user_id is not None:
            transactions_by_user[item.account_user_id].append(item)
    person_breakdown_items = []
    for member_user_id, name in member_rows:
        member_transactions = transactions_by_user[member_user_id]
        member_summary = (
            _summarize(member_transactions)
            if period == "monthly"
            else _summarize_by_month(member_transactions)
        )
        person_breakdown_items.append(PersonBreakdown(
            name,
            member_summary.total_income,
            member_summary.total_spending,
        ))
    person_breakdown = tuple(person_breakdown_items)

    gross_spending_by_account: defaultdict[int, Decimal] = defaultdict(Decimal)
    for item in selected:
        if item.transaction_type == TransactionType.EXPENSE:
            gross_spending_by_account[item.account_id] += abs(item.amount)
    account_spending = tuple(
        AccountSpending(
            account_name,
            gross_spending_by_account.get(account_id, Decimal()),
        )
        for account_id, account_name in account_rows
    )

    category_totals: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    budget_spending_by_id: defaultdict[int, Decimal] = defaultdict(Decimal)
    for item in selected:
        if item.category_name is None:
            continue
        key = (item.category_name, item.category_color or "#718096")
        if item.transaction_type == TransactionType.EXPENSE:
            category_totals[key] += abs(item.amount)
            if item.category_id is not None:
                budget_spending_by_id[item.category_id] += abs(item.amount)
        elif item.transaction_type == TransactionType.REFUND_REIMBURSEMENT:
            category_totals[key] -= item.amount

    if summary.e_transfer_spending_adjustment > 0:
        category_totals[
            ("Net negative e-transfers", NET_E_TRANSFER_COLOR)
        ] += summary.e_transfer_spending_adjustment

    category_spending = tuple(
        CategorySpending(name, color, amount)
        for (name, color), amount in sorted(
            category_totals.items(),
            key=lambda value: (-value[1], value[0][0].casefold()),
        )
        if amount > 0
    )

    budget_history: defaultdict[
        int, list[tuple[tuple[int, int], str, Decimal]]
    ] = defaultdict(list)
    for category_id, name, budget_year, budget_month, target in budget_rows:
        budget_history[category_id].append(
            ((budget_year, budget_month), name, target)
        )
    for history in budget_history.values():
        history.sort(key=lambda item: item[0])

    def effective_budget_targets(month_key: tuple[int, int]) -> dict[int, tuple[str, Decimal]]:
        effective: dict[int, tuple[str, Decimal]] = {}
        for category_id, history in budget_history.items():
            latest = next(
                (item for item in reversed(history) if item[0] <= month_key),
                None,
            )
            if latest is not None and latest[2] > 0:
                effective[category_id] = (latest[1], latest[2])
        return effective

    if period == "monthly":
        budget_targets = effective_budget_targets(selected_month)
    else:
        budget_targets: dict[int, tuple[str, Decimal]] = {}
        for month_key in timeline:
            for category_id, (name, target) in effective_budget_targets(month_key).items():
                previous_name, previous_target = budget_targets.get(
                    category_id, (name, Decimal())
                )
                budget_targets[category_id] = (
                    previous_name,
                    previous_target + target,
                )
    budget_progress = tuple(
        BudgetProgress(
            category_id,
            name,
            budget_spending_by_id.get(category_id, Decimal()),
            target,
        )
        for category_id, (name, target) in sorted(
            budget_targets.items(), key=lambda item: item[1][0].casefold()
        )
    )

    goal_history = sorted(
        (((row[0], row[1]), row[2]) for row in savings_goal_rows),
        key=lambda item: item[0],
    )

    def effective_savings_goal(month_key: tuple[int, int]) -> Decimal | None:
        latest = next(
            (target for effective_month, target in reversed(goal_history)
             if effective_month <= month_key),
            None,
        )
        return latest

    if period == "monthly":
        savings_goal = effective_savings_goal(selected_month)
    else:
        effective_goals = [
            effective_savings_goal(month_key) for month_key in timeline
        ]
        savings_goal = (
            sum((target for target in effective_goals if target is not None), Decimal())
            if any(target is not None for target in effective_goals)
            else None
        )
    selected_savings_rows = [
        row for row in savings_rows
        if period == "all" or (row[0].year, row[0].month) == selected_month
    ]
    cash_savings_actual = sum(
        (row[1] for row in selected_savings_rows), Decimal()
    )
    balance_rows = [row for row in selected_savings_rows if row[2] is not None]
    if group_id is None:
        savings_balance = balance_rows[-1][2] if balance_rows else None
    else:
        latest_by_owner = {}
        for row in balance_rows:
            owner = (row[3], row[4])
            previous = latest_by_owner.get(owner)
            if previous is None or row[0] >= previous[0]:
                latest_by_owner[owner] = (row[0], row[2])
        savings_balance = (
            sum((value for _, value in latest_by_owner.values()), Decimal())
            if latest_by_owner
            else None
        )

    cutoff_date = (
        date(
            selected_month[0],
            selected_month[1],
            calendar.monthrange(*selected_month)[1],
        )
        if period == "monthly"
        else today
    )
    eligible_investments = [
        item
        for item in investment_rows
        if item.snapshot_datetime.date() <= cutoff_date
    ]
    selected_investments = [
        item
        for item in eligible_investments
        if period == "all"
        or (
            item.snapshot_datetime.year,
            item.snapshot_datetime.month,
        ) == selected_month
    ]
    manual_investing_total = sum(
        (item.contribution_amount or Decimal() for item in selected_investments),
        Decimal(),
    )
    if user_id is None and group_id is None:
        work_rrsp_employee = employer_rrsp_match = Decimal()
    else:
        contribution_summary = (
            get_monthly_contribution_summary(
                *selected_month,
                user_id=user_id,
                group_id=group_id,
                session_factory=session_factory,
            )
            if period == "monthly"
            else get_total_contribution_summary(
                user_id=user_id,
                group_id=group_id,
                session_factory=session_factory,
            )
        )
        work_rrsp_employee = contribution_summary.work_rrsp_employee
        employer_rrsp_match = contribution_summary.work_rrsp_employer
    # Keep Dashboard goal progress identical to the Goals page formula.
    savings_actual = (
        summary.total_income
        - summary.total_spending
        + work_rrsp_employee
        + employer_rrsp_match
    )
    investing_total = (
        manual_investing_total + work_rrsp_employee + employer_rrsp_match
    )
    snapshot_months = sorted({
        (item.snapshot_datetime.year, item.snapshot_datetime.month)
        for item in eligible_investments
    })

    def portfolio_as_of(cutoff: date) -> Decimal:
        latest_by_account: dict[int, tuple[datetime, Decimal]] = {}
        for item in investment_rows:
            if item.snapshot_datetime.date() > cutoff:
                continue
            previous = latest_by_account.get(item.account_id)
            if previous is None or item.snapshot_datetime > previous[0]:
                latest_by_account[item.account_id] = (
                    item.snapshot_datetime,
                    item.total_value,
                )
        return sum((value for _, value in latest_by_account.values()), Decimal())

    portfolio_value = portfolio_as_of(cutoff_date)
    first_portfolio_date = min(
        (item.snapshot_datetime.date() for item in eligible_investments),
        default=None,
    )
    portfolio_baseline_value = (
        portfolio_as_of(first_portfolio_date)
        if first_portfolio_date is not None
        else None
    )

    visible_investment_months = [
        month for month in snapshot_months
        if period == "all" or month <= selected_month
    ][-12:]
    investment_month_labels = tuple(
        date(year, month, 1).strftime(
            "%b"
            if len({y for y, _ in visible_investment_months}) == 1
            else "%b %y"
        )
        for year, month in visible_investment_months
    )
    investment_value_series = tuple(
        portfolio_as_of(
            date(year, month, calendar.monthrange(year, month)[1])
        )
        for year, month in visible_investment_months
    )

    recent = tuple(
        RecentTransaction(
            item.description,
            item.account_name,
            item.transaction_date,
            item.amount,
            item.category_color or "#718096",
        )
        for item in selected[:5]
    )

    return DashboardData(
        period_label=period_label,
        month_labels=month_labels,
        regular_income=summary.regular_income,
        other_income=summary.other_income,
        e_transfer_received=summary.e_transfer_received,
        e_transfer_sent=summary.e_transfer_sent,
        e_transfer_net=summary.e_transfer_net,
        e_transfer_income_adjustment=summary.e_transfer_income_adjustment,
        gross_expense_spending=summary.gross_expense_spending,
        reimbursements=summary.reimbursements,
        e_transfer_spending_adjustment=summary.e_transfer_spending_adjustment,
        total_income=summary.total_income,
        total_spending=summary.total_spending,
        account_spending=account_spending,
        person_breakdown=person_breakdown,
        manual_investing_total=manual_investing_total,
        investing_total=investing_total,
        savings_goal=savings_goal,
        cash_savings_actual=cash_savings_actual,
        work_rrsp_employee=work_rrsp_employee,
        employer_rrsp_match=employer_rrsp_match,
        savings_actual=savings_actual,
        savings_balance=savings_balance,
        budget_progress=budget_progress,
        portfolio_value=portfolio_value,
        portfolio_baseline_value=portfolio_baseline_value,
        investment_month_labels=investment_month_labels,
        investment_value_series=investment_value_series,
        previous_income=previous_income,
        previous_spending=previous_spending,
        income_series=make_series(income_accounts, INCOME_ACCOUNT_COLORS),
        spending_series=make_series(spending_accounts, SPENDING_ACCOUNT_COLORS),
        cash_flow_income=tuple(cash_flow_income),
        cash_flow_spending=tuple(cash_flow_spending),
        category_spending=category_spending,
        recent_transactions=recent,
    )
