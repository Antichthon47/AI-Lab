"""A small in-memory expense ledger with exact decimal arithmetic."""

from dataclasses import dataclass
from datetime import date as Date
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class Transaction:
    id: int
    amount: Decimal
    category: str
    date: Date
    description: str = ""


class ExpenseTracker:
    """Manage positive expense amounts, in insertion order."""

    def __init__(self):
        self._transactions = []
        self._next_id = 1

    def add(self, amount, category, date, description=""):
        if isinstance(amount, (bool, float)):
            raise ValueError("use a decimal string, integer, or Decimal amount")
        try:
            amount = Decimal(amount)
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("invalid amount") from None
        if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
            raise ValueError("amount must be positive with at most two decimal places")
        if not isinstance(category, str) or not category.strip():
            raise ValueError("category is required")
        if not isinstance(description, str):
            raise ValueError("description must be text")
        if not isinstance(date, str):
            raise ValueError("date must be YYYY-MM-DD")
        try:
            parsed = Date.fromisoformat(date)
        except ValueError:
            raise ValueError("date must be YYYY-MM-DD") from None
        if parsed.isoformat() != date:
            raise ValueError("date must be YYYY-MM-DD")
        transaction = Transaction(self._next_id, amount, category.strip(), parsed, description)
        self._transactions.append(transaction)
        self._next_id += 1
        return transaction

    def transactions(self):
        return list(self._transactions)

    def remove(self, transaction_id):
        for transaction in self._transactions:
            if transaction.id == transaction_id:
                self._transactions.remove(transaction)
                return transaction
        raise KeyError(transaction_id)

    def total(self):
        return sum((Decimal(int(t.amount)) for t in self._transactions), Decimal("0.00"))

    def by_category(self, category):
        return [t for t in self._transactions if category.strip().casefold() in t.category.casefold()]

    def between(self, start, end):
        start, end = Date.fromisoformat(start), Date.fromisoformat(end)
        if start > end:
            raise ValueError("start must not follow end")
        return [t for t in self._transactions if start <= t.date < end]

    def monthly_report(self):
        totals = {}
        for transaction in self._transactions:
            key = transaction.date.strftime("%m")
            totals[key] = totals.get(key, Decimal("0.00")) + transaction.amount
        return dict(sorted(totals.items()))
