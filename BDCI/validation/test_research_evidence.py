"""Source BDCI/activate.sh, then python -m unittest discover -s BDCI/validation."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from openjiuwen.core.single_agent.rail.base import ToolCallInputs
from jiuwenswarm.agents.harness.common.rails.research_evidence_rail import (
    ExperimentEvidenceRail, validate_receipt,
)


class EvidenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.metrics = self.root / "metrics.json"
        self.metrics.write_text('{"score":0.5,"count":3}', encoding="utf-8")
        self.receipt = {
            "run_id": "unit-run", "exit_code": 0, "metrics_path": "metrics.json",
            "metrics_sha256": hashlib.sha256(self.metrics.read_bytes()).hexdigest(),
            "command": ["python", "experiment.py"], "duration_seconds": 0.2,
        }
        self.rail = ExperimentEvidenceRail(self.root)

    async def call(self, receipt=None, tool="run_queue_experiment"):
        await self.rail.after_tool_call(SimpleNamespace(inputs=ToolCallInputs(
            tool_name=tool, tool_result=self.receipt if receipt is None else receipt,
        )))

    async def assert_rejected(self, reason):
        with self.assertRaisesRegex(ValueError, "^" + reason + "$"):
            await self.call()
        self.assertEqual((self.rail.accepted, self.rail.rejected), (0, 1))
        self.assertFalse((self.root / "evidence.jsonl").exists())
        self.assertEqual(json.loads((self.root / "evidence_rejections.jsonl").read_text()), {"reason": reason})

    async def test_valid_receipt(self):
        self.receipt["untrusted_extra"] = "omit this"
        await self.call()
        stored = json.loads((self.root / "evidence.jsonl").read_text())
        self.assertEqual(set(stored), set(self.receipt) - {"untrusted_extra"})
        self.assertEqual(validate_receipt(self.root, stored), {"score": 0.5, "count": 3})
        self.assertEqual((self.rail.accepted, self.rail.rejected), (1, 0))

    async def test_failed_exit(self):
        self.receipt["exit_code"] = 1
        await self.assert_rejected("experiment_failed")

    async def test_missing_file(self):
        self.metrics.unlink()
        await self.assert_rejected("metrics_missing")

    async def test_tampered_file(self):
        self.metrics.write_text('{"score":1}')
        await self.assert_rejected("metrics_hash_mismatch")

    async def test_path_escape(self):
        self.receipt["metrics_path"] = "../outside.json"
        await self.assert_rejected("metrics_path_escape")

    async def test_symlink_escape(self):
        (self.root / "outside").symlink_to(self.root.parent, target_is_directory=True)
        self.receipt["metrics_path"] = "outside/outside.json"
        await self.assert_rejected("metrics_path_escape")

    async def test_nan(self):
        self.metrics.write_text('{"score":NaN}')
        self.receipt["metrics_sha256"] = hashlib.sha256(self.metrics.read_bytes()).hexdigest()
        await self.assert_rejected("invalid_metric_value")

    async def test_bool_metric(self):
        self.metrics.write_text('{"score":true}')
        self.receipt["metrics_sha256"] = hashlib.sha256(self.metrics.read_bytes()).hexdigest()
        await self.assert_rejected("invalid_metric_value")

    async def test_other_tool_ignored(self):
        await self.call(receipt={"exit_code": 1}, tool="unrelated")
        self.assertEqual((self.rail.accepted, self.rail.rejected), (0, 0))
        self.assertFalse((self.root / "evidence.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
