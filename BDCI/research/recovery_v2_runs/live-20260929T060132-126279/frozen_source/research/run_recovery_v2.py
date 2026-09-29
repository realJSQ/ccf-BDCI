"""Prospective native planner study; offline mode uses development cases only."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re

from native_runner import native_run
from recovery_v2_cases import SCENARIOS, make_cases, make_scenario
from recovery_v2_engine import POLICIES, forward_closure, initial_receipts, public_episode, replay
from replay_engine import digest
from replay_reference import score
from run_topics import write_json

HERE = Path(__file__).resolve().parent
SPEC = HERE.parent / 'docs/superpowers/specs/2026-09-29-recovery-v2-execution.md'


def provider_output_capacity():
    model = json.loads((HERE / 'model_capabilities.json').read_text())['model']
    value = model['max_output_tokens']
    if model['id'] != 'deepseek-flash' or type(value) is not int or value <= 0:
        raise ValueError('invalid_model_capacity')
    return value


class RecoveryState:
    def __init__(self, root, live):
        if type(live) is not bool:
            raise ValueError('invalid_mode')
        self.root, self.live = Path(root), live
        self.outputs, self.results, self.episodes = {}, [], {}
        split = 'heldout' if live else 'development'
        cases = make_cases(split)
        for base in cases:
            cached = initial_receipts(base)
            for scenario in SCENARIOS:
                current = make_scenario(base, scenario)
                role = f'episode_{len(self.episodes):02d}'
                self.episodes[role] = {'case_id': base['case_id'], 'family': base['family'],
                    'scenario': scenario, 'current': current,
                    'public': public_episode(base, current, scenario, cached)}
        self.roles = tuple(self.episodes)
        write_json(root / 'base_cases.json', cases)
        write_json(root / 'episodes.json', self.episodes)
        self.workflow = root / 'frozen_workflow.py'
        self.workflow.write_text(
            'from swarmflow import agent, phase\n'
            'META = {"name":"recovery-v2", "description":"Static dependency recovery", '
            '"phases":["Plan"]}\n'
            'async def run(args):\n    phase("Plan")\n    outputs = {}\n'
            f'    for role in {self.roles!r}:\n'
            '        outputs[role] = await agent("Plan recovery.", label=role, '
            'options={"agent_type":role,"timeout":180})\n'
            '    return outputs\n')
        paths = [HERE / name for name in ('run_recovery_v2.py', 'recovery_v2_cases.py',
            'recovery_v2_engine.py', 'recovery_v2_planner.md', 'replay_engine.py',
            'replay_reference.py', 'native_runner.py', 'run_topics.py',
            'model_capabilities.json', 'contracts.py', 'literature.py')]
        paths += [SPEC, HERE.parent / 'jiuwenswarm/jiuwenswarm/agents/harness/common/rails/research_budget_rail.py']
        paths += [root / 'base_cases.json', root / 'episodes.json', self.workflow]
        self.frozen, self.snapshot = {}, {}
        for path in paths:
            value = path.read_bytes()
            self.frozen[str(path)] = hashlib.sha256(value).hexdigest()
            relative = (Path('inputs') / path.name if path.parent == root else path.relative_to(HERE.parent))
            target = root / 'frozen_source' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
            self.snapshot[str(target.relative_to(root))] = self.frozen[str(path)]
        self.registration = {'mode': 'live' if live else 'offline_scripted', 'split': split,
            'local_freeze_not_public_preregistration': True, 'external_benchmark': False,
            'developer_assisted_protocol': True, 'base_instances': len(cases),
            'planned_model_calls': len(self.roles) if live else 0,
            'scripted_calls': len(self.roles) if not live else 0,
            'paired_model_policy_replays': 4 * len(self.roles),
            'deterministic_g_replays': len(self.roles),
            'independent_unit': 'base instance, not scenario or policy',
            'primary_comparison': 'E minus A: correct completion and total tool calls; no gain is valid',
            'strong_baseline': 'G: actual graph closure without model, not novel algorithm',
            'model': 'deepseek-flash', 'temperature': 0, 'reasoning': 'disabled',
            'project_token_stop': None, 'project_prompt_character_limit': None,
            'max_output_tokens': provider_output_capacity(),
            'frozen_snapshot_sha256': self.snapshot, 'source_sha256': self.frozen,
            'public_input_sha256': {role: digest(e['public']) for role, e in self.episodes.items()}}
        write_json(root / 'pre_registration.json', self.registration)
        self.registration_digest = digest(self.registration)
        self.episodes_digest = digest(self.episodes)

    def verify_frozen(self):
        if (digest(self.registration) != self.registration_digest
                or digest(json.loads((self.root / 'pre_registration.json').read_text())) != self.registration_digest
                or digest(self.episodes) != self.episodes_digest):
            raise ValueError('study_registration_or_episode_changed')
        for name, expected in self.frozen.items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
                raise ValueError('study_source_changed_after_freeze')
        for name, expected in self.snapshot.items():
            if hashlib.sha256((self.root / name).read_bytes()).hexdigest() != expected:
                raise ValueError('study_snapshot_changed_after_freeze')
        for role, episode in self.episodes.items():
            if digest(episode['public']) != self.registration['public_input_sha256'][role]:
                raise ValueError('study_public_input_changed_after_freeze')

    def prompt(self, role):
        self.verify_frozen()
        return (HERE / 'recovery_v2_planner.md').read_text() + '\nPUBLIC_OBSERVATION_JSON\n' + json.dumps(
            self.episodes[role]['public'], ensure_ascii=False)

    @staticmethod
    def decode_response(raw):
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate_json_key')
                result[key] = value
            return result

        def reject_constant(value):
            raise ValueError('nonfinite_json')

        try:
            if not isinstance(raw, str):
                raise ValueError('not_text')
            raw = raw.strip()
            if raw.startswith('```json\n') and raw.endswith('```'):
                raw = raw[8:-3].strip()
            value = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
            if not isinstance(value, dict):
                raise ValueError('not_object')
            return value
        except (ValueError, TypeError):
            # Raw text remains in raw_episode_XX.txt, including malformed JSON.
            return {'invalid_model_response': 'not_a_json_object'}

    def accept(self, role, value):
        self.verify_frozen()
        if role not in self.roles or list(self.outputs) != list(self.roles[:self.roles.index(role)]):
            raise ValueError('invalid_episode_order')
        episode = self.episodes[role]
        write_json(self.root / f'{role}.json', value)
        self.outputs[role] = value
        rows = []
        for policy in POLICIES:
            row = replay(policy, episode['current'], episode['public'], value)
            row.update(episode_id=role, case_id=episode['case_id'], family=episode['family'],
                       scenario=episode['scenario'])
            row['outcome'] = score(row['artifact'], episode['current'], row['status'])
            rows.append(row)
        self.results.extend(rows)
        write_json(self.root / f'results_{role}.json', rows)

    def offline_response(self, role):
        if self.live:
            raise ValueError('scripted_response_in_live_mode')
        public = self.episodes[role]['public']
        nodes = forward_closure(public['actual_dependencies'], public['changed_source_nodes'])
        return {'actions': [{'op': 'rerun', 'node': n} for n in nodes] + [{'op': 'emit'}],
                'reason': 'Developer fixture for integration only, not a model observation.'}

    def report(self, *, save=True):
        grouped = []
        for scenario in SCENARIOS:
            for policy in POLICIES:
                rows = [r for r in self.results if (r['scenario'], r['policy']) == (scenario, policy)]
                counts = Counter(r['outcome'] for r in rows)
                grouped.append({'scenario': scenario, 'policy': policy, 'episodes': len(rows),
                    **{k: counts[k] for k in ('correct_completion', 'wrong_completion', 'refusal')},
                    'tool_calls': sum(r['tool_calls'] for r in rows),
                    'termination_reasons': dict(sorted(Counter(r['reason'] for r in rows).items())),
                    'stale_completed': sum(r['provenance_current'] is False for r in rows)})
        pairs = []
        for case_id in dict.fromkeys(e['case_id'] for e in self.episodes.values()):
            policies = {}
            for policy in POLICIES:
                rows = [r for r in self.results if r['case_id'] == case_id and r['policy'] == policy]
                policies[policy] = {'episodes': len(rows),
                    'correct': sum(r['outcome'] == 'correct_completion' for r in rows),
                    'tool_calls': sum(r['tool_calls'] for r in rows)}
            pairs.append({'case_id': case_id, 'policies': policies,
                'E_minus_A_correct': policies['E']['correct'] - policies['A']['correct'],
                'E_minus_A_tool_calls': policies['E']['tool_calls'] - policies['A']['tool_calls']})
        report = {'status': 'completed' if len(self.outputs) == len(self.roles) else 'partial',
            'mode': 'live' if self.live else 'offline_scripted', 'split': self.registration['split'],
            'completed_plans': len(self.outputs), 'planned_plans': len(self.roles),
            'summary_by_scenario_policy': grouped, 'paired_base_instances': pairs,
            'novel_algorithm_claim': False, 'submission_ready': False,
            'initial_cache_tool_calls': sum(len(workflow_case['public']['tool_definitions'])
                for i, workflow_case in enumerate(self.episodes.values()) if i % len(SCENARIOS) == 0),
            'scope': 'Self-authored structural holdout' if self.live else 'Development integration fixtures only'}
        if save:
            write_json(self.root / 'analysis.json', report)
        return report


def verify_saved(root):
    """Recompute every saved policy outcome, including malformed-plan failures."""
    root = Path(root).resolve()
    registration = json.loads((root / 'pre_registration.json').read_text())
    for name, expected in registration['frozen_snapshot_sha256'].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('snapshot_hash_mismatch')
    # Reproduction can invoke the archived script to use the exact source version.
    for name in ('run_recovery_v2.py', 'recovery_v2_engine.py', 'recovery_v2_cases.py',
                 'replay_engine.py', 'replay_reference.py'):
        expected = registration['frozen_snapshot_sha256'][f'frozen_source/research/{name}']
        if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != expected:
            raise ValueError('run_verifier_from_frozen_source')
    for name in ('base_cases.json', 'episodes.json', 'frozen_workflow.py'):
        expected = registration['frozen_snapshot_sha256'][f'frozen_source/inputs/{name}']
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError('saved_input_hash_mismatch')
    state = RecoveryState.__new__(RecoveryState)
    state.root = root
    state.live = registration['mode'] == 'live'
    state.registration = registration
    state.episodes = json.loads((root / 'episodes.json').read_text())
    state.roles = tuple(state.episodes)
    state.outputs, state.results = {}, []
    for role, episode in state.episodes.items():
        public = episode['public']
        if digest(public) != registration['public_input_sha256'][role]:
            raise ValueError('public_binding_mismatch')
        expected_prompt = (root / 'frozen_source/research/recovery_v2_planner.md').read_text() + '\nPUBLIC_OBSERVATION_JSON\n' + json.dumps(public, ensure_ascii=False)
        if (root / f'prompt_{role}.txt').read_text() != expected_prompt:
            raise ValueError('prompt_binding_mismatch')
        value = json.loads((root / f'{role}.json').read_text())
        raw_value = state.decode_response((root / f'raw_{role}.txt').read_text())
        if digest(value) != digest(raw_value):
            raise ValueError('raw_plan_binding_mismatch')
        state.outputs[role] = value
        saved = json.loads((root / f'results_{role}.json').read_text())
        if [r['policy'] for r in saved] != list(POLICIES):
            raise ValueError('policy_inventory_mismatch')
        for row in saved:
            expected = replay(row['policy'], episode['current'], public, value)
            expected.update(episode_id=role, case_id=episode['case_id'], family=episode['family'],
                            scenario=episode['scenario'])
            expected['outcome'] = score(expected['artifact'], episode['current'], expected['status'])
            duration = row.get('duration_seconds')
            if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
                raise ValueError('invalid_replay_duration')
            expected.pop('duration_seconds')
            observed = {k: v for k, v in row.items() if k != 'duration_seconds'}
            if digest(expected) != digest(observed):
                raise ValueError('recomputed_policy_result_mismatch')
        state.results.extend(saved)
    if digest(state.report(save=False)) != digest(json.loads((root / 'analysis.json').read_text())):
        raise ValueError('analysis_mismatch')
    summary = json.loads((root / 'model_summary.json').read_text())
    usage = [json.loads(line) for line in (root / 'model_usage.jsonl').read_text().splitlines() if line.strip()]
    for call, row in enumerate(usage, 1):
        if (any(type(row.get(k)) is not int or row[k] < 0
                for k in ('input_tokens', 'output_tokens', 'total_tokens'))
                or row['input_tokens'] + row['output_tokens'] != row['total_tokens']
                or type(row.get('call')) is not int or row['call'] != call
                or row.get('run_id') != root.name or row.get('event') != 'usage'
                or row.get('finish_reason') != 'stop'):
            raise ValueError('invalid_completed_study_usage')
    if (summary['mode'] != registration['mode'] or summary['status'] != 'completed'
            or summary['model_usage'] != usage or summary['model_calls'] != len(state.roles)
            or len(usage) != len(state.roles)
            or summary['total_tokens'] != sum(r['total_tokens'] for r in usage)):
        raise ValueError('usage_summary_mismatch')
    return {'status': 'verified', 'mode': summary['mode'], 'plans': len(state.outputs),
            'policy_replays': len(state.results), 'total_tokens': summary['total_tokens'], 'new_api_calls': 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--verify-run', type=Path)
    args = parser.parse_args(argv)
    if args.verify_run:
        if args.live or args.prepare_only:
            parser.error('--verify-run cannot start a new study')
        print(json.dumps(verify_saved(args.verify_run)))
        return 0
    mode = 'live' if args.live else 'offline'
    root = HERE / 'recovery_v2_runs' / datetime.now(timezone.utc).strftime(f'{mode}-%Y%m%dT%H%M%S-%f')
    root.mkdir(parents=True)
    state = RecoveryState(root, args.live)
    if args.prepare_only:
        print(json.dumps({'status': 'prepared_only', 'output': str(root), 'api_calls': 0}))
        return 0
    os.chdir(root)
    ledger = HERE / 'recovery-v2-requests.jsonl' if args.live else root / 'requests.jsonl'
    try:
        with ledger.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.live and ledger.exists() and ledger.read_text().strip():
                raise ValueError('campaign_already_started_do_not_repeat')
            key = 'offline-placeholder'
            if args.live:
                keys = re.findall(r'\bsk-[A-Za-z0-9_-]{16,}\b', (HERE.parent / 'apis.txt').read_text())
                if len(keys) != 1:
                    raise ValueError('expected_one_credential')
                key = keys[0]
            asyncio.run(native_run(root, state.workflow, state, live=args.live, key=key, ledger=ledger,
                max_calls=len(state.roles), token_stop=None, timeout=7200,
                max_output_tokens=provider_output_capacity(), team_name='recovery_v2'))
        report = state.report()
        if args.live:
            write_json(HERE / 'latest-recovery-v2.json', {'run_directory': str(root.relative_to(HERE)),
                                                        'status': report['status']})
        print(json.dumps({'status': report['status'], 'output': str(root), 'plans': len(state.outputs)}))
        return 0
    except BaseException as error:
        state.report()
        write_json(root / 'failure.json', {'error_type': type(error).__name__})
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'output': str(root)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
