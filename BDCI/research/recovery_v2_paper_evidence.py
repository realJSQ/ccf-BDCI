"""Verified, versioned manuscript inputs for the recovery-v2 study.

Verification executes the archived verifier with saved responses only. No model
requests, post-hoc plan repairs, or old-paper results enter the primary evidence.
"""
from __future__ import annotations

from collections import Counter
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

SCHEMA = 'recovery_v2_evidence/1'
POLICIES = {
    'A': 'Model-requested reruns in their original order, including duplicates.',
    'D': 'Model requests union declared-graph closure of changed sources; actual topological order.',
    'E': 'Model requests union actual-graph closure of changed sources; actual topological order.',
    'F': 'Full replay when sources change; deduplicated model requests on clean inputs.',
    'G': 'Deterministic actual-graph closure of changed sources; no model plan required.',
}
SCENARIOS = {
    'clean': 'Unchanged source data and complete declared dependencies.',
    'aux_update': 'Auxiliary source changes; declared dependencies remain complete.',
    'joint_update': 'Both sources change; declared dependencies remain complete.',
    'incomplete_lineage': 'Auxiliary source changes; only the declared summarize_aux-to-combine edge is removed.',
}


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_evidence(run):
    """Return fully verified live evidence; reject incomplete/offline studies."""
    root = Path(run).resolve()
    registration = _read(root / 'pre_registration.json')
    analysis = _read(root / 'analysis.json')
    metering = _read(root / 'model_summary.json')
    if (registration.get('mode') != 'live' or registration.get('split') != 'heldout'
            or any(item.get('mode') != 'live' or item.get('status') != 'completed'
                   for item in (analysis, metering))
            or analysis.get('split') != 'heldout'):
        raise ValueError('completed_live_heldout_study_required')
    # Check every archived hash before executing the selected frozen verifier.
    snapshots = registration['frozen_snapshot_sha256']
    verifier_name = 'frozen_source/research/run_recovery_v2.py'
    if verifier_name not in snapshots:
        raise ValueError('missing_frozen_verifier')
    for name, expected in snapshots.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or _sha(path) != expected:
            raise ValueError('snapshot_hash_mismatch')
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    completed = subprocess.run(
        [sys.executable, '-B', str(root / verifier_name), '--verify-run', str(root)],
        cwd=root, env=environment, capture_output=True, text=True, timeout=120)
    if completed.returncode:
        raise ValueError('frozen_study_verification_failed: ' + completed.stderr[-2000:])
    try:
        verification = json.loads(completed.stdout)
    except ValueError as error:
        raise ValueError('invalid_frozen_verifier_output') from error
    if (verification.get('status') != 'verified' or verification.get('mode') != 'live'
            or verification.get('new_api_calls') != 0):
        raise ValueError('invalid_frozen_verifier_result')

    episodes = _read(root / 'episodes.json')
    cases = _read(root / 'base_cases.json')
    case_ids = [case['case_id'] for case in cases]
    expected_pairs = {(case_id, scenario) for case_id in case_ids for scenario in SCENARIOS}
    observed_pairs = [(e['case_id'], e['scenario']) for e in episodes.values()]
    if (len(case_ids) != 9 or len(set(case_ids)) != 9 or len(episodes) != 36
            or len(set(observed_pairs)) != len(observed_pairs)
            or set(observed_pairs) != expected_pairs
            or registration.get('base_instances') != len(cases)
            or registration.get('planned_model_calls') != len(episodes)
            or analysis.get('completed_plans') != len(episodes)
            or analysis.get('planned_plans') != len(episodes)):
        raise ValueError('incomplete_base_scenario_inventory')
    rows = []
    case_source = ast.parse((root / 'frozen_source/research/recovery_v2_cases.py').read_text())
    generation_notes = ast.get_docstring(case_source)
    intervention_notes = next(ast.get_docstring(node) for node in case_source.body
                              if isinstance(node, ast.FunctionDef) and node.name == 'make_scenario')
    graph_contracts = {}
    for case in cases:
        key = 'main=' + str(case['topology']['main_shards']) + ',aux=' + str(case['topology']['aux_shards'])
        first = next(e for e in episodes.values() if e['case_id'] == case['case_id'])
        graph_contracts[key] = first['public']['tool_definitions']
    artifacts = {'pre_registration.json', 'analysis.json', 'base_cases.json', 'episodes.json',
                 'frozen_workflow.py', 'model_summary.json', 'model_usage.jsonl', *snapshots}
    for role, episode in episodes.items():
        if not isinstance(role, str) or Path(role).name != role or role in ('.', '..'):
            raise ValueError('unsafe_episode_id')
        result = _read(root / f'results_{role}.json')
        if (len(result) != len(POLICIES) or {r['policy'] for r in result} != set(POLICIES)
                or any(r['episode_id'] != role or r['case_id'] != episode['case_id']
                       or r['scenario'] != episode['scenario'] for r in result)):
            raise ValueError('incomplete_policy_inventory')
        rows.extend(result)
        artifacts.update((f'{role}.json', f'prompt_{role}.txt', f'raw_{role}.txt', f'results_{role}.json'))
    if (verification.get('plans') != len(episodes) or verification.get('policy_replays') != len(rows)
            or verification.get('total_tokens') != metering['total_tokens']
            or registration.get('paired_model_policy_replays') != 4 * len(episodes)
            or registration.get('deterministic_g_replays') != len(episodes)):
        raise ValueError('replay_inventory_mismatch')
    summary = analysis['summary_by_scenario_policy']
    if (len(summary) != len(SCENARIOS) * len(POLICIES)
            or {(r['scenario'], r['policy']) for r in summary}
            != {(s, p) for s in SCENARIOS for p in POLICIES}
            or any(r['episodes'] != len(cases) for r in summary)):
        raise ValueError('incomplete_summary_matrix')
    paired = analysis['paired_base_instances']
    if (len(paired) != len(cases) or {r['case_id'] for r in paired} != set(case_ids)
            or any(set(r['policies']) != set(POLICIES)
                   or any(p['episodes'] != len(SCENARIOS) for p in r['policies'].values())
                   for r in paired)):
        raise ValueError('incomplete_paired_base_results')
    totals = []
    freshness = []
    for policy in POLICIES:
        selected = [r for r in rows if r['policy'] == policy]
        outcomes = Counter(r['outcome'] for r in selected)
        totals.append({'policy': policy, 'episodes': len(selected),
                       **{key: outcomes[key] for key in ('correct_completion', 'wrong_completion', 'refusal')},
                       'tool_calls': sum(r['tool_calls'] for r in selected),
                       'termination_reasons': dict(sorted(Counter(r['reason'] for r in selected).items()))})
        freshness.append({'policy': policy,
            'current': sum(r['provenance_current'] is True for r in selected),
            'stale': sum(r['provenance_current'] is False for r in selected),
            'not_completed': sum(r['provenance_current'] is None for r in selected)})
    return {
        'schema': SCHEMA, 'study_kind': 'recovery_v2',
        'study_stage': 'self_authored_structural_holdout',
        'writing_does_not_run_experiments': True,
        'base_instance_count': len(cases), 'completed_model_plans': len(episodes),
        'completed_policy_replays': len(rows), 'paired_model_policy_replays': 4 * len(episodes),
        'deterministic_g_replays': len(episodes),
        'policies': POLICIES.copy(), 'scenarios': SCENARIOS.copy(),
        'summary_by_scenario_policy': summary, 'summary_by_policy': totals,
        'paired_base_instances': paired, 'freshness_by_policy': freshness,
        'protocol': registration,
        'frozen_protocol_text': (root / 'frozen_source/docs/superpowers/specs/2026-09-29-recovery-v2-execution.md').read_text(),
        'task_generation_notes': generation_notes,
        'source_intervention_notes': intervention_notes,
        'case_manifest': [{key: case[key] for key in ('case_id', 'family', 'seed', 'topology', 'split')} for case in cases],
        'tool_contracts_by_topology': graph_contracts,
        'information_condition': 'Actual tool dependencies and declared dependencies are visible to the planner and every policy. Actual dependencies are supplied tool contracts, not discovered dependencies.',
        'resource': {**{k: metering[k] for k in ('model_calls', 'total_tokens', 'duration_seconds')},
                     'initial_cache_tool_calls': analysis['initial_cache_tool_calls'],
                     'cost': None, 'duration_scope': 'Native study invocation only; excludes development, literature, and writing.'},
        'development_assistance': {
            'developer_assisted_protocol': registration['developer_assisted_protocol'],
            'specification': 'docs/superpowers/specs/2026-09-29-recovery-v2-execution.md',
            'description': 'The research question follows Agent proposals; the developer corrected dependency propagation, oracle definition, matched information, and structural split before this frozen experiment. Development fixtures are CPU checks, not model observations.'},
        'prior_study': {
            'run': 'replay_runs/live-20260928T144804-532140',
            'role': 'Historical development study, separate from primary v2 evidence.',
            'claim': 'Prior strict execution and post-hoc terminal normalization motivated the revised protocol.',
            'verified_by_this_adapter': False},
        'limitations': [
            'Nine self-authored base instances are the paired analysis units; scenarios and policy replays are repeated measures.',
            'One saved model plan per episode is reused for A/D/E/F; G is deterministic and does not consume that plan.',
            'This is a small self-authored structural holdout, not independent external validation or a public benchmark.',
            'The local pre-run freeze is not public preregistration; the protocol was developer assisted.',
            'The reference scorer is a separate implementation by the same authors, not external independent reproduction.',
            'Numerical correctness and source freshness are separate outcomes; malformed plans are not voluntary refusal.',
            'Static actual-graph closure is an existing mechanism; no novel dependency-discovery algorithm is established.',
            'Report E versus A and G as well as F; equality does not establish statistical equivalence or generalization.',
            'Tool-call counts exclude shared initial-cache construction and are not measured monetary or computational cost.',
            'No transient failures were injected; no retry-effectiveness claim is supported.'],
        'verification': verification,
        'artifact_sha256': {name: _sha(root / name) for name in sorted(artifacts)},
    }
