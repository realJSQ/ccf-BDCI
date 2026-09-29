"""Developer-authored prospective recovery fixtures, not new Agent observations.

Nine cases per split: three task families crossed with three shard layouts.
Development layouts are (1,1), (2,1), (1,2); held-out layouts are (2,2),
(3,2), (2,3). Seeds are explicit arithmetic identifiers, not random sampling:
1009 + split_offset + 101*family_index + 17*layout_index, with split offsets
0 and 10000. Each case has eight keys k00..k07. Tabular uses three positive
transactions per key; retrieval uses revisions 2,1,3 (deliberately unsorted);
classification has one prediction and initially matching label per key.

The source rows retain replay_reference's existing schema. Partitioning is
performed by the executor, not here. Generating held-out structures does not
constitute execution, external validation, or independently authored data.
"""
from __future__ import annotations

from copy import deepcopy


FAMILIES = ('tabular', 'retrieval', 'classification')
TOPOLOGIES = {
    'development': ((1, 1), (2, 1), (1, 2)),
    'heldout': ((2, 2), (3, 2), (2, 3)),
}
SCENARIOS = ('clean', 'aux_update', 'joint_update', 'incomplete_lineage')


def make_cases(split):
    """Return fresh cases; no oracle, executor, or policy is invoked."""
    if split not in TOPOLOGIES:
        raise ValueError('unknown_recovery_split')
    cases = []
    for family_index, family in enumerate(FAMILIES):
        for layout_index, (main_shards, aux_shards) in enumerate(TOPOLOGIES[split]):
            seed = 1009 + (10000 if split == 'heldout' else 0) + 101 * family_index + 17 * layout_index
            main, aux = [], []
            for index in range(8):
                key = f'k{index:02d}'
                if family == 'tabular':
                    main.extend({'region': key, 'amount': 1 + (seed + 7 * index + 3 * row) % 23}
                                for row in range(3))
                    aux.append({'region': key, 'rate': 1 + (seed + index) % 5})
                elif family == 'retrieval':
                    main.extend({'entity': key, 'revision': revision,
                                 'value': 1 + (seed + 11 * index + 5 * revision) % 37}
                                for revision in (2, 1, 3))
                    # k00 and k01 are enabled, ensuring both update types matter.
                    aux.append({'entity': key, 'enabled': index % 3 != 2})
                else:
                    predicted = (seed >> index) & 1
                    main.append({'id': key, 'predicted': predicted})
                    aux.append({'id': key, 'label': predicted})
            cases.append({
                'case_id': f'recovery-v2-{split}-{family}-m{main_shards}-a{aux_shards}-{seed}',
                'family': family, 'split': split, 'seed': seed,
                'topology': {'main_shards': main_shards, 'aux_shards': aux_shards},
                'sources': {'main': {'revision': 1, 'rows': main},
                            'aux': {'revision': 1, 'rows': aux}},
            })
    return cases


def make_scenario(case, scenario):
    """Apply fixed source interventions without executing or evaluating a task.

Auxiliary updates affect k00: increase its rate, toggle its enabled flag,
or flip its label. Joint updates additionally affect k01: add seven to one
transaction/the latest retrieval value, or flip its prediction. Source-level
revisions increase only for changed sources. Missing lineage has exactly the
aux_update data; graph damage is exclusively the executor's responsibility.
"""
    if scenario not in SCENARIOS:
        raise ValueError('unknown_recovery_scenario')
    family = case['family']
    if family not in FAMILIES:
        raise ValueError('unknown_recovery_family')
    current = deepcopy(case)
    if scenario == 'clean':
        return current
    aux = current['sources']['aux']
    aux['revision'] += 1
    key_field = {'tabular': 'region', 'retrieval': 'entity', 'classification': 'id'}[family]
    auxiliary = next(row for row in aux['rows'] if row[key_field] == 'k00')
    if family == 'tabular':
        auxiliary['rate'] += 1
    elif family == 'retrieval':
        auxiliary['enabled'] = not auxiliary['enabled']
    else:
        auxiliary['label'] = 1 - auxiliary['label']
    if scenario == 'joint_update':
        main = current['sources']['main']
        main['revision'] += 1
        candidates = [row for row in main['rows'] if row[key_field] == 'k01']
        if family == 'tabular':
            candidates[0]['amount'] += 7
        elif family == 'retrieval':
            max(candidates, key=lambda row: row['revision'])['value'] += 7
        else:
            candidates[0]['predicted'] = 1 - candidates[0]['predicted']
    return current
