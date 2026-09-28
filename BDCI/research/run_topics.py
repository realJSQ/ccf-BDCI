"""Native SwarmFlow topic discovery. Offline by default; --live spends a fixed campaign."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import nullcontext
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import time
from unittest.mock import patch

from contracts import validate_and_select
from literature import LiteratureClient, synthetic_fixture

HERE = Path(__file__).resolve().parent
BDCI = HERE.parent
SKILL = HERE / "skills/topic-discovery"
CONSTRAINTS = {
    "research_area": "Language-model agent techniques and evaluation",
    "resources": "Current local computer plus external model API; no GPU or large-model training",
    "pilot_max_minutes": 20, "pilot_max_api_calls": 6,
    "objective": "A falsifiable research question, not a predetermined topic or a product demo",
}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def append_json(path, value):
    with path.open("a") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")


def parse_object(text):
    if not isinstance(text, str) or len(text) > 30000:
        raise ValueError("invalid_model_output_size")
    text = text.strip()
    if text.startswith("```json\n") and text.endswith("```"):
        text = text[8:-3].strip()
    def reject_constant(_):
        raise ValueError("nonfinite_json")
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result
    data = json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_pairs)
    if not isinstance(data, dict):
        raise ValueError("model_object_required")
    return data


def queries(value, minimum=1):
    if (not isinstance(value, list) or not minimum <= len(value) <= 2
            or any(not isinstance(q, str) or not q.strip() or len(q) > 180
                   or any(ord(c) < 32 for c in q) for q in value)
            or len(set(value)) != len(value)):
        raise ValueError("invalid_search_queries")
    return value


class DiscoveryState:
    def __init__(self, root, live):
        self.root, self.live = root, live
        self.sources, self.proposals, self.reviews = {}, [], []
        self.client = LiteratureClient(root / "literature", max_queries=4, max_results=5)

    async def retrieve(self, search_queries):
        for query in search_queries:
            if self.live:
                rows = await asyncio.to_thread(self.client.search, query)
            else:
                rows = []
                for i in (1, 2):
                    row = synthetic_fixture(query)[0]
                    row["id"] = f"synthetic:fixture-{i}"
                    row.pop("content_sha256")
                    row["content_sha256"] = hashlib.sha256(json.dumps(
                        row, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
                    rows.append(row)
            for row in rows:
                self.sources.setdefault(row["id"], row)
            append_json(self.root / "retrieval_events.jsonl", {
                "query": query, "ids": [r["id"] for r in rows],
                "mode": "live" if self.live else "synthetic",
                "cache_hit": self.client.last_cache_hit if self.live else None,
            })
            write_json(self.root / "sources.json", self.sources)
        if len([s for s in self.sources.values() if s.get("abstract")]) < 2:
            raise ValueError("insufficient_literature_evidence")

    def source_context(self):
        # Raw full metadata is retained on disk; truncation is visible to agents.
        return [{"id": s["id"], "title": s["title"][:250], "year": s["year"],
                 "abstract": (s.get("abstract") or "")[:1400],
                 "abstract_truncated": len(s.get("abstract") or "") > 1400,
                 "evidence_kind": s["evidence_kind"], "untrusted_data": True}
                for s in self.sources.values()]

    def prompt(self, role, task):
        text = (SKILL / "roles" / f"{role}.md").read_text()
        text += "\nCONSTRAINTS_JSON\n" + json.dumps(CONSTRAINTS)
        if role != "planner":
            text += "\nSOURCES_JSON\n" + json.dumps(self.source_context(), ensure_ascii=False)
        if role == "critic":
            text += "\nCANDIDATES_JSON\n" + json.dumps(self.proposals, ensure_ascii=False)
        return text + "\nTASK\n" + task

    async def accept(self, role, data):
        write_json(self.root / f"{role}.json", data)
        if role == "planner":
            await self.retrieve(queries(data.get("queries"), minimum=2))
        elif role == "proposer":
            self.proposals = data.get("candidates")
            if (not isinstance(self.proposals, list) or len(self.proposals) > 3
                    or any(not isinstance(c, dict) for c in self.proposals)):
                raise ValueError("invalid_candidates")
            if self.proposals:
                await self.retrieve(queries(data.get("novelty_queries")))
        else:
            self.reviews = data.get("critiques")
            if (not isinstance(self.reviews, list)
                    or any(not isinstance(c, dict) for c in self.reviews)):
                raise ValueError("invalid_critiques")

    def decide(self):
        if not self.proposals:
            return {"status": "needs_revision", "eligible_candidate_ids": [], "decisions": [],
                    "live_pilot_allowed": False, "novelty_proven": False,
                    "competition_score": None, "reason": "no_grounded_candidates",
                    "evidence_mode": "live" if self.live else "synthetic"}
        return validate_and_select(self.proposals, self.reviews, self.sources,
                                   allow_synthetic=not self.live)


def scripted_responses():
    candidate = {
        "id": "TEST-C1", "title": "SYNTHETIC pipeline test, not a research topic",
        "research_question": "Can the pipeline retain and gate a hypothetical comparison?",
        "hypothesis": "A synthetic placeholder, not a scientific hypothesis.",
        "source_ids": ["synthetic:fixture-1", "synthetic:fixture-2"],
        "closest_work_id": "synthetic:fixture-1", "difference": "No real novelty claim.",
        "baseline": "Synthetic control", "metric": "Synthetic count",
        "experiment": {"kind": "local_python", "dataset": "Synthetic contract fixture",
                       "steps": ["Validate schema only; do not execute a pilot"],
                       "max_minutes": 1, "max_api_calls": 0, "needs_gpu": False},
        "risks": ["This fixture is not real literature or a research proposal."],
    }
    return [
        {"queries": ["synthetic agent evaluation", "synthetic agent reliability"], "rationale": "Offline contract test"},
        {"candidates": [candidate], "novelty_queries": ["synthetic competing work"]},
        {"critiques": [{"candidate_id": "TEST-C1", "novelty_concern": "Synthetic only",
                        "verdict": "advance", "reason": "Exercise gate; no live pilot allowed"}]},
    ]


async def execute(root, live, key, ledger):
    from openjiuwen.agent_teams.paths import configure_openjiuwen_home
    from openjiuwen.agent_teams.workflow.backends.team_worker_backend import TeamWorkerBackend
    from openjiuwen.agent_teams.workflow.engine.backends.base import AgentBackend
    from openjiuwen.agent_teams.workflow.engine.budget import BudgetLedger
    from openjiuwen.agent_teams.workflow.engine.primitives import _rt
    from openjiuwen.agent_teams.workflow.engine.runner import run_workflow
    from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig
    from openjiuwen.core.foundation.llm.schema.message import AssistantMessage, UsageMetadata
    from openjiuwen.core.runner import Runner
    from openjiuwen.harness.schema.deep_agent_spec import DeepAgentSpec, ModelSpec, RailSpec, register_rail_provider
    from jiuwenswarm.agents.harness.common.rails.research_budget_rail import ResearchBudgetRail, ResearchRunBudget

    configure_openjiuwen_home(root / "runtime")
    state = DiscoveryState(root, live)
    metering = ResearchRunBudget(root, ledger)
    register_rail_provider("bdci.research_budget", lambda params, context: ResearchBudgetRail(metering))
    spec = DeepAgentSpec(
        model=ModelSpec(model_client_config=ModelClientConfig(
            client_provider="OpenAI", api_base="https://api.deepseek.com", api_key=key,
            max_retries=0, timeout=60, stream_first_chunk_timeout=60),
            model_request_config=ModelRequestConfig(model="deepseek-flash", max_tokens=2200,
                                                   temperature=0, reasoning={"mode": "disabled"})),
        enable_task_loop=False, max_iterations=1, enable_sys_operation=False,
        enable_task_planning=False, enable_security_rail=False, enable_tool_resilience_rail=False,
        auto_create_workspace=False, enable_read_image_multimodal=False, tools=[], skills=[],
        rails=[RailSpec(type="core.team.skill_use", params={"include_tools": False}),
               RailSpec(type="bdci.research_budget")],
    )

    class TopicRouter(AgentBackend):
        def __init__(self):
            super().__init__()
            self.workers = {role: TeamWorkerBackend(model=None, worker_base_spec=spec,
                team_name="research_topics", language="en", session_id=root.name, run_id=root.name)
                for role in ("planner", "proposer", "critic")}

        async def run(self, prompt, opts, schema_json, *, call_key=None):
            role = opts.get("agent_type")
            if role not in self.workers:
                raise ValueError("unknown_topic_role")
            child = self.workers[role]
            child.bind_budget(self.budget)
            child.bind_workflow_budget(self.workflow_budget)
            child.bind_progress_sink(self.progress_sink)
            answer = await child.run(state.prompt(role, prompt), opts, None, call_key=call_key)
            await state.accept(role, parse_object(answer.text))
            return answer

        async def aclose(self):
            for worker in self.workers.values():
                await worker.aclose()

    def progress(event):
        if event.kind == "workflow_started":
            _rt.get().retries = 0  # pinned engine has no public retry option
        append_json(root / "workflow_events.jsonl", asdict(event))

    fake = iter(scripted_responses())
    async def offline_model(_model, *args, **kwargs):
        return AssistantMessage(content=json.dumps(next(fake)), finish_reason="stop",
            usage_metadata=UsageMetadata(input_tokens=1, output_tokens=1, total_tokens=2))

    started = time.monotonic()
    summary = {"mode": "live" if live else "offline_scripted", "model": "deepseek-flash" if live else "scripted",
               "pilot_executed": False, "cost": None}
    try:
        with nullcontext() if live else patch.object(Model, "invoke", offline_model):
            await asyncio.wait_for(run_workflow(str(SKILL / "scripts/workflow.py"), args={},
                backend=TopicRouter(), cap=1, budget=BudgetLedger(total=20000), strict=True,
                journal_path=str(root / "workflow_journal.json"), progress_sink=progress,
                run_id=root.name), timeout=360)
        decision = state.decide()
        write_json(root / "decision.json", decision)
        eligible = decision["eligible_candidate_ids"]
        selected = next((c for c in state.proposals if c.get("id") in eligible), None)
        handoff = {"status": decision["status"], "selected_candidate": selected,
                   "selection_rule": "First eligible candidate in proposer order; provisional until pilot results",
                   "pilot_executed": False, "execution_enabled": False,
                   "requires": "An executor with data verification, code isolation and aggregate budget accounting",
                   "source_ids": selected["source_ids"] if selected else [], "decision": decision}
        write_json(root / "pilot_handoff.json", handoff)
        write_json(root / "revision_queue.json", revision_queue(state.proposals, state.reviews, decision))
        render_report(root, state, decision, handoff, live)
        summary.update(status="completed", topic_status=decision["status"], source_count=len(state.sources),
                       candidate_count=len(state.proposals), selected_candidate_id=selected["id"] if selected else None)
    except BaseException as error:
        summary.update(status="failed", error_type=type(error).__name__)
        raise
    finally:
        summary.update(model_calls=metering.calls, model_usage=metering.usage,
                       total_tokens=sum(r["total_tokens"] for r in metering.usage),
                       duration_seconds=time.monotonic() - started)
        write_json(root / "summary.json", summary)
        await Runner.stop()
    return summary


def revision_queue(proposals, reviews, decision):
    """Carry criticism forward as data, without spending another model request."""
    items = []
    for candidate in proposals:
        cid = candidate.get("id")
        review = next((r for r in reviews if r.get("candidate_id") == cid), {})
        gate = next((d for d in decision.get("decisions", []) if d["candidate_id"] == cid), {})
        if gate.get("status") != "eligible_for_pilot":
            items.append({"candidate_id": cid, "title": candidate.get("title"),
                          "action": "replace" if review.get("verdict") == "reject" else "revise",
                          "critic": review, "gate_reasons": gate.get("reasons", [])})
    return {"status": "pending_revision" if items else "no_revision_items", "items": items,
            "automatic_retry": False, "next_model_calls": 0,
            "requires": ["A separately bounded revision round", "Full-text check of closest prior work",
                         "Operational controls and outcome metrics", "Pilot execution before final topic selection"]}


def render_report(root, state, decision, handoff, live):
    lines = ["# Autonomous topic discovery", "", "LIVE API + retrieved metadata" if live else "OFFLINE SYNTHETIC TEST",
             "", f"Decision: {decision['status']}. Pilot executed: no. Novelty proven: no.", "",
             "Abstract-only Crossref coverage is incomplete. Full-text prior-work checks and actual pilots remain required.", ""]
    for candidate in state.proposals:
        lines += [f"## {candidate.get('id')}: {candidate.get('title')}", "",
                  str(candidate.get("research_question")), "", "Hypothesis: " + str(candidate.get("hypothesis")),
                  "", "Tentative difference: " + str(candidate.get("difference")), "",
                  "Baseline: " + str(candidate.get("baseline")), "Metric: " + str(candidate.get("metric")), "",
                  "```json", json.dumps(candidate.get("experiment"), indent=2, ensure_ascii=False), "```", ""]
        for review in state.reviews:
            if review.get("candidate_id") == candidate.get("id"):
                lines += ["Critic: " + json.dumps(review, ensure_ascii=False), ""]
    lines += ["## Deterministic gate", "", "```json", json.dumps(decision, indent=2), "```", "", "## Sources", ""]
    for source in state.sources.values():
        lines += [f"- {source['id']}: {source['title']} — {source['url'] or 'SYNTHETIC'}"]
    (root / "report.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Use the fixed topic-v1 campaign (3 requests total)")
    args = parser.parse_args()
    mode = "live" if args.live else "offline"
    root = HERE / "runs" / datetime.now(timezone.utc).strftime(f"{mode}-%Y%m%dT%H%M%S-%f")
    root.mkdir(parents=True)
    os.chdir(root)
    # Configure before framework imports, including direct invocation without activate.sh.
    os.environ.setdefault("JIUWENSWARM_HOME", str(root / "runtime"))
    os.environ.setdefault("JIUWENSWARM_DATA_DIR", str(root / "runtime/.jiuwenswarm"))
    key = "offline-placeholder"
    ledger = HERE / "topic-v1-requests.jsonl" if args.live else root / "requests.jsonl"
    lock = ledger.with_suffix(".lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.live:
            keys = re.findall(r"\bsk-[A-Za-z0-9_-]{16,}\b", (BDCI / "apis.txt").read_text())
            if len(keys) != 1:
                raise ValueError("expected_one_credential")
            key = keys[0]
        summary = asyncio.run(execute(root, args.live, key, ledger))
        print(json.dumps({"status": summary["status"], "topic_status": summary["topic_status"], "output": str(root)}))
        return 0
    except BaseException as error:
        if not (root / "summary.json").exists():
            write_json(root / "summary.json", {"status": "failed", "mode": mode,
                                              "error_type": type(error).__name__})
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "output": str(root)}))
        return 1
    finally:
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
