# Mini Expense Tracker

Repair this standard-library Python package while preserving its public API.
Use Python 3.12 or newer. No dependencies, database, CLI, or network are needed.

`from expense_tracker import ExpenseTracker, Transaction`

- `ExpenseTracker()` creates an empty in-memory ledger.
- `add(amount, category, date, description="")` returns an immutable Transaction
  with fields `id`, `amount`, `category`, `date`, and `description`. IDs start at
  1 and increase without reuse. Amounts are positive Decimal values, supplied as
  decimal strings, integers, or Decimal objects with at most two fractional
  places. Reject floats, booleans, nonfinite amounts, zero, negatives, invalid
  dates, empty categories and nontext descriptions with ValueError. Dates passed
  to add are strings in canonical YYYY-MM-DD form; stored dates are date objects.
  Trim category whitespace when adding, retaining spelling and case.
- `transactions()` returns a separate list in insertion order.
- `remove(id)` returns the removed transaction or raises KeyError for an unknown
  ID. Invalid additions must not consume IDs or change ledger contents.
- `total()` returns the exact Decimal sum, including Decimal zero for an empty ledger.
- `by_category(category)` returns matching transactions in insertion order.
  Match the whole category after stripping query whitespace, ignoring Unicode
  case differences. An unknown category returns an empty list.
- `between(start, end)` accepts ISO date strings and returns transactions whose
  dates fall within both inclusive bounds, in insertion order. Reversed bounds
  raise ValueError. A one-day range is valid.
- `monthly_report()` returns a dictionary from YYYY-MM to exact Decimal totals,
  sorted by month, retaining the year. Include only months with transactions.

Example: adding `"12.50"` and `"3.25"` to the same category and month gives a
total and monthly total of Decimal("15.75").

Run the visible smoke tests from this directory:

```sh
python3 -m unittest discover -s tests -v
```

Additional independent acceptance tests evaluate the documented behavior. Keep
the package importable directly from this directory and do not add dependencies.
