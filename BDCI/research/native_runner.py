"""Reusable bounded native SwarmFlow adapter; no framework replaced except offline LLM."""
import asyncio
from contextlib import nullcontext
from dataclasses import asdict
import json
from pathlib import Path
import time
from unittest.mock import patch


async def native_run(root, workflow, state, *, live, key, ledger,
                     max_calls=6, token_stop=30000, timeout=420,
                     max_output_tokens=2200, team_name='research_pilot', workflow_args=None):
    if type(live) is not bool or getattr(state, 'live', None) is not live:
        raise ValueError('research_mode_mismatch')
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
    from run_topics import parse_object, write_json, append_json

    configure_openjiuwen_home(root / 'runtime')
    metering = ResearchRunBudget(root, ledger, max_calls=max_calls, token_stop=token_stop,
        **({"max_prompt_chars": None} if token_stop is None else {}))
    request_options = {"model": "deepseek-flash", "temperature": 0,
                       "reasoning": {"mode": "disabled"}}
    if max_output_tokens is not None:
        request_options["max_tokens"] = max_output_tokens
    rail_type = f'bdci.{team_name}_budget'
    register_rail_provider(rail_type, lambda params, context: ResearchBudgetRail(metering))
    spec = DeepAgentSpec(
        model=ModelSpec(model_client_config=ModelClientConfig(
            client_provider='OpenAI', api_base='https://api.deepseek.com', api_key=key,
            max_retries=0, timeout=60, stream_first_chunk_timeout=60),
            model_request_config=ModelRequestConfig(**request_options)),
        enable_task_loop=False, max_iterations=1, enable_sys_operation=False,
        enable_task_planning=False, enable_security_rail=False, enable_tool_resilience_rail=False,
        auto_create_workspace=False, enable_read_image_multimodal=False, tools=[], skills=[],
        rails=[RailSpec(type='core.team.skill_use', params={'include_tools':False}),
               RailSpec(type=rail_type)])

    class Router(AgentBackend):
        def __init__(self):
            super().__init__()
            self.workers = {}
            self.active_role = None

        async def run(self, prompt, opts, schema_json, *, call_key=None):
            role = opts.get('agent_type')
            if role not in state.roles:
                raise ValueError('unknown_pilot_role')
            self.active_role = role
            child = self.workers.setdefault(role, TeamWorkerBackend(
                model=None, worker_base_spec=spec, team_name=team_name, language='en',
                session_id=root.name, run_id=root.name))
            child.bind_budget(self.budget)
            child.bind_workflow_budget(self.workflow_budget)
            child.bind_progress_sink(self.progress_sink)
            full_prompt = state.prompt(role)
            (root / f'prompt_{role}.txt').write_text(full_prompt)
            # Exposed to offline model stub only. Live responses never read oracle.
            state.active_role = role
            answer = await child.run(full_prompt, opts, None, call_key=call_key)
            (root / f'raw_{role}.txt').write_text(answer.text or '')
            # Studies may record malformed model text as a measured failure.
            # Historical workflows retain their strict parser and exceptions.
            decoder = getattr(state, 'decode_response', parse_object)
            data = decoder(answer.text)
            state.accept(role, data)
            # A study may add deterministic, separately archived control feedback
            # after accepting a raw model review. Only its workflow-visible value
            # steers later roles; raw_<role>.txt remains the unmodified model reply.
            workflow_response = getattr(state, 'workflow_response', None)
            answer.text = json.dumps(workflow_response(role, data) if callable(workflow_response) else data)
            return answer

        async def aclose(self):
            for worker in self.workers.values():
                await worker.aclose()

    def progress(event):
        if event.kind == 'workflow_started':
            _rt.get().retries = 0
        append_json(root / 'workflow_events.jsonl', asdict(event))

    async def offline_model(_model, *args, **kwargs):
        return AssistantMessage(content=json.dumps(state.offline_response(state.active_role)),
            finish_reason='stop', usage_metadata=UsageMetadata(input_tokens=1, output_tokens=1, total_tokens=2))

    started = time.monotonic()
    summary = {'mode':'live' if live else 'offline_scripted', 'status':'failed', 'cost':None,
               'team_name':team_name,'max_output_tokens':max_output_tokens}
    try:
        with nullcontext() if live else patch.object(Model, 'invoke', offline_model):
            result = await asyncio.wait_for(run_workflow(str(workflow), args=workflow_args or {}, backend=Router(),
                cap=1, budget=BudgetLedger(total=token_stop), strict=True,
                journal_path=str(root / 'workflow_journal.json'), progress_sink=progress,
                run_id=root.name), timeout=timeout)
        summary['status'] = 'completed'
        return result
    except BaseException as error:
        summary['error_type'] = type(error).__name__
        raise
    finally:
        summary.update(model_calls=metering.calls, model_usage=metering.usage,
                       total_tokens=sum(r['total_tokens'] for r in metering.usage),
                       duration_seconds=time.monotonic()-started)
        write_json(root / 'model_summary.json', summary)
        await Runner.stop()
