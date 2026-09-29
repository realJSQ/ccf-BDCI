"""No-network tests for persistent research model admissions."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from jiuwenswarm.agents.harness.common.rails.research_budget_rail import (
    ResearchBudgetRail, ResearchRunBudget,
)


def inputs(messages=None, tools=None):
    return SimpleNamespace(messages=messages or ["short prompt"], tools=tools or [])


def response(input_tokens=10, output_tokens=4, finish_reason="stop", total_tokens=None):
    total_tokens = input_tokens + output_tokens if total_tokens is None else total_tokens
    return SimpleNamespace(
        usage_metadata=SimpleNamespace(input_tokens=input_tokens,
                                       output_tokens=output_tokens,
                                       total_tokens=total_tokens),
        finish_reason=finish_reason,
    )


class ResearchBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "ledger.jsonl"
        self.budget = ResearchRunBudget(self.root, self.path, max_calls=3, token_stop=50,
                                       max_prompt_chars=100)

    def cancel(self, reason, function, *args):
        with self.assertRaisesRegex(asyncio.CancelledError, reason):
            function(*args)

    def test_normal_usage_persists_admission_and_usage(self):
        self.budget.admit(inputs())
        self.budget.record_response(response())
        records = self.budget.records()
        self.assertEqual([r["event"] for r in records], ["admission", "usage"])
        self.assertEqual([r["call"] for r in records], [1, 1])
        self.assertEqual(records[-1]["total_tokens"], 14)
        self.assertIsNone(self.budget.active)
        self.assertEqual(json.loads((self.root / "model_usage.jsonl").read_text()), records[-1])

    def test_calls_exhausted_before_next_request(self):
        for _ in range(3):
            self.budget.admit(inputs())
            self.budget.record_response(response())
        self.cancel("research_call_limit", self.budget.admit, inputs())
        self.assertEqual(len(self.budget.records()), 6)
        self.assertEqual(self.budget.calls, 3)

    def test_uncertain_prior_blocks_same_instance_and_reopened_campaign(self):
        self.budget.admit(inputs())
        self.cancel("unresolved_prior_request", self.budget.admit, inputs())
        reopened = ResearchRunBudget(self.root, self.path)
        self.cancel("unresolved_prior_request", reopened.admit, inputs())
        self.assertEqual(len(self.budget.records()), 1)

    def test_missing_usage_does_not_release_admission(self):
        self.budget.admit(inputs())
        self.cancel("missing_or_invalid_usage", self.budget.record_response,
                    SimpleNamespace(finish_reason="stop"))
        self.cancel("unresolved_prior_request", self.budget.admit, inputs())
        self.assertEqual(len(self.budget.records()), 1)

    def test_invalid_and_inconsistent_usage(self):
        self.budget.admit(inputs())
        for bad in (response(-1, 2), response(True, 2)):
            self.cancel("missing_or_invalid_usage", self.budget.record_response, bad)
        self.cancel("inconsistent_usage", self.budget.record_response,
                    response(total_tokens=99))
        self.assertEqual(len(self.budget.records()), 1)

    def test_prompt_char_limit_rejects_before_admission(self):
        self.cancel("research_prompt_limit", self.budget.admit, inputs(["x" * 101]))
        self.assertFalse(self.path.exists())
        self.budget.admit(inputs(["x" * 100]))
        self.assertEqual(self.budget.records()[0]["preview_chars"], 100)

    def test_tools_forbidden_before_admission(self):
        self.cancel("unexpected_research_tools", self.budget.admit,
                    inputs(tools=[{"name": "unexpected"}]))
        self.assertFalse(self.path.exists())

    def test_truncation_records_cost_before_stopping(self):
        self.budget.admit(inputs())
        self.cancel("research_output_truncated", self.budget.record_response,
                    response(finish_reason="length"))
        self.assertEqual(self.budget.records()[-1]["finish_reason"], "length")
        self.assertEqual(self.budget.usage[0]["total_tokens"], 14)
        self.assertIsNone(self.budget.active)

    def test_cumulative_token_threshold_blocks_next_call(self):
        self.budget.admit(inputs())
        self.budget.record_response(response(20, 10))
        self.budget.admit(inputs())
        self.budget.record_response(response(10, 10))
        self.cancel("research_token_stop", self.budget.admit, inputs())
        self.assertEqual(self.budget.calls, 2)

    def test_threshold_is_post_response_and_can_overshoot(self):
        self.budget.admit(inputs())
        self.budget.record_response(response(50, 5))
        self.cancel("research_token_stop", self.budget.admit, inputs())
        self.assertEqual(self.budget.usage[0]["total_tokens"], 55)

    def test_response_without_admission(self):
        self.cancel("response_without_admission", self.budget.record_response, response())

    def test_rail_routes_context_and_cancel_is_base_exception(self):
        rail = ResearchBudgetRail(self.budget)
        asyncio.run(rail.before_model_call(SimpleNamespace(inputs=inputs())))
        asyncio.run(rail.after_model_call(SimpleNamespace(
            inputs=SimpleNamespace(response=response()))))
        self.assertEqual(self.budget.calls, 1)
        self.assertEqual(len(self.budget.usage), 1)
        self.assertFalse(issubclass(asyncio.CancelledError, Exception))

    def test_invalid_constructor_limits(self):
        for name in ("max_calls", "token_stop", "max_prompt_chars"):
            for value in (0, -1, True, 1.5, float("nan")) + ((None,) if name == "max_calls" else ()):
                with self.subTest(name=name, value=value):
                    with self.assertRaisesRegex(ValueError, "invalid_research_budget"):
                        ResearchRunBudget(self.root, self.path, **{name: value})

    def test_unlimited_tokens_keep_accounting_and_call_limit(self):
        budget = ResearchRunBudget(self.root, self.path, max_calls=2,
                                   token_stop=None, max_prompt_chars=None)
        budget.admit(inputs(["x" * 100000]))
        budget.record_response(response(1000000, 2000000))
        reopened = ResearchRunBudget(self.root, self.path, max_calls=2,
                                     token_stop=None, max_prompt_chars=None)
        reopened.admit(inputs())
        reopened.record_response(response(1000000, 2000000))
        self.assertEqual(sum(r["total_tokens"] for r in reopened.records()
                             if r["event"] == "usage"), 6000000)
        self.cancel("research_call_limit", reopened.admit, inputs())

    def test_unlimited_tokens_keep_unresolved_guard(self):
        budget = ResearchRunBudget(self.root, self.path, token_stop=None,
                                   max_prompt_chars=None)
        budget.admit(inputs())
        self.cancel("unresolved_prior_request", budget.admit, inputs())
        self.assertEqual(len(budget.records()), 1)

    def test_sdk_unbounded_ledger_and_provider_output_omission(self):
        from openjiuwen.agent_teams.workflow.engine.budget import BudgetLedger
        from openjiuwen.agent_teams.workflow.engine.runner import _resolve_workflow_budget
        from openjiuwen.core.foundation.llm import ModelClientConfig, ModelRequestConfig
        from openjiuwen.core.foundation.llm.model_clients.openai_model_client import OpenAIModelClient

        ledger = BudgetLedger(total=None)
        ledger.add(10000000)
        self.assertFalse(ledger.exhausted)
        self.assertIsNone(ledger.remaining())
        workflow = _resolve_workflow_budget(SimpleNamespace(meta={}), ledger)
        self.assertIsNone(workflow.total)
        config = ModelRequestConfig(model="deepseek-flash", temperature=0,
                                    reasoning={"mode": "disabled"})
        client = OpenAIModelClient(config, ModelClientConfig(
            client_provider="OpenAI", api_base="https://api.deepseek.com",
            api_key="offline-placeholder"))
        params = client._build_request_params(
            messages=[{"role": "user", "content": "offline check"}], tools=None,
            temperature=None, top_p=None, model=None, stop=None,
            max_tokens=None, stream=False)
        self.assertNotIn("max_tokens", params)
        self.assertNotIn("max_completion_tokens", params)
        self.assertNotIn("max_output_tokens", params)

    def test_optional_limits_are_independent(self):
        budget = ResearchRunBudget(self.root, self.path, token_stop=None,
                                   max_prompt_chars=5)
        self.cancel("research_prompt_limit", budget.admit, inputs(["123456"]))
        budget = ResearchRunBudget(self.root, self.path, token_stop=5,
                                   max_prompt_chars=None)
        budget.admit(inputs(["x" * 100000]))
        budget.record_response(response())
        self.cancel("research_token_stop", budget.admit, inputs())

    def test_corrupted_ledger_fails_closed_before_admission(self):
        admission = {"event": "admission", "call": 1, "run_id": "r1"}
        usage = {"event": "usage", "call": 1, "run_id": "r1", "input_tokens": 2,
                 "output_tokens": 3, "total_tokens": 5}
        cases = {
            "non_object": [None],
            "orphan_usage": [usage],
            "duplicate_admission": [admission, admission],
            "duplicate_usage": [admission, usage, usage],
            "mismatched_call": [admission, dict(usage, call=2)],
            "mismatched_run": [admission, dict(usage, run_id="r2")],
            "bad_sum": [admission, dict(usage, total_tokens=99)],
            "negative_usage": [admission, dict(usage, input_tokens=-1, total_tokens=2)],
            "boolean_usage": [admission, dict(usage, input_tokens=True, total_tokens=4)],
            "missing_usage_field": [admission, {k: v for k, v in usage.items() if k != "total_tokens"}],
            "nonsequential": [dict(admission, call=2)],
        }
        for name, records in cases.items():
            with self.subTest(name=name):
                original = "".join(json.dumps(row) + "\n" for row in records)
                self.path.write_text(original)
                self.cancel("invalid_budget_ledger", self.budget.admit, inputs())
                self.assertEqual(self.path.read_text(), original)
                self.assertEqual(self.budget.calls, 0)

    def test_incomplete_json_ledger_cannot_admit(self):
        original = '{"event": "admission"'
        self.path.write_text(original)
        with self.assertRaises(json.JSONDecodeError):
            self.budget.admit(inputs())
        self.assertEqual(self.path.read_text(), original)
        self.assertEqual(self.budget.calls, 0)


if __name__ == "__main__":
    unittest.main()
