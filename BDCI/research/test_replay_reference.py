"""Hand-calculated reference cases and strict scoring boundary checks."""
from copy import deepcopy
import json
import unittest

from replay_cases import make_cases, make_scenario
from replay_reference import reference, score


def fixture(family, main, aux):
    return {'case_id': 'manual', 'family': family, 'sources': {
        'main': {'revision': 1, 'rows': main}, 'aux': {'revision': 1, 'rows': aux}}}


class ReplayReferenceTests(unittest.TestCase):
    def test_family_cases_have_distinct_actual_source_content(self):
        cases = make_cases()
        for family in ('tabular', 'retrieval', 'classification'):
            content = [json.dumps(case['sources'], sort_keys=True)
                       for case in cases if case['family'] == family]
            self.assertEqual(len(content), 2)
            self.assertEqual(len(set(content)), 2, family)

    def test_hand_calculated_tabular(self):
        case = fixture('tabular', [{'region': 'x', 'amount': 3}, {'region': 'x', 'amount': -1},
                                    {'region': 'y', 'amount': 4}],
                       [{'region': 'x', 'rate': 2}, {'region': 'y', 'rate': 5}])
        self.assertEqual(reference(case), {'value': 24, 'unit': 'weighted_amount'})

    def test_hand_calculated_latest_enabled_retrieval(self):
        case = fixture('retrieval', [{'entity': 'a', 'revision': 3, 'value': 8},
                                     {'entity': 'a', 'revision': 1, 'value': 100},
                                     {'entity': 'b', 'revision': 9, 'value': 900}],
                       [{'entity': 'a', 'enabled': True}, {'entity': 'b', 'enabled': False}])
        self.assertEqual(reference(case), {'value': 8, 'unit': 'selected_value'})

    def test_hand_calculated_classification(self):
        case = fixture('classification', [{'id': 'a', 'predicted': 2}, {'id': 'b', 'predicted': 0}],
                       [{'id': 'b', 'label': 1}, {'id': 'a', 'label': 2}])
        self.assertEqual(reference(case), {'correct': 1, 'total': 2})

    def test_scenarios_preserve_cases_and_change_every_reference(self):
        cases = make_cases()
        self.assertEqual(len(cases), 6)
        self.assertEqual(len({case['case_id'] for case in cases}), 6)
        self.assertEqual({family: sum(c['family'] == family for c in cases)
                          for family in ('tabular', 'retrieval', 'classification')},
                         {'tabular': 2, 'retrieval': 2, 'classification': 2})
        original = deepcopy(cases)
        for case in cases:
            clean = make_scenario(case, 'clean')
            updated = make_scenario(case, 'update')
            self.assertEqual(clean, case)
            self.assertEqual(set(updated), {'case_id', 'family', 'sources'})
            self.assertEqual(updated, make_scenario(case, 'incomplete_lineage'))
            self.assertEqual(updated['sources']['aux']['revision'], 2)
            self.assertNotEqual(reference(clean), reference(updated))
            clean['sources']['main']['rows'].clear()
        self.assertEqual(cases, original)
        self.assertEqual(make_cases(), original)

    def test_refusals_are_never_correct_completions(self):
        case = make_cases()[0]
        self.assertEqual(score(reference(case), case), 'correct_completion')
        for status in ('refused', 'blocked', 'budget_exhausted', 'failed'):
            self.assertEqual(score(reference(case), case, status), 'refusal')
            self.assertEqual(score(None, case, status), 'refusal')

    def test_invalid_completed_artifacts_are_wrong(self):
        for case in make_cases():
            answer = reference(case)
            numeric = 'value' if 'value' in answer else 'correct'
            invalid = [None, [], {}, dict(answer, extra=1)]
            invalid += [dict(answer, **{numeric: value}) for value in (
                True, False, str(answer[numeric]), float(answer[numeric]),
                float('nan'), float('inf'), float('-inf'), answer[numeric] + 1)]
            if 'unit' in answer:
                invalid.append(dict(answer, unit='wrong_unit'))
            else:
                invalid.append(dict(answer, total=True))
            for artifact in invalid:
                with self.subTest(case=case['case_id'], artifact=artifact):
                    self.assertEqual(score(artifact, case), 'wrong_completion')

    def test_invalid_reference_data_is_an_experiment_error(self):
        case = make_cases()[0]
        case['sources']['main']['rows'][0]['amount'] = True
        with self.assertRaises(ValueError):
            score(None, case)
        case = fixture('retrieval', [{'entity': 'a', 'revision': 1, 'value': 1},
                                     {'entity': 'a', 'revision': 1, 'value': 2}],
                       [{'entity': 'a', 'enabled': True}])
        with self.assertRaises(ValueError):
            reference(case)
        with self.assertRaises(ValueError):
            make_scenario(make_cases()[0], 'unsupported')


if __name__ == '__main__':
    unittest.main()
