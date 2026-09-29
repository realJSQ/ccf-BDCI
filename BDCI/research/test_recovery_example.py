import copy
import json
from pathlib import Path
import unittest

from check_recovery_example import check_example

HERE = Path(__file__).resolve().parent / 'protocol_examples'


class RecoveryExampleTests(unittest.TestCase):
    def fixture(self, name):
        return json.loads((HERE / (name + '.json')).read_text())

    def test_prior_error_types_are_detected_without_model_calls(self):
        result = check_example(self.fixture('inconsistent'))
        self.assertFalse(result['claims_consistent'])
        codes = {issue['code'] for issue in result['issues']}
        self.assertEqual(codes, {'experiment_request_budget', 'claimed_changed_sources_mismatch',
                                'claimed_closure_mismatch', 'policy_prediction_mismatch'})
        self.assertEqual(result['policy_checks']['A']['outcome'], 'wrong_completion')
        self.assertEqual(result['policy_checks']['C']['outcome'], 'correct_completion')
        self.assertIn('report', result['declared_closure'])
        self.assertEqual(result['new_model_calls'], 0)

    def test_consistent_example_does_not_certify_science_or_execution(self):
        result = check_example(self.fixture('consistent'))
        self.assertTrue(result['claims_consistent'])
        self.assertFalse(result['scientific_certification'])
        self.assertFalse(result['experiment_execution_enabled'])
        self.assertEqual(result['policy_checks']['A']['tool_calls'], 4)
        self.assertEqual(result['policy_checks']['C']['tool_calls'], 6)

    def test_missing_emit_and_refusal_are_not_correct_completion(self):
        for actions in ([{'op': 'rerun', 'node': 'report'}], [{'op': 'refuse'}]):
            spec = self.fixture('consistent')
            spec['plan']['actions'] = actions
            result = check_example(spec)
            self.assertFalse(result['claims_consistent'])
            for row in result['policy_checks'].values():
                self.assertEqual(row['outcome'], 'refusal')
                self.assertEqual(row['tool_calls'], 0)

    def test_unsupported_structures_and_false_integer_counts_rejected(self):
        for field, value in [('case_id', 'new-independent-task'), ('resources', {'base_instances': True,
                'scenarios': 3, 'prompt_conditions': 2, 'planned_api_calls': 6})]:
            spec = self.fixture('consistent');spec[field] = value
            with self.assertRaises(ValueError):check_example(spec)
        spec = self.fixture('consistent');del spec['predictions']['C']
        with self.assertRaisesRegex(ValueError, 'incomplete_policy'):check_example(spec)


if __name__ == '__main__':
    unittest.main()
