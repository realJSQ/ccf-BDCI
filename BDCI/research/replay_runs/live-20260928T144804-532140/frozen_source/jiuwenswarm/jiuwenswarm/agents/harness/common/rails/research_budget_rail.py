"""Persistent model admission for bounded research runs.

The caller MUST hold an exclusive lock for the entire run. Token usage is a
post-response stop threshold, not a prepaid hard cap. Failed/uncertain requests
consume admissions. A missing usage record prevents reopening that campaign.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from openjiuwen.core.single_agent.rail.base import AgentRail


def _append(path, record):
    with Path(path).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


class ResearchRunBudget:
    def __init__(self, root, ledger_path, *, max_calls=3, token_stop=20000,
                 max_prompt_chars=48000):
        if any(type(v) is not int or v <= 0 for v in
               (max_calls, token_stop, max_prompt_chars)):
            raise ValueError("invalid_research_budget")
        self.root = Path(root)
        self.path = Path(ledger_path)
        self.max_calls = max_calls
        self.token_stop = token_stop
        self.max_prompt_chars = max_prompt_chars
        self.calls = 0
        self.usage = []
        self.active = None

    def records(self):
        if not self.path.exists():
            return []
        records = [json.loads(line) for line in self.path.read_text().splitlines()]
        expected = 1
        pending = None
        for row in records:
            if not isinstance(row, dict):
                raise asyncio.CancelledError("invalid_budget_ledger")
            if row.get("event") == "admission" and pending is None and row.get("call") == expected:
                pending = row
            elif (row.get("event") == "usage" and pending is not None
                  and row.get("call") == expected and row.get("run_id") == pending.get("run_id")):
                values = [row.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")]
                if any(type(v) is not int or v < 0 for v in values) or values[0] + values[1] != values[2]:
                    raise asyncio.CancelledError("invalid_budget_ledger")
                expected += 1
                pending = None
            else:
                raise asyncio.CancelledError("invalid_budget_ledger")
        return records

    def admit(self, inputs):
        records = self.records()
        admitted = [r for r in records if r["event"] == "admission"]
        answered = [r for r in records if r["event"] == "usage"]
        if len(admitted) != len(answered):
            raise asyncio.CancelledError("unresolved_prior_request")
        if len(admitted) >= self.max_calls:
            raise asyncio.CancelledError("research_call_limit")
        if sum(r["total_tokens"] for r in answered) >= self.token_stop:
            raise asyncio.CancelledError("research_token_stop")
        if inputs.tools:
            raise asyncio.CancelledError("unexpected_research_tools")
        # Rail messages are a preview; this is not an exact tokenizer estimate.
        chars = sum(len(str(m)) for m in inputs.messages)
        if chars > self.max_prompt_chars:
            raise asyncio.CancelledError("research_prompt_limit")
        self.active = len(admitted) + 1
        _append(self.path, {"event": "admission", "call": self.active,
                           "run_id": self.root.name, "preview_chars": chars,
                           "timestamp": datetime.now(timezone.utc).isoformat()})
        self.calls += 1

    def record_response(self, response):
        if self.active is None:
            raise asyncio.CancelledError("response_without_admission")
        usage = getattr(response, "usage_metadata", None)
        row = {k: getattr(usage, k, None)
               for k in ("input_tokens", "output_tokens", "total_tokens")}
        if any(type(v) is not int or v < 0 for v in row.values()):
            raise asyncio.CancelledError("missing_or_invalid_usage")
        if row["total_tokens"] != row["input_tokens"] + row["output_tokens"]:
            raise asyncio.CancelledError("inconsistent_usage")
        row.update(event="usage", call=self.active, run_id=self.root.name,
                   finish_reason=getattr(response, "finish_reason", None))
        _append(self.path, row)
        _append(self.root / "model_usage.jsonl", row)
        self.usage.append(row)
        self.active = None
        if row["finish_reason"] == "length":
            raise asyncio.CancelledError("research_output_truncated")


class ResearchBudgetRail(AgentRail):
    """Abort admission with BaseException so ordinary retry rails cannot retry."""
    priority = 1000

    def __init__(self, budget):
        self.budget = budget

    async def before_model_call(self, ctx):
        self.budget.admit(ctx.inputs)

    async def after_model_call(self, ctx):
        self.budget.record_response(ctx.inputs.response)
