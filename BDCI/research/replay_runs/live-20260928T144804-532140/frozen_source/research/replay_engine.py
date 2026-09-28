"""CPU tools and matched recovery adapters. This module never imports a scorer.

Declared lineage is policy-visible; actual tool reads are executed independently
and retained in the trace for post-run analysis. No arbitrary model code runs.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time

NODES = ('read_main', 'summarize_main', 'read_aux', 'summarize_aux', 'combine', 'report')
DEPENDENCIES = {'read_main': [], 'summarize_main': ['read_main'], 'read_aux': [],
                'summarize_aux': ['read_aux'], 'combine': ['summarize_main', 'summarize_aux'],
                'report': ['combine']}
POLICIES = ('A', 'B', 'C', 'D')


class TransientToolError(RuntimeError):
    """Explicit retryable tool error; not injected in the present study."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def declared_dependencies(scenario):
    if scenario not in ('clean', 'update', 'incomplete_lineage'):
        raise ValueError('unknown_replay_scenario')
    graph = copy.deepcopy(DEPENDENCIES)
    if scenario == 'incomplete_lineage':
        graph['combine'].remove('summarize_aux')
    return graph


def closure(graph, roots):
    reached = set(roots)
    while True:
        expanded = reached | {node for node, parents in graph.items() if reached.intersection(parents)}
        if expanded == reached:
            return [node for node in NODES if node in reached]
        reached = expanded


class ToolRuntime:
    def __init__(self, case, receipts=None):
        self.case = copy.deepcopy(case)
        self.receipts = copy.deepcopy(receipts or {})
        self.trace = []

    def execute(self, node):
        if node not in NODES:
            raise ValueError('unknown_tool_node')
        parents = DEPENDENCIES[node]
        reads = {p: digest(self.receipts[p]) for p in parents}
        family = self.case['family']
        if node.startswith('read_'):
            source = self.case['sources'][node[5:]]
            value = copy.deepcopy(source['rows'])
            reads = {f'source:{node[5:]}': digest(source)}
        elif node == 'summarize_main':
            rows = self.receipts['read_main']['value']
            if family == 'tabular':
                value = {}
                for row in rows:
                    value[row['region']] = value.get(row['region'], 0) + row['amount']
            elif family == 'retrieval':
                latest = {}
                for row in rows:
                    if row['entity'] not in latest or row['revision'] > latest[row['entity']]['revision']:
                        latest[row['entity']] = row
                value = {entity: row['value'] for entity, row in latest.items()}
            elif family == 'classification':
                value = {row['id']: row['predicted'] for row in rows}
            else:
                raise ValueError('unknown_tool_family')
        elif node == 'summarize_aux':
            rows = self.receipts['read_aux']['value']
            key, field = {'tabular': ('region', 'rate'), 'retrieval': ('entity', 'enabled'),
                          'classification': ('id', 'label')}[family]
            value = {row[key]: row[field] for row in rows}
        elif node == 'combine':
            main, aux = (self.receipts[name]['value'] for name in ('summarize_main', 'summarize_aux'))
            if family == 'tabular':
                value = {'value': sum(amount * aux[region] for region, amount in main.items()),
                         'unit': 'weighted_amount'}
            elif family == 'retrieval':
                value = {'value': sum(number for entity, number in main.items() if aux[entity]),
                         'unit': 'selected_value'}
            else:
                value = {'correct': sum(prediction == aux[item] for item, prediction in main.items()),
                         'total': len(main)}
        else:
            value = copy.deepcopy(self.receipts['combine']['value'])
        self.receipts[node] = {'ok': True, 'value': value}
        self.trace.append({'node': node, 'actual_reads': reads, 'receipt_sha256': digest(self.receipts[node])})
        return self.receipts[node]


def initial_receipts(case):
    runtime = ToolRuntime(case)
    for node in NODES:
        runtime.execute(node)
    return runtime.receipts


