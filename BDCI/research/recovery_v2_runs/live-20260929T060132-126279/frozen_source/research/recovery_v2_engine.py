"""Matched static-dependency recovery on domain-preserving sharded workflows.

No scorer is imported. Actual dependencies are tool contracts, shared with all
policies, not a discovered graph. Historical replay_engine remains unchanged.
"""
from __future__ import annotations

from copy import deepcopy
import time

from replay_engine import digest

POLICIES = ('A', 'D', 'E', 'F', 'G')


def workflow(topology):
    """Insertion order is a topological tool order; shards own complete keys."""
    if (set(topology) != {'main_shards', 'aux_shards'}
            or any(type(n) is not int or not 1 <= n <= 3 for n in topology.values())):
        raise ValueError('invalid_shard_topology')
    nodes = {}
    for side in ('main', 'aux'):
        read = f'read_{side}'
        nodes[read] = {'op': 'read', 'side': side, 'parents': []}
        count = topology[f'{side}_shards']
        if count == 1:
            nodes[f'summarize_{side}'] = {'op': 'summarize', 'side': side, 'parents': [read]}
        else:
            summaries = []
            for index in range(count):
                part, summary = f'partition_{side}_{index}', f'summarize_{side}_{index}'
                nodes[part] = {'op': 'partition', 'side': side, 'parents': [read],
                               'index': index, 'count': count}
                nodes[summary] = {'op': 'summarize', 'side': side, 'parents': [part]}
                summaries.append(summary)
            nodes[f'summarize_{side}'] = {'op': 'merge', 'side': side, 'parents': summaries}
    nodes['combine'] = {'op': 'combine', 'parents': ['summarize_main', 'summarize_aux']}
    nodes['report'] = {'op': 'report', 'parents': ['combine']}
    return nodes


def forward_closure(graph, roots):
    """Include every descendant, including those never requested by a model."""
    if not set(roots) <= graph.keys() or any(not set(p) <= graph.keys() for p in graph.values()):
        raise ValueError('unknown_graph_node')
    reached = set(roots)
    while True:
        expanded = reached | {node for node, parents in graph.items() if reached.intersection(parents)}
        if expanded == reached:
            return [node for node in graph if node in reached]
        reached = expanded


def key_field(family):
    return {'tabular': 'region', 'retrieval': 'entity', 'classification': 'id'}[family]


def summarize(family, side, rows):
    key = key_field(family)
    if side == 'aux':
        field = {'tabular': 'rate', 'retrieval': 'enabled', 'classification': 'label'}[family]
        return {row[key]: row[field] for row in rows}
    if family == 'tabular':
        output = {}
        for row in rows:
            output[row[key]] = output.get(row[key], 0) + row['amount']
        return output
    if family == 'retrieval':
        latest = {}
        for row in rows:
            if row[key] not in latest or row['revision'] > latest[row[key]]['revision']:
                latest[row[key]] = row
        return {name: row['value'] for name, row in latest.items()}
    return {row[key]: row['predicted'] for row in rows}


class Runtime:
    def __init__(self, case, receipts=None):
        self.case = deepcopy(case)
        self.nodes = workflow(case['topology'])
        self.receipts = deepcopy(receipts or {})
        self.trace = []

    def execute(self, node):
        spec = self.nodes[node]
        parents = [self.receipts[p] for p in spec['parents']]
        reads = {p: digest(self.receipts[p]) for p in spec['parents']}
        versions = {}
        for receipt in parents:
            for source, values in receipt['source_versions'].items():
                versions.setdefault(source, set()).update(values)
        op, family = spec['op'], self.case['family']
        if op == 'read':
            side = spec['side']
            source = self.case['sources'][side]
            value = deepcopy(source['rows'])
            versions = {side: {source['revision']}}
            reads = {f'source:{side}': digest(source)}
        elif op == 'partition':
            key = key_field(family)
            value = [deepcopy(row) for row in parents[0]['value']
                     if sum(row[key].encode('utf-8')) % spec['count'] == spec['index']]
        elif op == 'summarize':
            value = summarize(family, spec['side'], parents[0]['value'])
        elif op == 'merge':
            value = {}
            for parent in parents:
                if value.keys() & parent['value'].keys():
                    raise ValueError('overlapping_partition_keys')
                value.update(parent['value'])
        elif op == 'combine':
            main, aux = (p['value'] for p in parents)
            if family == 'tabular':
                value = {'value': sum(v * aux[k] for k, v in main.items()), 'unit': 'weighted_amount'}
            elif family == 'retrieval':
                value = {'value': sum(v for k, v in main.items() if aux[k]), 'unit': 'selected_value'}
            else:
                value = {'correct': sum(v == aux[k] for k, v in main.items()), 'total': len(main)}
        else:
            value = deepcopy(parents[0]['value'])
        receipt = {'value': value, 'source_versions': {k: sorted(v) for k, v in versions.items()}}
        self.receipts[node] = receipt
        self.trace.append({'node': node, 'actual_reads': reads, 'receipt_sha256': digest(receipt)})
        return receipt


