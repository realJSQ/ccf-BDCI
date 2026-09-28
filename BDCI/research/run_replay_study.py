"""Pre-frozen, bounded recovery-plan replay study on native SwarmFlow."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re

from native_runner import native_run
from replay_cases import make_cases, make_scenario
from replay_engine import NODES, POLICIES, digest, initial_receipts, public_episode, replay
from replay_reference import score
from run_topics import write_json

HERE = Path(__file__).resolve().parent
SKILL = HERE / 'skills/recovery-replay'
SCENARIOS = ('clean', 'update', 'incomplete_lineage')


class ReplayState:
    def __init__(self, root, live):
        if type(live) is not bool:
            raise ValueError('invalid_replay_mode')
        self.root, self.live, self.outputs, self.results = Path(root), live, {}, []
        self.episodes = {}
        cases = make_cases()
        for base in cases:
            cached = initial_receipts(base)
            for scenario in SCENARIOS:
                current = make_scenario(base, scenario)
                role = f'episode_{len(self.episodes):02d}'
                public = public_episode(base, current, scenario, cached)
                self.episodes[role] = {'case_id': base['case_id'], 'family': base['family'],
                    'scenario': scenario, 'current': current, 'public': public}
        self.roles = tuple(self.episodes)
        write_json(root / 'base_cases.json', cases)
        write_json(root / 'episodes.json', self.episodes)
        self.workflow = root / 'frozen_workflow.py'
        self.workflow.write_text(
            'from swarmflow import agent, phase\n'
            'META = {"name":"recovery-replay", "description":"Paired CPU recovery replay", '
            '"phases":["Recover"], "workflow_token_limit":100000}\n'
            'async def run(args):\n    phase("Recover")\n    outputs = {}\n'
            f'    for role in {self.roles!r}:\n'
            '        outputs[role] = await agent("Produce the bounded recovery plan.", '
            'label=role, options={"agent_type":role,"timeout":100})\n'
            '        if not outputs[role]:\n            raise RuntimeError("missing_recovery_plan")\n'
            '    return outputs\n')
        # Freeze all experiment implementations and prompt text before calls.
        paths = [HERE / n for n in ('run_replay_study.py', 'replay_engine.py', 'replay_cases.py',
                 'replay_reference.py', 'replay_protocol.json', 'native_runner.py', 'run_topics.py')]
        paths += [HERE.parent / 'jiuwenswarm/jiuwenswarm/agents/harness/common/rails/research_budget_rail.py']
        paths += [SKILL / 'roles/planner.md', root / 'base_cases.json', root / 'episodes.json', self.workflow]
        manifest = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        self.frozen = manifest
        snapshot = {}
        for path in paths:
            relative = path.relative_to(HERE.parent) if path.is_relative_to(HERE.parent) else Path('inputs') / path.name
            destination = root / 'frozen_source' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
            snapshot[str(destination.relative_to(root))] = manifest[str(path)]
        self.snapshot = snapshot
        write_json(root / 'pre_registration.json', {'mode': 'live' if live else 'offline_scripted',
            'stage': 'development_only', 'model_calls_planned': 18, 'cpu_replays_planned': 72,
            'base_instances': 6, 'family_count': 3, 'scenario_count': 3,
            'independent_unit': 'base_instance; paired variants are not independent samples',
            'model': 'deepseek-flash', 'max_output_tokens': 1200,
            'campaign': 'research-v2', 'campaign_max_calls': 24,
            'campaign_usage_stop': 100000, 'formal_holdout': False,
            'implementation_sha256': manifest,
            'frozen_snapshot_sha256': snapshot,
            'public_input_sha256': {role: digest(episode['public']) for role, episode in self.episodes.items()}})

    def verify_frozen(self):
        for name, expected in self.frozen.items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
                raise ValueError('experiment_source_changed_after_freeze')
        for name, expected in self.snapshot.items():
            if hashlib.sha256((self.root / name).read_bytes()).hexdigest() != expected:
                raise ValueError('experiment_snapshot_changed_after_freeze')

    def prompt(self, role):
        self.verify_frozen()
        if role not in self.episodes:
            raise ValueError('unknown_replay_role')
        return (SKILL / 'roles/planner.md').read_text() + '\nPUBLIC_OBSERVATION_JSON\n' + json.dumps(
            self.episodes[role]['public'], ensure_ascii=False)

    def accept(self, role, value):
        self.verify_frozen()
        if role not in self.roles or list(self.outputs) != list(self.roles[:self.roles.index(role)]):
            raise ValueError('invalid_replay_role_order')
        episode = self.episodes[role]
        # Invalid model plan objects are scored as refusal, not silently repaired
        # or removed from the denominator. JSON parsing failures remain run failures.
        write_json(self.root / f'{role}.json', value)
        self.outputs[role] = value
        per_episode = []
        for policy in POLICIES:
            result = replay(policy, episode['current'], episode['public'], value)
            result.update(episode_id=role, case_id=episode['case_id'], family=episode['family'],
                          scenario=episode['scenario'])
            # Reference labels are computed only AFTER policy execution.
            result['outcome'] = score(result['artifact'], episode['current'], result['status'])
            per_episode.append(result)
        self.results.extend(per_episode)
        write_json(self.root / f'results_{role}.json', per_episode)

    def offline_response(self, role):
        if self.live:
            raise ValueError('scripted_replay_in_live_mode')
        changed = self.episodes[role]['public']['changed_source_nodes']
        nodes = list(NODES) if changed else []
        return {'actions': [{'op': 'rerun', 'node': node} for node in nodes] + [{'op': 'emit'}],
                'reason': 'Scripted integration fixture; not a model or research result.'}

    def report(self):
        rows = []
        for scenario in SCENARIOS:
            for policy in POLICIES:
                selected = [r for r in self.results if r['scenario'] == scenario and r['policy'] == policy]
                counts = Counter(r['outcome'] for r in selected)
                rows.append({'scenario': scenario, 'policy': policy, 'episodes': len(selected),
                    **{name: counts[name] for name in ('correct_completion', 'wrong_completion', 'refusal')},
                    'tool_calls': sum(r['tool_calls'] for r in selected),
                    'cpu_replay_seconds': sum(r['duration_seconds'] for r in selected)})
        result = {'status': 'completed' if len(self.outputs) == 18 else 'partial',
            'mode': 'live' if self.live else 'offline_scripted', 'stage': 'development_only',
            'base_instance_count': 6, 'completed_model_plans': len(self.outputs),
            'completed_policy_replays': len(self.results), 'summary_by_scenario_policy': rows,
            'initial_cache_tool_calls_shared': len(make_cases()) * len(NODES),
            'descriptive_development_results_only': self.live and len(self.outputs) == 18,
            'claim_scope': 'Descriptive results on these self-authored development instances only.',
            'novelty_established': False, 'formal_study_ready': False}
        families = sorted({episode['family'] for episode in self.episodes.values()})
        result['summary_by_family_scenario_policy'] = []
        for family in families:
            for scenario in SCENARIOS:
                for policy in POLICIES:
                    selected = [r for r in self.results if (r['family'], r['scenario'], r['policy']) ==
                                (family, scenario, policy)]
                    counts = Counter(r['outcome'] for r in selected)
                    result['summary_by_family_scenario_policy'].append({'family': family,
                        'scenario': scenario, 'policy': policy, 'episodes': len(selected),
                        **{name: counts[name] for name in ('correct_completion', 'wrong_completion', 'refusal')},
                        'tool_calls': sum(r['tool_calls'] for r in selected)})
        result['paired_full_minus_selective'] = []
        for role, episode in self.episodes.items():
            pair = {r['policy']: r for r in self.results if r['episode_id'] == role}
            if not all(policy in pair for policy in ('C', 'D')):
                continue
            result['paired_full_minus_selective'].append({'episode_id': role,
                'case_id': episode['case_id'], 'family': episode['family'], 'scenario': episode['scenario'],
                'correct_completion_difference': int(pair['C']['outcome'] == 'correct_completion') -
                                                 int(pair['D']['outcome'] == 'correct_completion'),
                'tool_call_difference': pair['C']['tool_calls'] - pair['D']['tool_calls']})
        write_json(self.root / 'results.json', self.results)
        write_json(self.root / 'report.json', result)
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    mode = 'live' if args.live else 'offline'
    root = HERE / 'replay_runs' / datetime.now(timezone.utc).strftime(f'{mode}-%Y%m%dT%H%M%S-%f')
    root.mkdir(parents=True)
    os.chdir(root)
    state = ReplayState(root, args.live)
    if args.prepare_only:
        print(json.dumps({'status': 'prepared_only', 'output': str(root), 'api_calls': 0}))
        return 0
    ledger = HERE / 'research-v2-requests.jsonl' if args.live else root / 'requests.jsonl'
    try:
        with ledger.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            key = 'offline-placeholder'
            if args.live:
                records = [json.loads(line) for line in ledger.read_text().splitlines()]
                if sum(row['event'] == 'admission' for row in records) + len(state.roles) > 24:
                    raise ValueError('insufficient_remaining_campaign_calls')
                keys = re.findall(r'\bsk-[A-Za-z0-9_-]{16,}\b', (HERE.parent / 'apis.txt').read_text())
                if len(keys) != 1:
                    raise ValueError('expected_one_credential')
                key = keys[0]
            asyncio.run(native_run(root, state.workflow, state, live=args.live, key=key, ledger=ledger,
                max_calls=24, token_stop=100000, timeout=1800, max_output_tokens=1200,
                team_name='recovery_replay'))
        report = state.report()
        summary = json.loads((root / 'model_summary.json').read_text())
        write_json(HERE / 'latest-replay.json', {'run_directory': str(root.relative_to(HERE)), **report})
        print(json.dumps({'status': report['status'], 'output': str(root), 'mode': summary['mode'],
            'model_calls': summary['model_calls'], 'total_tokens': summary['total_tokens'],
            'policy_replays': len(state.results)}))
        return 0
    except BaseException as error:
        state.report()
        write_json(root / 'failure.json', {'error_type': type(error).__name__})
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'output': str(root)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
