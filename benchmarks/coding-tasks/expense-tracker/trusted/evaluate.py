"""Trusted unittest entry point. Used on host only for authored fixture validation."""
import argparse
import json
from pathlib import Path
import sys
import unittest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--tests", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.project).resolve()))
    suite = unittest.defaultTestLoader.discover(args.tests, pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stderr).run(suite)
    failures = [case.id() for case, _ in result.failures]
    errors = [case.id() for case, _ in result.errors]
    # Multiple failing subtests count as one failed unittest method, not many
    # negative points against testsRun (which counts methods).
    excluded = {getattr(case, "test_case", case).id() for case, _ in
                result.failures + result.errors + result.skipped + result.expectedFailures}
    excluded.update(case.id() for case in result.unexpectedSuccesses)
    record = {"tests_run": result.testsRun, "passed": result.testsRun - len(excluded),
              "failures": failures, "errors": errors,
              "skipped": len(result.skipped), "successful": result.wasSuccessful()}
    print(json.dumps(record, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
