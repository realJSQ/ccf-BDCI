"""Bounded, code-free dependency/cache examples; not a scientific correctness oracle."""
from __future__ import annotations

FIELDS = {
    'nodes', 'actual_dependencies', 'declared_dependencies', 'changed_sources',
    'cached_source_versions', 'current_source_versions', 'actions',
    'claimed_closure', 'tool_budget',
}


def _ids(value, allowed, name):
    if type(value) is not list or any(type(x) is not str for x in value):
        raise ValueError(f'{name} must be a list of node ids')
    if len(value) != len(set(value)) or not set(value) <= allowed:
        raise ValueError(f'{name} contains duplicate or unknown ids')
    return value


def analyze_graph_example(spec):
    """Validate a strict JSON object and simulate explicit cached reads.

    Invalid contracts raise ValueError. Incorrect closure claims are diagnostics,
    independently of execution. Each rerun consumes one tool attempt, including
    duplicates; emit consumes none and never reruns a dependency. Refusal and
    budget exhaustion are noncompletion. Source vectors retain *all* versions
    read along converging branches, so a fresh branch cannot hide a stale one.
    ``provenance_current`` says nothing about computed values or scientific merit.
    """
    if type(spec) is not dict or set(spec) != FIELDS:
        raise ValueError('graph example must contain exactly the supported fields')
    nodes = spec['nodes']
    if type(nodes) is not list or not 1 <= len(nodes) <= 64:
        raise ValueError('nodes must contain 1..64 topological ids')
    if any(type(n) is not str or not n or len(n) > 128 for n in nodes):
        raise ValueError('node ids must be nonempty strings of at most 128 characters')
    _ids(nodes, set(nodes), 'nodes')
    positions = {n: i for i, n in enumerate(nodes)}
    graphs = []
    for name in ('actual_dependencies', 'declared_dependencies'):
        graph = spec[name]
        if type(graph) is not dict or set(graph) != set(nodes):
            raise ValueError(f'{name} must map every node exactly once')
        for node, parents in graph.items():
            _ids(parents, set(nodes), f'{name}.{node}')
            if any(positions[p] >= positions[node] for p in parents):
                raise ValueError(f'{name} must be an acyclic graph in nodes topological order')
        graphs.append(graph)
    actual, declared = graphs
    roots = {n for n in nodes if not actual[n]}
    # A missing declared edge is permitted; an actual source cannot acquire parents.
    if any(declared[n] for n in roots):
        raise ValueError('actual source nodes cannot have declared parents')
    for name in ('cached_source_versions', 'current_source_versions'):
        versions = spec[name]
        if type(versions) is not dict or set(versions) != roots:
            raise ValueError(f'{name} must map precisely the actual source nodes')
        if any(type(v) is not int or v < 0 for v in versions.values()):
            raise ValueError(f'{name} versions must be nonnegative integers')
    old, current = spec['cached_source_versions'], spec['current_source_versions']
    changed = _ids(spec['changed_sources'], roots, 'changed_sources')
    if set(changed) != {r for r in roots if old[r] != current[r]}:
        raise ValueError('changed_sources must exactly match source version differences')
    claimed = _ids(spec['claimed_closure'], set(nodes), 'claimed_closure')
    budget = spec['tool_budget']
    if type(budget) is not int or not 0 <= budget <= 128:
        raise ValueError('tool_budget must be an integer in 0..128')
    actions = spec['actions']
    if type(actions) is not list or not 1 <= len(actions) <= 128:
        raise ValueError('actions must contain 1..128 operations with one terminal action')
    for index, action in enumerate(actions):
        if type(action) is not dict:
            raise ValueError('each action must be an object')
        op = action.get('op')
        if op not in ('rerun', 'emit', 'refuse'):
            raise ValueError('only rerun, emit and refuse are supported')
        keys = {'op'} if op == 'refuse' else {'op', 'node'}
        if set(action) != keys:
            raise ValueError('action contains missing or unsupported fields')
        if op != 'refuse' and (type(action['node']) is not str or action['node'] not in positions):
            raise ValueError('action references unknown node')
        if (index == len(actions) - 1) != (op in ('emit', 'refuse')):
            raise ValueError('actions must end in exactly one emit or refuse')
    closure = set(changed)
    for node in nodes:
        if any(p in closure for p in declared[node]):
            closure.add(node)
    diagnostics = []
    if set(claimed) != closure:
        diagnostics.append({'code': 'incorrect_claimed_closure',
                            'missing_nodes': [n for n in nodes if n in closure - set(claimed)],
                            'extra_nodes': [n for n in nodes if n in set(claimed) - closure]})
    cache = {}
    source_dependencies = {}

    def merge(node):
        merged = {}
        for parent in actual[node]:
            for source, versions in cache[parent].items():
                merged.setdefault(source, set()).update(versions)
        return merged

    for node in nodes:
        cache[node] = {node: {old[node]}} if node in roots else merge(node)
        source_dependencies[node] = set(cache[node])
    result = {
        'declared_closure': [n for n in nodes if n in closure],
        'closure_claim_valid': not diagnostics, 'diagnostics': diagnostics,
        'completed': False, 'termination': None, 'tool_attempts': 0,
        'emitted_node': None, 'provenance_current': False, 'stale_sources': [],
        'output_source_versions': {}, 'expected_source_versions': {},
        'scope': 'source_version_provenance_only_not_numeric_or_scientific_correctness',
    }
    for action in actions:
        if action['op'] == 'refuse':
            result['termination'] = 'refused'
            break
        node = action['node']
        if action['op'] == 'rerun':
            if result['tool_attempts'] >= budget:
                result['termination'] = 'tool_budget_exhausted'
                break
            result['tool_attempts'] += 1
            cache[node] = {node: {current[node]}} if node in roots else merge(node)
        else:
            stale = sorted(r for r in source_dependencies[node] if cache[node][r] != {current[r]})
            result.update(completed=True, termination='emitted', emitted_node=node,
                          provenance_current=not stale, stale_sources=stale,
                          output_source_versions={r: sorted(v) for r, v in sorted(cache[node].items())},
                          expected_source_versions={r: current[r] for r in sorted(source_dependencies[node])})
    return result
