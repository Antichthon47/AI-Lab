import unittest
from decimal import Decimal
from expense_tracker import ExpenseTracker


class SmokeTests(unittest.TestCase):
    def test_add_and_list(self):
        tracker = ExpenseTracker()
        item = tracker.add("12.50", "Food", "2026-01-02")
        self.assertEqual(item.id, 1)
        self.assertEqual(item.amount, Decimal("12.50"))
        self.assertEqual(tracker.transactions(), [item])

    def test_remove(self):
        tracker = ExpenseTracker()
        item = tracker.add("2", "Travel", "2026-01-02")
        self.assertEqual(tracker.remove(item.id), item)
        self.assertEqual(tracker.transactions(), [])


if __name__ == "__main__":
    unittest.main()
