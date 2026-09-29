"""Generator contracts; held-out cases receive structural checks only."""
from copy import deepcopy
import json
import unittest

from recovery_v2_cases import FAMILIES, SCENARIOS, make_cases, make_scenario
from replay_reference import reference


class RecoveryV2CaseTests(unittest.TestCase):
    def test_split_structure_and_source_schema(self):
        expected = {'development': {(1, 1), (2, 1), (1, 2)},
                    'heldout': {(2, 2), (3, 2), (2, 3)}}
        identities, seeds = set(), set()
        for split, layouts in expected.items():
            cases = make_cases(split)
            self.assertEqual(len(cases), 9)
            self.assertEqual(cases, make_cases(split))
            for family in FAMILIES:
                selected = [case for case in cases if case['family'] == family]
                self.assertEqual(len(selected), 3)
                self.assertEqual(len({json.dumps(case['sources'], sort_keys=True)
                                      for case in selected}), 3)
                self.assertEqual({(case['topology']['main_shards'], case['topology']['aux_shards'])
                                  for case in selected}, layouts)
            for case in cases:
                self.assertEqual(case['split'], split)
                self.assertNotIn(case['case_id'], identities)
                self.assertNotIn(case['seed'], seeds)
                identities.add(case['case_id'])
                seeds.add(case['seed'])
                family = case['family']
                key = {'tabular': 'region', 'retrieval': 'entity', 'classification': 'id'}[family]
                main, aux = (case['sources'][source]['rows'] for source in ('main', 'aux'))
                expected_keys = {f'k{index:02d}' for index in range(8)}
                self.assertEqual({row[key] for row in main}, expected_keys)
                self.assertEqual({row[key] for row in aux}, expected_keys)
                self.assertEqual(len(aux), 8)
                for source in case['sources'].values():
                    self.assertEqual(source['revision'], 1)
                if family != 'classification':
                    self.assertEqual(len(main), 24)
                    for identifier in expected_keys:
                        self.assertEqual(sum(row[key] == identifier for row in main), 3)
                if family == 'retrieval':
                    for identifier in expected_keys:
                        self.assertEqual([row['revision'] for row in main if row[key] == identifier], [2, 1, 3])
                    self.assertTrue(all(type(row['enabled']) is bool for row in aux))

    def test_development_updates_change_reference_and_preserve_inputs(self):
        cases = make_cases('development')
        original = deepcopy(cases)
        for case in cases:
            with self.subTest(case=case['case_id']):
                clean = make_scenario(case, 'clean')
                aux = make_scenario(case, 'aux_update')
                joint = make_scenario(case, 'joint_update')
                self.assertEqual(clean, case)
                self.assertEqual(aux, make_scenario(case, 'incomplete_lineage'))
                self.assertEqual(aux['sources']['main'], case['sources']['main'])
                self.assertEqual(aux['sources']['aux']['revision'], 2)
                self.assertEqual(joint['sources']['aux'], aux['sources']['aux'])
                self.assertEqual(joint['sources']['main']['revision'], 2)
                self.assertNotEqual(reference(clean), reference(aux))
                self.assertNotEqual(reference(aux), reference(joint))
                main_only = deepcopy(joint)
                main_only['sources']['aux'] = deepcopy(case['sources']['aux'])
                self.assertNotEqual(reference(clean), reference(main_only))
                clean['sources']['main']['rows'].clear()
        self.assertEqual(cases, original)
        self.assertEqual(make_cases('development'), original)

    def test_fresh_generation_and_scenario_objects(self):
        first = make_cases('development')
        expected = deepcopy(first)
        for scenario in SCENARIOS:
            changed = make_scenario(first[0], scenario)
            changed['topology']['main_shards'] = 99
            changed['sources']['aux']['rows'].clear()
        self.assertEqual(first, expected)
        first[0]['sources']['main']['rows'].clear()
        self.assertEqual(make_cases('development'), expected)

    def test_invalid_identifiers_fail(self):
        for split in ('dev', 'test', ''):
            with self.assertRaisesRegex(ValueError, 'unknown_recovery_split'):
                make_cases(split)
        case = make_cases('development')[0]
        with self.assertRaisesRegex(ValueError, 'unknown_recovery_scenario'):
            make_scenario(case, 'update')
        case['family'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'unknown_recovery_family'):
            make_scenario(case, 'clean')


if __name__ == '__main__':
    unittest.main()
