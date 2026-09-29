"""Independent post-run reference scoring, not an execution tool or gate.

This module deliberately imports no executor, case generator, or policy. It
recomputes from current source rows with direct loops. Algorithmic separation
does not imply independent human authorship or process security isolation.
"""
from __future__ import annotations


def _rows(case):
    try:
        family = case['family']
        sources = case['sources']
        main, aux = sources['main']['rows'], sources['aux']['rows']
        if (not isinstance(main, list) or not isinstance(aux, list)
                or any(not isinstance(row, dict) for row in main + aux)):
            raise ValueError('invalid_reference_rows')
        return family, main, aux
    except (KeyError, TypeError) as error:
        raise ValueError('invalid_reference_case') from error


def _integer(value):
    if type(value) is not int:
        raise ValueError('invalid_reference_integer')
    return value


def reference(case):
    """Recompute the expected final artifact from source rows, without tools."""
    family, main, aux = _rows(case)
    try:
        if family == 'tabular':
            value = 0
            for row in main:
                matches = [other for other in aux if other['region'] == row['region']]
                if len(matches) != 1:
                    raise ValueError('ambiguous_reference_region')
                value += _integer(row['amount']) * _integer(matches[0]['rate'])
            return {'value': value, 'unit': 'weighted_amount'}
        if family == 'retrieval':
            value, entities = 0, set()
            for selector in aux:
                entity = selector['entity']
                if entity in entities or type(selector['enabled']) is not bool:
                    raise ValueError('invalid_reference_selector')
                entities.add(entity)
                newest = None
                seen_revisions = set()
                for row in main:
                    if row['entity'] != entity:
                        continue
                    revision = _integer(row['revision'])
                    _integer(row['value'])
                    if revision in seen_revisions:
                        raise ValueError('duplicate_reference_revision')
                    seen_revisions.add(revision)
                    if newest is None or revision > newest['revision']:
                        newest = row
                if newest is None:
                    raise ValueError('missing_reference_entity')
                if selector['enabled']:
                    value += newest['value']
            return {'value': value, 'unit': 'selected_value'}
        if family == 'classification':
            correct, identifiers = 0, set()
            for row in main:
                if row['id'] in identifiers:
                    raise ValueError('duplicate_reference_id')
                identifiers.add(row['id'])
                matches = [other for other in aux if other['id'] == row['id']]
                if len(matches) != 1:
                    raise ValueError('ambiguous_reference_label')
                if _integer(row['predicted']) == _integer(matches[0]['label']):
                    correct += 1
            return {'correct': correct, 'total': len(main)}
        raise ValueError('unknown_reference_family')
    except (KeyError, TypeError) as error:
        raise ValueError('invalid_reference_case') from error


def score(artifact, case, status='completed'):
    """Return one exclusive outcome; refusal never counts as successful work.

An invalid completed artifact is a wrong completion, not an exception. Broken
reference inputs raise ValueError because they invalidate the experiment.
"""
    expected = reference(case)
    if status != 'completed':
        return 'refusal'
    if not isinstance(artifact, dict) or set(artifact) != set(expected):
        return 'wrong_completion'
    for key, value in expected.items():
        if type(artifact[key]) is not type(value) or artifact[key] != value:
            return 'wrong_completion'
    return 'correct_completion'
