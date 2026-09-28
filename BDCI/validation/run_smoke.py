"""Run the real SwarmFlow/TeamHarness path; offline unless --live is explicit."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import nullcontext
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
BDCI = HERE.parent
SKILL = HERE / "skills/research-smoke"
MAX_CALLS = 3
MAX_OUTPUT = 512


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def append_json(path, value):
    with path.open("a") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")


class CallAllowance:
    """Single-process admission, shared by all workers, persisted for live runs.

    A file lock around the entire live run prevents two processes spending the
    same allowance. Failed/uncertain requests still consume their admission.
    """

    def __init__(self, root, live):
        self.root = root
        self.live = live
        self.path = HERE / "live_requests.jsonl" if live else root / "requests.jsonl"
        self.current = 0
        self.responses = []

    def admit(self):
        prior = len(self.path.read_text().splitlines()) if self.path.exists() else 0
        if prior >= MAX_CALLS:
            raise asyncio.CancelledError("smoke_model_call_limit")
        self.current += 1
        append_json(self.path, {
            "run_id": self.root.name,
            "admission": prior + 1,
            "max_output_tokens": MAX_OUTPUT,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "live" if self.live else "offline",
        })


def experiment_tool(root):
    from openjiuwen.core.foundation.tool import ToolCard
    from openjiuwen.core.foundation.tool.function.function import LocalFunction

    def execute():
        if (root / "metrics.json").exists():
            raise ValueError("experiment_already_executed")
        command = [sys.executable, str(HERE / "queue_experiment.py"), str(root / "metrics.json")]
        start = time.monotonic()
        proc = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        (root / "experiment.stdout").write_text(proc.stdout)
        (root / "experiment.stderr").write_text(proc.stderr)
        metrics = root / "metrics.json"
        receipt = {
            "run_id": root.name,
            "exit_code": proc.returncode,
            "metrics_path": "metrics.json",
            "metrics_sha256": hashlib.sha256(metrics.read_bytes()).hexdigest() if metrics.exists() else "",
            "command": command,
            "duration_seconds": time.monotonic() - start,
        }
        write_json(root / "experiment_receipt.json", receipt)
        return receipt

    return LocalFunction(
        card=ToolCard(
            name="run_queue_experiment",
            description="Run the fixed local FIFO/SJF scheduling simulation exactly once and return its evidence receipt.",
            input_params={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        func=execute,
    )


def verified_metrics(root):
    from jiuwenswarm.agents.harness.common.rails.research_evidence_rail import validate_receipt
    evidence = root / "evidence.jsonl"
    if not evidence.exists():
        raise ValueError("no_rail_evidence")
    rows = [json.loads(line) for line in evidence.read_text().splitlines()]
    if len(rows) != 1:
        raise ValueError("expected_one_experiment_receipt")
    metrics = validate_receipt(root, rows[0])
    # Independent fixture oracle: checks real tool output, not the model's claim.
    expected = {
        "job_count": 5,
        "fifo_mean_completion_units": 16.2,
        "sjf_mean_completion_units": 11.0,
        "total_service_units": 25,
    }
    if metrics != expected:
        raise ValueError("fixture_metrics_mismatch")
    return metrics


async def execute_workflow(root, live, key):
    from openjiuwen.agent_teams.paths import configure_openjiuwen_home
    from openjiuwen.agent_teams.workflow.backends.team_worker_backend import TeamWorkerBackend
    from openjiuwen.agent_teams.workflow.engine.backends.base import AgentBackend
    from openjiuwen.agent_teams.workflow.engine.budget import BudgetLedger
    from openjiuwen.agent_teams.workflow.engine.primitives import _rt
    from openjiuwen.agent_teams.workflow.engine.runner import run_workflow
    from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig
    from openjiuwen.core.foundation.llm.schema.message import AssistantMessage, UsageMetadata
    from openjiuwen.core.foundation.llm.schema.tool_call import ToolCall
    from openjiuwen.core.runner import Runner
    from openjiuwen.core.single_agent.rail.base import AgentRail, ModelCallInputs
    from openjiuwen.harness.schema.deep_agent_spec import (
        BuiltinToolSpec, DeepAgentSpec, ModelSpec, RailSpec,
        register_rail_provider, register_tool_provider,
    )
    from jiuwenswarm.agents.harness.common.rails.research_evidence_rail import ExperimentEvidenceRail

    configure_openjiuwen_home(root / "runtime")
    allowance = CallAllowance(root, live)
    evidence_rail = ExperimentEvidenceRail(root)

    class MeterRail(AgentRail):
        priority = 1000

        async def before_model_call(self, ctx):
            allowance.admit()
            tool_names = sorted(getattr(tool, "name", "") for tool in (ctx.inputs.tools or []))
            expected_tools = ["run_queue_experiment"] if allowance.current <= 2 else []
            if tool_names != expected_tools:
                raise asyncio.CancelledError("unexpected_model_tools")
            append_json(root / "rail_events.jsonl", {
                "event": "before_model_call", "call": allowance.current, "tools": tool_names,
            })

        async def after_model_call(self, ctx):
            if not isinstance(ctx.inputs, ModelCallInputs):
                return
            response = ctx.inputs.response
            usage = getattr(response, "usage_metadata", None)
            row = {
                "call": allowance.current,
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
                "finish_reason": getattr(response, "finish_reason", None),
                "mode": "live" if live else "offline_scripted",
            }
            allowance.responses.append(row)
            append_json(root / "model_usage.jsonl", row)
            if row["finish_reason"] == "length":
                raise asyncio.CancelledError("model_output_truncated")

    register_rail_provider("bdci.smoke_meter", lambda params, context: MeterRail())
    register_rail_provider("bdci.experiment_evidence", lambda params, context: evidence_rail)
    register_tool_provider("bdci.queue_experiment", lambda params, context: experiment_tool(root))
    model = ModelSpec(
        model_client_config=ModelClientConfig(
            client_provider="OpenAI", api_base="https://api.deepseek.com", api_key=key,
            max_retries=0, timeout=60, stream_first_chunk_timeout=60,
        ),
        model_request_config=ModelRequestConfig(
            model="deepseek-flash", max_tokens=MAX_OUTPUT, temperature=0,
            reasoning={"mode": "disabled"},
        ),
    )
    spec = DeepAgentSpec(
        model=model, enable_task_loop=False, max_iterations=2,
        enable_sys_operation=False, enable_task_planning=False,
        enable_security_rail=False, enable_tool_resilience_rail=False,
        auto_create_workspace=False, enable_read_image_multimodal=False,
        skills=[], tools=[BuiltinToolSpec(type="bdci.queue_experiment")],
        rails=[
            RailSpec(type="core.team.skill_use", params={"include_tools": False}),
            RailSpec(type="bdci.smoke_meter"),
            RailSpec(type="bdci.experiment_evidence"),
        ],
    )
    specs = {
        "experimenter": spec,
        "writer": spec.model_copy(update={"max_iterations": 1, "tools": []}),
    }

    class RoleRouter(AgentBackend):
        def __init__(self):
            super().__init__()
            self.children = {
                role: TeamWorkerBackend(
                    model=None, worker_base_spec=role_spec,
                    team_name="research_smoke", language="en", session_id=root.name,
                    run_id=root.name,
                ) for role, role_spec in specs.items()
            }

        async def run(self, prompt, opts, schema_json, *, call_key=None):
            role = opts.get("agent_type")
            if role not in self.children:
                raise ValueError("unknown_role")
            child = self.children[role]
            child.bind_budget(self.budget)
            child.bind_workflow_budget(self.workflow_budget)
            child.bind_progress_sink(self.progress_sink)
            instructions = (SKILL / "roles" / f"{role}.md").read_text()
            if role == "writer":
                instructions += "\nVerified evidence:\n" + json.dumps(verified_metrics(root))
            return await child.run(instructions + "\nTask:\n" + prompt, opts, schema_json, call_key=call_key)

        async def aclose(self):
            for child in self.children.values():
                await child.aclose()

    def progress(event):
        if event.kind == "workflow_started":
            # Pinned engine has no public retries option: disable its default
            # two retries for this run only, before dispatching any worker.
            _rt.get().retries = 0
        append_json(root / "workflow_events.jsonl", asdict(event))

    fake_index = 0

    async def scripted_model(_model, *args, **kwargs):
        nonlocal fake_index
        fake_index += 1
        usage = UsageMetadata(input_tokens=1, output_tokens=1, total_tokens=2)
        if fake_index == 1:
            return AssistantMessage(
                content="", finish_reason="tool_calls", usage_metadata=usage,
                tool_calls=[ToolCall(id="smoke-tool", type="function", name="run_queue_experiment", arguments="{}")],
            )
        if fake_index == 2:
            return AssistantMessage(content="The fixed simulation was executed and its metrics were saved.",
                                    finish_reason="stop", usage_metadata=usage)
        if fake_index == 3:
            return AssistantMessage(
                content="This framework smoke test executed a fixed scheduling simulation and retained its results. "
                        "Shortest-job-first reduced mean completion time for this particular input.\n\n"
                        "This is not a novel research finding. Simulated job time is not measured wall-clock speed. "
                        "The fixed workload cannot establish performance on real agent workloads.",
                finish_reason="stop", usage_metadata=usage,
            )
        raise AssertionError("unexpected_offline_model_request")

    mode = nullcontext() if live else patch.object(Model, "invoke", scripted_model)
    started = time.monotonic()
    try:
        with mode:
            result = await asyncio.wait_for(run_workflow(
                str(SKILL / "scripts/workflow.py"), args={}, backend=RoleRouter(),
                cap=1, budget=BudgetLedger(total=12000), strict=True,
                journal_path=str(root / "workflow_journal.json"), progress_sink=progress,
                run_id=root.name,
            ), timeout=240)
        metrics = verified_metrics(root)
        if allowance.current != 3 or len(allowance.responses) != 3 or evidence_rail.accepted != 1:
            raise ValueError("incomplete_model_or_rail_coverage")
        write_json(root / "result.json", result)
        summary = {
            "status": "framework_passed",
            "mode": "live" if live else "offline_scripted",
            "model_calls": allowance.current,
            "source_rail_accepted": evidence_rail.accepted,
            "source_rail_rejected": evidence_rail.rejected,
            "model_usage": allowance.responses,
            "duration_seconds": time.monotonic() - started,
            "metrics": metrics,
            "cost": None,
        }
        write_json(root / "summary.json", summary)
        render_report(root, result["report"], metrics, live)
        return summary
    except BaseException as error:
        write_json(root / "summary.json", {
            "status": "failed", "mode": "live" if live else "offline_scripted",
            "error_type": type(error).__name__,
            "model_calls": allowance.current, "model_usage": allowance.responses,
            "duration_seconds": time.monotonic() - started,
        })
        raise
    finally:
        await Runner.stop()


def render_report(root, prose, metrics, live):
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    def escape(text):
        return "".join(replacements.get(c, c) for c in text)
    mode = "LIVE API" if live else "OFFLINE SCRIPTED MODEL"
    title = "Research Agent Framework Smoke Test"
    rows = "\n".join(f"{escape(k)} & {v} " + r"\\" for k, v in metrics.items())
    latex = (
        "\\documentclass{article}\n\\usepackage[T1]{fontenc}\n"
        "\\begin{document}\n"
        f"\\title{{{title}}}\\author{{Validation artifact}}\\date{{}}\\maketitle\n"
        f"\\textbf{{{mode}. Not a competition submission.}}\n\n"
        "\\section*{Observed execution}\n" + escape(prose) + "\n\n"
        "\\section*{Deterministically verified metrics}\n"
        "\\begin{tabular}{lr}\nMetric & Value \\\\\n\\hline\n"
        + rows + "\n\\end{tabular}\n\n"
        "Input job durations were [9, 1, 7, 3, 5] abstract service units. "
        "All jobs arrived together on one non-preemptive server. "
        "Means are computed from exact completion times, not LLM estimates.\n"
        "\\end{document}\n"
    )
    (root / "report.tex").write_text(latex)
    (root / "report.md").write_text(f"# {title}\n\n{mode}. Not a competition submission.\n\n{prose}\n\n"
                                    + "\n".join(f"- {k}: {v}" for k, v in metrics.items()) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Use the authorized DeepSeek API; shared limit 3 requests")
    args = parser.parse_args()
    mode = "live" if args.live else "offline"
    run_id = datetime.now(timezone.utc).strftime(f"{mode}-%Y%m%dT%H%M%S-%f")
    root = HERE / "runs" / run_id
    root.mkdir(parents=True)
    # Framework logging defaults to cwd; do not let smoke artifacts escape BDCI.
    os.chdir(root)
    lock = None
    key = "offline-placeholder"
    if args.live:
        import fcntl
        lock = (HERE / "live_requests.lock").open("a")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        keys = re.findall(r"\bsk-[A-Za-z0-9_-]{16,}\b", (BDCI / "apis.txt").read_text())
        if len(keys) != 1:
            raise SystemExit("Expected one credential in apis.txt; no credential printed")
        key = keys[0]
    try:
        summary = asyncio.run(execute_workflow(root, args.live, key))
        print(json.dumps({"status": summary["status"], "mode": mode, "output": str(root)}, ensure_ascii=False))
    except BaseException as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "output": str(root)}))
        return 1
    finally:
        if lock:
            lock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
