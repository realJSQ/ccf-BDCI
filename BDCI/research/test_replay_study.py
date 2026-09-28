from pathlib import Path
import tempfile
import unittest

from run_replay_study import ReplayState


class ReplayStudyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = ReplayState(Path(temporary.name), False)

    def test_all_scripted_paths_preserve_denominators_and_scientific_boundary(self):
        for role in self.state.roles:
            prompt = self.state.prompt(role)
            self.assertNotIn('incomplete_lineage', prompt)
            self.assertNotIn('oracle', prompt)
            self.state.accept(role, self.state.offline_response(role))
        report = self.state.report()
        self.assertEqual(report['completed_policy_replays'], 72)
        self.assertEqual(report['base_instance_count'], 6)
        self.assertFalse(report['descriptive_development_results_only'])
        self.assertFalse(report['formal_study_ready'])
        self.assertEqual(len(report['paired_full_minus_selective']), 18)
        self.assertTrue(all(row['correct_completion'] == 6 for row in report['summary_by_scenario_policy']))

    def test_invalid_model_plan_stays_in_denominator(self):
        self.state.accept(self.state.roles[0], {'actions': [{'op': 'invent_answer', 'value': 1}]})
        self.assertEqual(len(self.state.results), 4)
        self.assertTrue(all(r['outcome'] == 'refusal' for r in self.state.results))

    def test_frozen_dataset_change_stops_before_prompt_or_policy_execution(self):
        (self.state.root / 'base_cases.json').write_text('[]')
        with self.assertRaisesRegex(ValueError, 'changed_after_freeze'):
            self.state.prompt(self.state.roles[0])
        with self.assertRaisesRegex(ValueError, 'changed_after_freeze'):
            self.state.accept(self.state.roles[0], {'actions': [{'op': 'emit'}]})


if __name__ == '__main__':
    unittest.main()