def public_episode(base, current, scenario, receipts):
    """Explicit whitelist: no oracle, scenario label, fault location or actual-read log."""
    graph = declared_dependencies(scenario)
    changed = [f'read_{name}' for name in ('main', 'aux')
               if current['sources'][name]['revision'] != base['sources'][name]['revision']]
    descriptions = {
        'tabular': 'Report the sum of each transaction amount times its region rate, using current sources.',
        'retrieval': 'Report the sum of latest record values for currently enabled entities.',
        'classification': 'Report correct predictions and total predictions against the current label source.'}
    return {'task': descriptions[base['family']], 'family': base['family'],
            'nodes_in_execution_order': list(NODES), 'declared_dependencies': graph,
            'source_revisions': {name: current['sources'][name]['revision'] for name in ('main', 'aux')},
            'changed_source_nodes': changed, 'cached_receipts': copy.deepcopy(receipts),
            'tool_call_budget': 12}


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) - {'actions', 'reason'}:
        raise ValueError('invalid_plan_object')
    if 'reason' in plan and (not isinstance(plan['reason'], str) or len(plan['reason']) > 2000):
        raise ValueError('invalid_plan_reason')
    actions = plan.get('actions')
    if not isinstance(actions, list) or not 1 <= len(actions) <= 13:
        raise ValueError('invalid_plan_actions')
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ValueError('invalid_plan_action')
        if index == len(actions) - 1:
            if action not in ({'op': 'emit'}, {'op': 'refuse'}):
                raise ValueError('missing_terminal_action')
        elif set(action) != {'op', 'node'} or action['op'] != 'rerun' or action['node'] not in NODES:
            raise ValueError('invalid_tool_action')
    return copy.deepcopy(actions)


def replay(policy, current, public, plan, *, tool_budget=12):
    """Matched policies consume the same public observation and cached model plan.

    C/D add required work to requested nodes, deduplicate and execute in the
    fixed tool order. Model-requested work is never silently removed. A/B keep
    model order. In this study there are no transient error injections, so B is
    an explicit negative control for error-only retry on silent changes.
    """
    if policy not in POLICIES or type(tool_budget) is not int or tool_budget < 0:
        raise ValueError('invalid_policy_or_budget')
    started = time.perf_counter()
    runtime = ToolRuntime(current, public['cached_receipts'])
    result = {'policy': policy, 'status': 'refused', 'artifact': None, 'trace': [], 'tool_calls': 0,
              'public_input_sha256': digest(public), 'plan_sha256': digest(plan)}
    try:
        actions = validate_plan(plan)
    except ValueError as error:
        result['reason'] = str(error)
        result['duration_seconds'] = time.perf_counter() - started
        return result
    if actions[-1]['op'] == 'refuse':
        result['reason'] = 'model_refusal'
        result['duration_seconds'] = time.perf_counter() - started
        return result
    requested = [action['node'] for action in actions[:-1]]
    nodes = requested
    changed = public['changed_source_nodes']
    if policy == 'C' and changed:
        nodes = list(NODES)
    elif policy in ('C', 'D'):
        mandatory = closure(public['declared_dependencies'], changed) if policy == 'D' else []
        nodes = [node for node in NODES if node in set(requested + mandatory)]
    error = None
    for node in nodes:
        for attempt in range(2 if policy in ('B', 'C', 'D') else 1):
            if result['tool_calls'] >= tool_budget:
                error = 'tool_budget_exhausted'
                break
            result['tool_calls'] += 1
            try:
                runtime.execute(node)
                error = None
                break
            except (TransientToolError, KeyError, TypeError, ValueError) as failure:
                error = 'tool_error:' + type(failure).__name__
                runtime.trace.append({'node': node, 'error': type(failure).__name__, 'attempt': attempt + 1})
                if not isinstance(failure, TransientToolError):
                    break
        if error:
            break
    result.update(trace=runtime.trace, duration_seconds=time.perf_counter() - started)
    if error:
        result['reason'] = error
    else:
        result.update(status='completed', artifact=copy.deepcopy(runtime.receipts['report']['value']))
    return result
