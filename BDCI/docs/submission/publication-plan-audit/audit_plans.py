#!/usr/bin/env python3
"""Zero-API, post-hoc descriptive audit of the 36 already saved model plans.

No frozen input is modified; reruns reproduce existing plans locally using the
frozen engine. Repeated plan signatures are not additional independent samples.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signature(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def independent_closure(graph, roots):
    reached, pending = set(roots), list(roots)
    while pending:
        parent = pending.pop()
        for node, dependencies in graph.items():
            if parent in dependencies and node not in reached:
                reached.add(node)
                pending.append(node)
    return [node for node in graph if node in reached]


def audit(run):
    frozen = run / 'frozen_source/research'
    sys.path.insert(0, str(frozen))
    spec = importlib.util.spec_from_file_location('audited_frozen_v2_engine', frozen / 'recovery_v2_engine.py')
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    paths = [run / 'episodes.json', frozen / 'recovery_v2_engine.py', frozen / 'replay_engine.py',
             run / 'frozen_source/inputs/episodes.json']
    episodes = json.loads((run / 'episodes.json').read_text())
    assert episodes == json.loads((run / 'frozen_source/inputs/episodes.json').read_text())
    assert len(episodes) == 36
    records, representatives = [], defaultdict(list)
    actions_signatures, complete_signatures = Counter(), Counter()
    signature_episodes = defaultdict(list)
    for episode_id, episode in sorted(episodes.items()):
        plan_file, raw_file, results_file = [run / (prefix + episode_id + suffix)
                                           for prefix, suffix in (('', '.json'), ('raw_', '.txt'), ('results_', '.json'))]
        paths.extend((plan_file, raw_file, results_file))
        plan = json.loads(plan_file.read_text())
        raw_plan = json.loads(raw_file.read_text())
        assert raw_plan == plan, ('raw_vs_saved_mismatch', episode_id)
        public = episode['public']
        engine.validate_plan(plan, public)
        results = {r['policy']: r for r in json.loads(results_file.read_text())}
        closure = independent_closure(public['actual_dependencies'], public['changed_source_nodes'])
        assert closure == engine.forward_closure(public['actual_dependencies'], public['changed_source_nodes'])
        requested = [a['node'] for a in plan['actions'] if a['op'] == 'rerun']
        trace = [a['node'] for a in results['A']['trace']]
        reproduced = engine.replay('A', episode['current'], public, plan)
        # Timings are non-deterministic; all semantic fields are checked exactly.
        assert all(results['A'][key] == value for key, value in reproduced.items() if key != 'duration_seconds')
        actions_signatures[signature(plan['actions'])] += 1
        signature_episodes[signature(plan['actions'])].append(episode_id)
        complete_signatures[signature(plan)] += 1
        position = {node: i for i, node in enumerate(requested)}
        # Topological order among rerun nodes only. Unrerun parents may legally use cache.
        topological = (len(position) == len(requested) and all(position[parent] < position[node]
                        for node in requested for parent in public['actual_dependencies'][node] if parent in position))
        row = {'episode_id': episode_id, 'family': episode['family'], 'scenario': episode['scenario'],
               'topology': episode['current']['topology'], 'terminal': plan['actions'][-1]['op'],
               'requested_nodes_in_order': requested, 'A_trace_nodes_in_order': trace,
               'actual_closure_in_engine_order': closure,
               'duplicate_rerun_count': len(requested) - len(set(requested)),
               'A_order_exactly_raw_plan': trace == requested,
               'requested_node_set_equals_actual_closure': set(requested) == set(closure),
               'requested_order_equals_actual_closure_order': requested == closure,
               'requested_order_is_topological': topological, 'A_semantic_reproduction_matches': True}
        records.append(row)
        group = (episode['current']['topology']['main_shards'], episode['current']['topology']['aux_shards'], episode['scenario'])
        representatives[group].append(row)
    groups = []
    for (m, a, scenario), rows in sorted(representatives.items()):
        groups.append({'main_shards': m, 'aux_shards': a, 'scenario': scenario,
                       'episode_ids': [r['episode_id'] for r in rows], 'families': [r['family'] for r in rows],
                       'same_requested_sequence_across_families': len({signature(r['requested_nodes_in_order']) for r in rows}) == 1,
                       'representative_episode': rows[0]['episode_id'],
                       'requested_nodes_in_order': rows[0]['requested_nodes_in_order'],
                       'actual_closure_in_engine_order': rows[0]['actual_closure_in_engine_order']})
    return {'schema': 'saved_plan_posthoc_audit/1', 'study_run_name': run.name,
            'scope': 'Post-hoc descriptive analysis of existing saved plans; zero model calls; no new scientific trials.',
            'input_sha256': {str(p.relative_to(run)): digest(p) for p in sorted(paths)},
            'audit_script_sha256': digest(Path(__file__)),
            'summary': {'plans': len(records), 'independent_base_instances': 9,
                        'plans_with_duplicate_rerun_nodes': sum(r['duplicate_rerun_count'] > 0 for r in records),
                        'duplicate_rerun_occurrences': sum(r['duplicate_rerun_count'] for r in records),
                        **{key: sum(r[key] for r in records) for key in (
                            'A_order_exactly_raw_plan', 'requested_node_set_equals_actual_closure',
                            'requested_order_equals_actual_closure_order', 'requested_order_is_topological',
                            'A_semantic_reproduction_matches')},
                        'unique_action_sequences_ignoring_reason': len(actions_signatures),
                        'unique_complete_plans_including_reason': len(complete_signatures),
                        'action_sequence_frequency_distribution': sorted(actions_signatures.values(), reverse=True)},
            'episodes': records, 'topology_scenario_representatives': groups,
            'action_sequence_groups': [{'actions': json.loads(sig), 'episode_ids': ids, 'count': len(ids)}
                                       for sig, ids in sorted(signature_episodes.items(), key=lambda item: (-len(item[1]), item[0]))],
            'interpretation_limits': [
                'No duplicate requests or out-of-order requests occurred in these saved plans. This observation does not test engine response to such requests.',
                'Frozen replay code passes A rerun actions through in listed order without deduplication or topological sorting. D/E/F use a set union and engine order; G uses closure order.',
                'Matching closure describes emitted plans under supplied graphs and execution order, not unseen-graph inference or superiority over the deterministic baseline.',
                'Repeated action signatures across families or scenarios are descriptive similarity, not independent replications.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.run.resolve())
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()
