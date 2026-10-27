"""Independent specification checks; no imports from the reference code."""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
import unittest
from expense_tracker import ExpenseTracker


class ManagementTests(unittest.TestCase):
    def test_empty(self):
        tracker = ExpenseTracker()
        self.assertEqual(tracker.transactions(), [])
        self.assertEqual(tracker.monthly_report(), {})

    def test_fields(self):
        item = ExpenseTracker().add("3.20", " Food ", "2024-02-29", "lunch")
        self.assertEqual((item.id, item.amount, item.category, item.date, item.description),
                         (1, Decimal("3.20"), "Food", date(2024, 2, 29), "lunch"))

    def test_immutable(self):
        item = ExpenseTracker().add(1, "A", "2026-01-01")
        with self.assertRaises(FrozenInstanceError):
            item.amount = Decimal("4")

    def test_list_is_copy(self):
        tracker = ExpenseTracker()
        item = tracker.add(1, "A", "2026-01-01")
        tracker.transactions().clear()
        self.assertEqual(tracker.transactions(), [item])

    def test_ids_not_reused(self):
        tracker = ExpenseTracker()
        first = tracker.add(1, "A", "2026-01-01")
        self.assertEqual(tracker.remove(first.id), first)
        self.assertEqual(tracker.add(2, "A", "2026-01-01").id, 2)

    def test_missing_remove(self):
        with self.assertRaises(KeyError):
            ExpenseTracker().remove(123)

    def test_invalid_amounts(self):
        for amount in (0, -1, "-0.01", "NaN", "Infinity", "bad", "1.001", True, 1.2, None):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    ExpenseTracker().add(amount, "A", "2026-01-01")

    def test_invalid_fields(self):
        for category, day, description in ((" ", "2026-01-01", ""), (None, "2026-01-01", ""),
                ("A", "2026-02-30", ""), ("A", "20260101", ""), ("A", None, ""),
                ("A", "2026-01-01", 3)):
            with self.subTest(category=category, day=day, description=description):
                with self.assertRaises(ValueError):
                    ExpenseTracker().add(1, category, day, description)

    def test_invalid_add_is_atomic(self):
        tracker = ExpenseTracker()
        with self.assertRaises(ValueError):
            tracker.add(0, "A", "2026-01-01")
        self.assertEqual(tracker.transactions(), [])
        self.assertEqual(tracker.add(1, "A", "2026-01-01").id, 1)


class TotalTests(unittest.TestCase):
    def test_empty_decimal(self):
        value = ExpenseTracker().total()
        self.assertIsInstance(value, Decimal)
        self.assertEqual(value, Decimal("0"))

    def test_cents(self):
        tracker = ExpenseTracker()
        tracker.add("12.50", "A", "2026-01-01")
        tracker.add("3.25", "A", "2026-01-01")
        self.assertEqual(tracker.total(), Decimal("15.75"))

    def test_tiny_amounts(self):
        tracker = ExpenseTracker()
        for _ in range(10):
            tracker.add("0.01", "A", "2026-01-01")
        self.assertEqual(tracker.total(), Decimal("0.10"))

    def test_removal_updates_total(self):
        tracker = ExpenseTracker()
        first = tracker.add("1.20", "A", "2026-01-01")
        tracker.add("2.30", "A", "2026-01-01")
        tracker.remove(first.id)
        self.assertEqual(tracker.total(), Decimal("2.30"))


class CategoryTests(unittest.TestCase):
    def setUp(self):
        self.tracker = ExpenseTracker()
        self.a = self.tracker.add(1, "Food", "2026-01-01")
        self.b = self.tracker.add(2, "Seafood", "2026-01-02")
        self.c = self.tracker.add(3, "FOOD", "2026-01-03")

    def test_case_and_whitespace(self):
        self.assertEqual(self.tracker.by_category(" food "), [self.a, self.c])

    def test_not_substring(self):
        self.assertEqual(self.tracker.by_category("foo"), [])

    def test_unknown(self):
        self.assertEqual(self.tracker.by_category("Rent"), [])

    def test_unicode_casefold(self):
        item = self.tracker.add(1, "Straße", "2026-01-01")
        self.assertEqual(self.tracker.by_category("STRASSE"), [item])


class DateTests(unittest.TestCase):
    def setUp(self):
        self.tracker = ExpenseTracker()
        self.items = [self.tracker.add(1, "A", d) for d in
                      ("2026-02-01", "2026-01-31", "2026-02-28", "2026-03-01")]

    def test_both_boundaries(self):
        self.assertEqual(self.tracker.between("2026-02-01", "2026-02-28"),
                         [self.items[0], self.items[2]])

    def test_same_day(self):
        self.assertEqual(self.tracker.between("2026-02-28", "2026-02-28"), [self.items[2]])

    def test_empty_range(self):
        self.assertEqual(self.tracker.between("2020-01-01", "2020-01-02"), [])

    def test_reversed(self):
        with self.assertRaises(ValueError):
            self.tracker.between("2026-03-01", "2026-02-01")

    def test_leap_day(self):
        item = self.tracker.add(1, "A", "2024-02-29")
        self.assertEqual(self.tracker.between("2024-02-29", "2024-02-29"), [item])


class MonthlyTests(unittest.TestCase):
    def test_year_separation(self):
        tracker = ExpenseTracker()
        tracker.add(2, "A", "2025-01-01")
        tracker.add(3, "A", "2026-01-01")
        self.assertEqual(tracker.monthly_report(), {"2025-01": Decimal(2), "2026-01": Decimal(3)})

    def test_accumulates_same_month(self):
        tracker = ExpenseTracker()
        tracker.add("2.20", "A", "2026-01-01")
        tracker.add("3.30", "B", "2026-01-31")
        self.assertEqual(tracker.monthly_report(), {"2026-01": Decimal("5.50")})

    def test_sorted_and_no_empty_months(self):
        tracker = ExpenseTracker()
        tracker.add(1, "A", "2026-12-31")
        tracker.add(2, "A", "2026-01-01")
        self.assertEqual(list(tracker.monthly_report()), ["2026-01", "2026-12"])

    def test_removal(self):
        tracker = ExpenseTracker()
        item = tracker.add(1, "A", "2026-01-01")
        tracker.remove(item.id)
        self.assertEqual(tracker.monthly_report(), {})


if __name__ == "__main__":
    unittest.main()
