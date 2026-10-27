"""Harness safety checks. These never launch an agent or an edited candidate."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("expense_benchmark_runner", ROOT/"runner.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)/"work"
        self.work.mkdir()

    def test_two_resets_are_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = runner.clean_copy(Path(tmp)/"first")
            second = runner.clean_copy(Path(tmp)/"second")
            self.assertEqual(first, second)

    def test_changed_fixture_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"fixture"
            runner.clean_copy(path)
            (path/"README.md").write_text("changed")
            with patch.object(runner, "FIXTURE", path):
                with self.assertRaises(ValueError):
                    runner.clean_copy(Path(tmp)/"target")

    def test_agent_mounts_exclude_trusted_material(self):
        cmd = runner.sandbox(self.work)
        mounts = [cmd[i+1] for i, token in enumerate(cmd) if token in ("--bind", "--ro-bind")]
        self.assertNotIn(str(runner.TRUSTED), mounts)
        self.assertFalse(any(str(runner.TRUSTED).startswith(p+"/") for p in mounts))
        self.assertNotIn("/tests", cmd)

    def test_evaluator_is_offline_and_readonly_tests(self):
        cmd = runner.sandbox(self.work, tests=True)
        self.assertIn("--unshare-all", cmd)
        self.assertNotIn("--share-net", cmd)
        i = cmd.index(str(runner.TRUSTED/"regression"))
        self.assertEqual(cmd[i-1], "--ro-bind")
        self.assertEqual(cmd[i+1], "/tests")

    def test_broad_runtime_mount_rejected(self):
        with self.assertRaises(ValueError):
            runner.sandbox(self.work, runtime=[str(Path.home())])

    def test_failed_probe_never_falls_back_to_host(self):
        with patch.object(runner, "capture", return_value={"exit_status":1}) as capture:
            with self.assertRaises(RuntimeError):
                runner.probe(self.work, Path(self.temp.name)/"probe-log")
            self.assertEqual(capture.call_count, 1)
            self.assertIn("bwrap", capture.call_args.args[0][0])

    def test_approval_required_before_attempt_creation(self):
        with patch.object(runner, "prepare") as prepare, patch.object(sys, "argv", ["runner.py", "run", "test", "--", "never-execute"]):
            with self.assertRaises(SystemExit) as exc:
                runner.main()
            self.assertEqual(exc.exception.code, 2)
            prepare.assert_not_called()

    def test_failure_of_live_probe_prevents_agent_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(runner,"prepare",return_value=Path(tmp)), \
                 patch.object(runner,"validate_isolation",return_value={"passed":True}), \
                 patch.object(runner,"probe",side_effect=RuntimeError("probe blocked")), \
                 patch.object(runner,"capture") as capture, \
                 patch.object(sys,"argv",["runner.py","run","test","--approved","--","never-execute"]):
                with self.assertRaises(RuntimeError):
                    runner.main()
                capture.assert_not_called()

    def test_host_network_rejected(self):
        with self.assertRaises(ValueError):
            runner.sandbox(self.work,host_network=True)

    def test_missing_helper_does_not_fallback(self):
        from security import isolation
        with patch.object(isolation,"HELPER",Path(self.temp.name)/"missing"):
            with self.assertRaises((OSError,RuntimeError)):
                runner.sandbox(self.work)

    def test_evaluator_cannot_mount_broker(self):
        with self.assertRaises(ValueError):
            runner.sandbox(self.work,tests=True,broker=Path(self.temp.name))

    def test_full_offline_gate_failure_blocks_agent(self):
        with patch.object(runner,"prepare",return_value=Path(self.temp.name)), \
             patch.object(runner,"validate_isolation",side_effect=RuntimeError("gate failed")), \
             patch.object(runner,"capture") as capture, \
             patch.object(sys,"argv",["runner.py","run","test","--approved","--","never-execute"]):
            with self.assertRaises(RuntimeError):
                runner.main()
            capture.assert_not_called()


if __name__ == "__main__":
    unittest.main()
