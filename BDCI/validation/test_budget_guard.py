"""Offline integration test: the third model call must never be admitted.

Run after sourcing BDCI/activate.sh:
    python -m unittest discover -s BDCI/validation -p test_budget_guard.py
This test uses the real workflow and harness with run_smoke's scripted model.
It never reads credentials or invokes the external model service.
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


class BudgetGuardIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_model_admission_stops_writer(self):
        runs = HERE / "runs"
        runs.mkdir(exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="budget-guard-", dir=runs))
        spec = importlib.util.spec_from_file_location("bdci_budget_guard_runner", HERE / "run_smoke.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        original_cwd = Path.cwd()
        environment = {
            "JIUWENSWARM_HOME": str(root / "runtime"),
            "JIUWENSWARM_DATA_DIR": str(root / "runtime" / ".jiuwenswarm"),
        }
        try:
            os.chdir(root)
            with patch.dict(os.environ, environment), patch.object(runner, "MAX_CALLS", 2):
                with self.assertRaisesRegex(asyncio.CancelledError, "smoke_model_call_limit"):
                    await runner.execute_workflow(root, False, "offline-placeholder")
            admissions = [json.loads(line) for line in (root / "requests.jsonl").read_text().splitlines()]
            usage = [json.loads(line) for line in (root / "model_usage.jsonl").read_text().splitlines()]
            self.assertEqual(len(admissions), 2)
            self.assertEqual([row["admission"] for row in admissions], [1, 2])
            self.assertEqual(len(usage), 2)
            self.assertEqual([row["call"] for row in usage], [1, 2])
            summary = json.loads((root / "summary.json").read_text())
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["error_type"], "CancelledError")
            self.assertEqual(summary["model_calls"], 2)
            self.assertEqual(len((root / "evidence.jsonl").read_text().splitlines()), 1)
            for filename in ("result.json", "report.md", "report.tex"):
                self.assertFalse((root / filename).exists())
            result = {
                "status": "passed",
                "mode": "offline_scripted",
                "model_call_limit": 2,
                "admissions": len(admissions),
                "responses": len(usage),
                "expected_cancellation": "smoke_model_call_limit",
                "writer_result_created": False,
                "description": "The real model-call Rail rejected writer before the third scripted model request.",
            }
            (root / "budget_guard_result.json").write_text(json.dumps(result, indent=2) + "\n")
            print("Budget guard artifacts: " + str(root))
        finally:
            os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
