"""Validate local experiment receipts at the real tool-call boundary.

Receipts establish file integrity and successful execution as reported by the
trusted experiment tool; they do not establish scientific correctness.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from openjiuwen.core.single_agent.rail.base import AgentCallbackContext, AgentRail, ToolCallInputs

_FIELDS = (
    "run_id", "exit_code", "metrics_path", "metrics_sha256", "command", "duration_seconds",
)


def validate_receipt(root: Path, receipt: dict) -> dict:
    """Return verified numeric metrics, or raise ValueError with a fixed reason.

    ``metrics_path`` must be relative to root, including after resolving symlinks.
    Unknown receipt fields are ignored and never persisted by the rail.
    """
    if not isinstance(receipt, dict):
        raise ValueError("invalid_receipt")
    if not isinstance(receipt.get("run_id"), str) or not receipt["run_id"].strip():
        raise ValueError("invalid_run_id")
    if type(receipt.get("exit_code")) is not int or receipt["exit_code"] != 0:
        raise ValueError("experiment_failed")
    command = receipt.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(v, str) and v for v in command):
        raise ValueError("invalid_command")
    duration = receipt.get("duration_seconds")
    if type(duration) not in (int, float) or duration < 0:
        raise ValueError("invalid_duration")
    try:
        if not math.isfinite(duration):
            raise ValueError("invalid_duration")
    except OverflowError:
        raise ValueError("invalid_duration") from None
    relative = receipt.get("metrics_path")
    if not isinstance(relative, str) or not relative or "\x00" in relative or Path(relative).is_absolute():
        raise ValueError("invalid_metrics_path")
    try:
        resolved_root = Path(root).resolve(strict=True)
        path = (resolved_root / relative).resolve()
        if not path.is_relative_to(resolved_root):
            raise ValueError("metrics_path_escape")
        if not path.is_file():
            raise ValueError("metrics_missing")
        content = path.read_bytes()
    except (OSError, RuntimeError):
        raise ValueError("metrics_unreadable") from None
    digest = receipt.get("metrics_sha256")
    if not isinstance(digest, str) or hashlib.sha256(content).hexdigest() != digest:
        raise ValueError("metrics_hash_mismatch")
    try:
        metrics = json.loads(content)
    except (ValueError, UnicodeError):
        raise ValueError("invalid_metrics_json") from None
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError("invalid_metrics_shape")
    for value in metrics.values():
        if type(value) not in (int, float):
            raise ValueError("invalid_metric_value")
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("invalid_metric_value")
    return metrics


class ExperimentEvidenceRail(AgentRail):
    """Archive validated receipts for the selected experiment tool only."""

    def __init__(self, root: Path, tool_name: str = "run_queue_experiment") -> None:
        super().__init__()
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.tool_name = tool_name
        self.accepted = 0
        self.rejected = 0

    async def after_tool_call(self, ctx: AgentCallbackContext) -> None:
        inputs = ctx.inputs
        if not isinstance(inputs, ToolCallInputs) or inputs.tool_name != self.tool_name:
            return
        receipt = inputs.tool_result
        try:
            validate_receipt(self.root, receipt)
        except ValueError as exc:
            self.rejected += 1
            self._append("evidence_rejections.jsonl", {"reason": str(exc)})
            raise
        self._append("evidence.jsonl", {field: receipt[field] for field in _FIELDS})
        self.accepted += 1

    def _append(self, filename: str, record: dict) -> None:
        with (self.root / filename).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
