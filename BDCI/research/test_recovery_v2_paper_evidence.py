"""Real saved-response integration and tampering checks, with zero API calls."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from recovery_v2_paper_evidence import build_evidence

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE / 'recovery_v2_runs/live-20260929T060132-126279'


@unittest.skipUnless(ARCHIVE.is_dir(), 'requires archived recovery-v2 live evidence')
class RecoveryV2PaperEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.run = Path(self.temporary.name) / ARCHIVE.name
        self.run.mkdir()
        # Never copy private runtime/SDK logs or mutate the authoritative run.
        for path in ARCHIVE.iterdir():
            if path.is_file() and path.suffix in ('.json', '.jsonl', '.txt', '.py') and path.name != 'requests.jsonl':
                shutil.copyfile(path, self.run / path.name)
        shutil.copytree(ARCHIVE / 'frozen_source', self.run / 'frozen_source',
                        ignore=shutil.ignore_patterns('__pycache__'))

    def change_json(self, name, mutate):
        path = self.run / name
        value = json.loads(path.read_text())
        mutate(value)
        path.write_text(json.dumps(value))

    def test_complete_evidence_is_derived_and_separate_from_history(self):
        evidence = build_evidence(self.run)
        self.assertEqual(evidence['schema'], 'recovery_v2_evidence/1')
        self.assertEqual((evidence['base_instance_count'], evidence['completed_model_plans'],
                          evidence['completed_policy_replays']), (9, 36, 180))
        self.assertEqual(len(evidence['summary_by_scenario_policy']), 20)
        self.assertEqual(len(evidence['paired_base_instances']), 9)
        self.assertEqual(set(evidence['policies']), {'A', 'D', 'E', 'F', 'G'})
        metering = json.loads((self.run / 'model_summary.json').read_text())
        self.assertEqual(evidence['resource']['total_tokens'], metering['total_tokens'])
        self.assertEqual(evidence['verification']['new_api_calls'], 0)
        self.assertFalse(evidence['prior_study']['verified_by_this_adapter'])
        self.assertTrue(evidence['development_assistance']['developer_assisted_protocol'])
        self.assertNotIn('posthoc', evidence)
        self.assertIn('raw_episode_00.txt', evidence['artifact_sha256'])
        rows = json.loads((self.run / 'analysis.json').read_text())['summary_by_scenario_policy']
        for total in evidence['summary_by_policy']:
            self.assertEqual(total['tool_calls'], sum(r['tool_calls'] for r in rows if r['policy'] == total['policy']))

    def test_changed_raw_response_rejected(self):
        (self.run / 'raw_episode_00.txt').write_text('{"actions": [{"op": "refuse"}]}')
        with self.assertRaisesRegex(ValueError, 'frozen_study_verification_failed'):
            build_evidence(self.run)

    def test_missing_g_rejected(self):
        self.change_json('results_episode_00.json', lambda rows: rows.pop())
        with self.assertRaisesRegex(ValueError, 'frozen_study_verification_failed'):
            build_evidence(self.run)

    def test_missing_scenario_rejected(self):
        self.change_json('episodes.json', lambda episodes: episodes.pop('episode_00'))
        with self.assertRaisesRegex(ValueError, 'frozen_study_verification_failed'):
            build_evidence(self.run)

    def test_missing_pair_rejected(self):
        self.change_json('analysis.json', lambda analysis: analysis['paired_base_instances'].pop())
        with self.assertRaisesRegex(ValueError, 'frozen_study_verification_failed'):
            build_evidence(self.run)

    def test_changed_pair_rejected(self):
        self.change_json('analysis.json', lambda analysis: analysis['paired_base_instances'][0].update(E_minus_A_correct=99))
        with self.assertRaisesRegex(ValueError, 'frozen_study_verification_failed'):
            build_evidence(self.run)

    def test_offline_rejected(self):
        self.change_json('pre_registration.json', lambda registration: registration.update(mode='offline_scripted'))
        with self.assertRaisesRegex(ValueError, 'completed_live_heldout_study_required'):
            build_evidence(self.run)

    def test_changed_frozen_verifier_rejected_before_execution(self):
        (self.run / 'frozen_source/research/run_recovery_v2.py').write_text('raise RuntimeError("must not execute")')
        with self.assertRaisesRegex(ValueError, 'snapshot_hash_mismatch'):
            build_evidence(self.run)


if __name__ == '__main__':
    unittest.main()
