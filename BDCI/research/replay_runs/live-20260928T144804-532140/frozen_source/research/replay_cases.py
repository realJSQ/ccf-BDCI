"""Self-authored synthetic development cases; no reference answers are stored.

Six base cases are the sampling units. Their scenario variants are paired
counterfactuals, not independent model trajectories or a held-out benchmark.
"""
from __future__ import annotations

from copy import deepcopy


def make_cases():
    """Return six fresh case dictionaries: two seeds in each of three families."""
    cases = []
    for seed in (17, 29):
        offset = seed % 7
        rows_by_family = {
            'tabular': (
                [{'region': 'north', 'amount': 11 + offset},
                 {'region': 'south', 'amount': 7 + offset},
                 {'region': 'north', 'amount': 3}],
                [{'region': 'north', 'rate': 2}, {'region': 'south', 'rate': 3}]),
            'retrieval': (
                [{'entity': 'alpha', 'revision': 2, 'value': 13 + offset},
                 {'entity': 'beta', 'revision': 1, 'value': 5},
                 {'entity': 'alpha', 'revision': 1, 'value': 4},
                 {'entity': 'beta', 'revision': 3, 'value': 9 + offset}],
                [{'entity': 'alpha', 'enabled': True}, {'entity': 'beta', 'enabled': True}]),
            'classification': (
                [{'id': 'a', 'predicted': 0}, {'id': 'b', 'predicted': 1},
                 {'id': 'c', 'predicted': offset % 2}]
                + ([{'id': 'd', 'predicted': 0}] if seed == 29 else []),
                [{'id': 'a', 'label': 0}, {'id': 'b', 'label': 0},
                 {'id': 'c', 'label': offset % 2}]
                + ([{'id': 'd', 'label': 1}] if seed == 29 else [])),
        }
        for family, (main, aux) in rows_by_family.items():
            cases.append({'case_id': f'{family}-{seed}', 'family': family,
                          'sources': {'main': {'revision': 1, 'rows': main},
                                      'aux': {'revision': 1, 'rows': aux}}})
    return cases


def make_scenario(case, scenario):
    """Return a deep-copied case with current public source data.

The two update scenarios have identical data. Missing lineage is injected by
the execution harness into its declared graph, never encoded as an answer or
hidden fault label in this case dictionary.
"""
    if scenario not in ('clean', 'update', 'incomplete_lineage'):
        raise ValueError('unknown_replay_scenario')
    current = deepcopy(case)
    if scenario == 'clean':
        return current
    aux = current['sources']['aux']
    aux['revision'] = 2
    first = aux['rows'][0]
    if current['family'] == 'tabular':
        first['rate'] += 1
    elif current['family'] == 'retrieval':
        first['enabled'] = not first['enabled']
    elif current['family'] == 'classification':
        first['label'] = 1 - first['label']
    else:
        raise ValueError('unknown_replay_family')
    return current
