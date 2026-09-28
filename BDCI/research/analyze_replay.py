"""Verify saved frozen replay evidence and run a labeled post-hoc normalization.

No model calls. Original plans/results remain immutable. A compatibility rule
can append emit only when a plan already ends by recomputing report. This is a
post-hoc analysis, never a replacement for preregistered strict results.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def load_frozen(root, name):
    path = root / 'frozen_source/research' / (name + '.py')
    spec = importlib.util.spec_from_file_location('frozen_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_report_terminal(plan):
    """Do not manufacture reruns, replace values, override refusal or fix ordering."""
    result = copy.deepcopy(plan)
    if isinstance(result, dict) and isinstance(result.get('actions'), list) and result['actions']:
        if result['actions'][-1] == {'op': 'rerun', 'node': 'report'}:
            result['actions'].append({'op': 'emit'})
    return result


def deterministic(result):
    return {key: value for key, value in result.items() if key != 'duration_seconds'}


def verify_saved(root):
    root = Path(root).resolve()
    registration = read(root / 'pre_registration.json')
    for name, expected in registration['frozen_snapshot_sha256'].items():
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('unsafe_snapshot_path')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('frozen_snapshot_digest_mismatch')
    required = {'frozen_source/research/' + name for name in
                ('replay_engine.py', 'replay_cases.py', 'replay_reference.py')}
    if not required <= registration['frozen_snapshot_sha256'].keys():
        raise ValueError('missing_frozen_implementation')
    engine = load_frozen(root, 'replay_engine')
    cases_module = load_frozen(root, 'replay_cases')
    scorer = load_frozen(root, 'replay_reference')
    cases = read(root / 'base_cases.json')
    if cases != cases_module.make_cases():
        raise ValueError('base_case_reproduction_mismatch')
    episodes = read(root / 'episodes.json')
    expected_episodes = {}
    for base in cases:
        receipts = engine.initial_receipts(base)
        for scenario in ('clean', 'update', 'incomplete_lineage'):
            current = cases_module.make_scenario(base, scenario)
            role = f'episode_{len(expected_episodes):02d}'
            expected_episodes[role] = {'case_id': base['case_id'], 'family': base['family'],
                'scenario': scenario, 'current': current,
                'public': engine.public_episode(base, current, scenario, receipts)}
    if episodes != expected_episodes:
        raise ValueError('episode_reproduction_mismatch')
    all_results = read(root / 'results.json')
    if len(all_results) != 72 or set(episodes) != {f'episode_{i:02d}' for i in range(18)}:
        raise ValueError('incomplete_replay_study')
    replayed = []
    for role, episode in episodes.items():
        if engine.digest(episode['public']) != registration['public_input_sha256'][role]:
            raise ValueError('public_observation_digest_mismatch')
        plan = read(root / f'{role}.json')
        # The same JSON object must come from the saved actual model response.
        raw = (root / f'raw_{role}.txt').read_text().strip()
        if raw.startswith('```json\n') and raw.endswith('```'):
            raw = raw[8:-3].strip()
        if json.loads(raw) != plan:
            raise ValueError('saved_model_plan_mismatch')
        per_episode = []
        for policy in engine.POLICIES:
            result = engine.replay(policy, episode['current'], episode['public'], plan)
            result.update(episode_id=role, case_id=episode['case_id'], family=episode['family'],
                          scenario=episode['scenario'])
            result['outcome'] = scorer.score(result['artifact'], episode['current'], result['status'])
            per_episode.append(result)
        if [deterministic(r) for r in per_episode] != [deterministic(r) for r in read(root / f'results_{role}.json')]:
            raise ValueError('saved_episode_results_mismatch')
        replayed.extend(per_episode)
    if [deterministic(r) for r in replayed] != [deterministic(r) for r in all_results]:
        raise ValueError('saved_aggregate_results_mismatch')
    report = read(root / 'report.json')
    for row in report['summary_by_scenario_policy']:
        selected = [r for r in replayed if (r['scenario'], r['policy']) == (row['scenario'], row['policy'])]
        counts = Counter(r['outcome'] for r in selected)
        if row['episodes'] != len(selected) or row['tool_calls'] != sum(r['tool_calls'] for r in selected):
            raise ValueError('saved_summary_counts_mismatch')
        if any(row[name] != counts[name] for name in ('correct_completion', 'wrong_completion', 'refusal')):
            raise ValueError('saved_summary_outcome_mismatch')
    usage = [json.loads(line) for line in (root / 'model_usage.jsonl').read_text().splitlines()]
    summary = read(root / 'model_summary.json')
    if len(usage) != 18 or summary['model_calls'] != 18 or summary['model_usage'] != usage:
        raise ValueError('saved_model_accounting_mismatch')
    if sum(row['total_tokens'] for row in usage) != summary['total_tokens']:
        raise ValueError('saved_token_accounting_mismatch')
    return engine, scorer, episodes, replayed


def analyze(root):
    root = Path(root).resolve()
    engine, scorer, episodes, strict_results = verify_saved(root)
    posthoc = root / 'posthoc_report_terminal'
    posthoc.mkdir(exist_ok=False)
    results, transformations = [], []
    for role, episode in episodes.items():
        original = read(root / f'{role}.json')
        normalized = normalize_report_terminal(original)
        transformations.append({'episode_id': role, 'changed': original != normalized,
            'original_plan_sha256': engine.digest(original), 'normalized_plan_sha256': engine.digest(normalized)})
        for policy in engine.POLICIES:
            result = engine.replay(policy, episode['current'], episode['public'], normalized)
            result.update(episode_id=role, case_id=episode['case_id'], family=episode['family'],
                          scenario=episode['scenario'])
            result['outcome'] = scorer.score(result['artifact'], episode['current'], result['status'])
            results.append(result)
    comparison = []
    for label, rows in (('preregistered_strict', strict_results), ('posthoc_report_terminal', results)):
        for scenario in ('clean', 'update', 'incomplete_lineage'):
            for policy in engine.POLICIES:
                selected = [r for r in rows if (r['scenario'], r['policy']) == (scenario, policy)]
                counts = Counter(r['outcome'] for r in selected)
                comparison.append({'analysis': label, 'scenario': scenario, 'policy': policy,
                    'episodes': len(selected), **{name: counts[name] for name in
                        ('correct_completion', 'wrong_completion', 'refusal')},
                    'tool_calls': sum(r['tool_calls'] for r in selected)})
    reasons = Counter(r.get('reason') for r in strict_results if r['policy'] == 'A' and r['status'] != 'completed')
    summary = {'status': 'verified_posthoc_analysis', 'model_calls': 0,
        'original_evidence_modified': False, 'strict_policy_replays_verified': len(strict_results),
        'normalization': 'Append emit iff the final existing action is exactly rerun(report). No reruns added.',
        'normalization_implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'transformed_plan_count': sum(t['changed'] for t in transformations),
        'strict_noncompletion_reasons_per_episode': dict(reasons), 'comparison': comparison,
        'limitations': ['Normalization was selected after inspecting these results; it is post hoc, not held-out evidence.',
            'All variants share 18 cached plans from 6 self-authored base instances.',
            'Equal observed correctness does not establish statistical equivalence or general safety.',
            'Selective replay, dependency graphs and terminal-action normalization are not claimed as novel algorithms.'],
        'formal_study_ready': False}
    write(posthoc / 'transformations.json', transformations)
    write(posthoc / 'results.json', results)
    write(posthoc / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        _, _, episodes, results = verify_saved(args.run)
        print(json.dumps({'status': 'verified', 'episodes': len(episodes), 'policy_replays': len(results), 'model_calls': 0}))
    else:
        result = analyze(args.run)
        print(json.dumps({key: result[key] for key in ('status', 'model_calls', 'transformed_plan_count')}))


if __name__ == '__main__':
    main()