def initial_receipts(case):
    runtime = Runtime(case)
    for node in runtime.nodes:
        runtime.execute(node)
    return runtime.receipts


def public_episode(base, current, scenario, cached=None):
    """No scorer output or scenario label is included in the public observation."""
    nodes = workflow(base['topology'])
    actual = {n: spec['parents'][:] for n, spec in nodes.items()}
    declared = deepcopy(actual)
    if scenario == 'incomplete_lineage':
        declared['combine'].remove('summarize_aux')
    elif scenario not in ('clean', 'aux_update', 'joint_update'):
        raise ValueError('unknown_scenario')
    return {'family': base['family'], 'tool_definitions': nodes,
            'actual_dependencies': actual, 'declared_dependencies': declared,
            'nodes_in_execution_order': list(nodes),
            'changed_source_nodes': [f'read_{s}' for s in ('main', 'aux')
                                     if base['sources'][s]['revision'] != current['sources'][s]['revision']],
            'source_revisions': {s: current['sources'][s]['revision'] for s in ('main', 'aux')},
            'cached_receipts': initial_receipts(base) if cached is None else deepcopy(cached),
            'tool_call_budget': 2 * len(nodes)}


def validate_plan(plan, public):
    if not isinstance(plan, dict) or set(plan) - {'actions', 'reason'}:
        raise ValueError('invalid_plan_object')
    if 'reason' in plan and not isinstance(plan['reason'], str):
        raise ValueError('invalid_plan_reason')
    actions = plan.get('actions')
    if not isinstance(actions, list) or not 1 <= len(actions) <= public['tool_call_budget'] + 1:
        raise ValueError('invalid_plan_actions')
    if actions[-1] not in ({'op': 'emit'}, {'op': 'refuse'}):
        raise ValueError('missing_terminal_action')
    for action in actions[:-1]:
        if (not isinstance(action, dict) or set(action) != {'op', 'node'}
                or action['op'] != 'rerun' or not isinstance(action['node'], str)
                or action['node'] not in public['actual_dependencies']):
            raise ValueError('invalid_tool_action')
    return actions


def replay(policy, current, public, plan=None):
    if policy not in POLICIES:
        raise ValueError('unknown_policy')
    started = time.perf_counter()
    runtime = Runtime(current, public['cached_receipts'])
    actual = {n: spec['parents'] for n, spec in runtime.nodes.items()}
    if (public['actual_dependencies'] != actual
            or public['tool_definitions'] != runtime.nodes
            or public['nodes_in_execution_order'] != list(runtime.nodes)):
        raise ValueError('actual_tool_contract_mismatch')
    result = {'policy': policy, 'status': 'refused', 'artifact': None, 'trace': [],
              'tool_calls': 0, 'public_input_sha256': digest(public),
              'plan_sha256': None if policy == 'G' else digest(plan), 'provenance_current': None}

    def finish(reason):
        result.update(reason=reason, trace=deepcopy(runtime.trace),
                      duration_seconds=time.perf_counter() - started)
        return result

    changed = public['changed_source_nodes']
    if policy == 'G':
        nodes = forward_closure(actual, changed)
    else:
        try:
            actions = validate_plan(plan, public)
        except ValueError as error:
            return finish(str(error))
        if actions[-1]['op'] == 'refuse':
            return finish('model_refusal')
        nodes = [a['node'] for a in actions[:-1]]
        if policy == 'F' and changed:
            nodes = list(actual)
        elif policy in ('D', 'E', 'F'):
            graph = actual if policy == 'E' else public['declared_dependencies']
            required = forward_closure(graph, changed) if policy != 'F' else []
            selected = set(nodes) | set(required)
            nodes = [n for n in actual if n in selected]
    for node in nodes:
        if result['tool_calls'] >= public['tool_call_budget']:
            return finish('tool_budget_exhausted')
        result['tool_calls'] += 1
        try:
            runtime.execute(node)
        except (KeyError, ValueError, TypeError) as error:
            return finish('tool_error:' + type(error).__name__)
    report = runtime.receipts['report']
    result.update(status='completed', artifact=deepcopy(report['value']),
                  provenance_current=report['source_versions'] == {
                      s: [v] for s, v in public['source_revisions'].items()})
    return finish('emitted')
