import json
from pathlib import Path
import tempfile
import unittest

from run_recovery_v2 import RecoveryState, verify_saved


class RecoveryStudyTests(unittest.TestCase):
    def test_malformed_model_response_is_recorded_and_does_not_poison_g(self):
        with tempfile.TemporaryDirectory() as directory:
            state = RecoveryState(Path(directory), False)
            self.assertEqual(state.registration['split'], 'development')
            self.assertEqual(len(state.roles), 36)
            self.assertFalse(state.registration['external_benchmark'])
            state.accept(state.roles[0], state.decode_response('not json'))
            rows = state.results
            self.assertEqual([r['outcome'] for r in rows[:4]], ['refusal'] * 4)
            self.assertEqual(rows[-1]['outcome'], 'correct_completion')
            self.assertEqual(state.report()['status'], 'partial')

    def test_decoder_does_not_impose_old_30000_character_limit(self):
        valid = {'actions': [{'op': 'emit'}], 'reason': 'x' * 50000}
        self.assertEqual(RecoveryState.decode_response(json.dumps(valid)), valid)
        for raw in ('{"actions":[],"actions":[]}', '{"reason":NaN}', '[]', None):
            self.assertIn('invalid_model_response', RecoveryState.decode_response(raw))

    def test_offline_complete_and_source_freeze_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = RecoveryState(root, False)
            for role in state.roles:
                state.accept(role, state.offline_response(role))
            report = state.report()
            self.assertEqual(report['status'], 'completed')
            self.assertEqual(len(state.results), 180)
            self.assertEqual(len(report['paired_base_instances']), 9)
            self.assertEqual(sum(r['refusal'] + r['wrong_completion'] for r in report['summary_by_scenario_policy']), 0)
            self.assertTrue(all(p['E_minus_A_correct'] == 0 for p in report['paired_base_instances']))
            (root / 'frozen_source/research/recovery_v2_engine.py').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'snapshot_changed'):
                state.prompt(state.roles[0])

    def test_saved_verifier_binds_prompt_raw_plan_and_usage_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = RecoveryState(root, False)
            for role in state.roles:
                value = state.offline_response(role)
                (root / f'prompt_{role}.txt').write_text(state.prompt(role))
                (root / f'raw_{role}.txt').write_text(json.dumps(value))
                state.accept(role, value)
            state.report()
            usage = [{'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2,
                      'event': 'usage', 'call': i + 1, 'run_id': root.name, 'finish_reason': 'stop'}
                     for i in range(len(state.roles))]

            def save_usage():
                (root / 'model_usage.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in usage))
                (root / 'model_summary.json').write_text(json.dumps({'mode': 'offline_scripted',
                    'status': 'completed', 'model_calls': 36, 'total_tokens': 72, 'model_usage': usage}))

            save_usage()
            self.assertEqual(verify_saved(root)['policy_replays'], 180)
            prompt = root / 'prompt_episode_00.txt'
            original = prompt.read_text()
            prompt.write_text(original + ' changed')
            with self.assertRaisesRegex(ValueError, 'prompt_binding_mismatch'):
                verify_saved(root)
            prompt.write_text(original)
            for field, invalid in (('call', 2), ('run_id', 'other'), ('input_tokens', -1),
                                   ('finish_reason', 'length'), ('total_tokens', 3)):
                previous = usage[0][field]
                usage[0][field] = invalid
                save_usage()
                with self.assertRaisesRegex(ValueError, 'invalid_completed_study_usage'):
                    verify_saved(root)
                usage[0][field] = previous


if __name__ == '__main__':
    unittest.main()
