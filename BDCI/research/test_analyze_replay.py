import json
from pathlib import Path
import tempfile
import unittest

from analyze_replay import normalize_report_terminal, verify_saved
from run_replay_study import ReplayState


class TerminalNormalizationTests(unittest.TestCase):
    def test_only_existing_terminal_report_is_completed(self):
        raw = {'actions': [{'op': 'rerun', 'node': 'read_aux'}, {'op': 'rerun', 'node': 'report'}]}
        normalized = normalize_report_terminal(raw)
        self.assertEqual(normalized['actions'][:-1], raw['actions'])
        self.assertEqual(normalized['actions'][-1], {'op': 'emit'})
        self.assertEqual(len(raw['actions']), 2)

    def test_no_silent_semantic_repair_or_refusal_override(self):
        for actions in ([], [{'op': 'rerun', 'node': 'combine'}], [{'op': 'refuse'}],
                        [{'op': 'emit'}], [{'op': 'rerun', 'node': 'report', 'value': 99}]):
            raw = {'actions': actions}
            self.assertEqual(normalize_report_terminal(raw), raw)


class SavedReplayVerificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        state = ReplayState(self.root, False)
        for role in state.roles:
            value = state.offline_response(role)
            (self.root / f'raw_{role}.txt').write_text(json.dumps(value))
            state.accept(role, value)
        state.report()
        usage = [{'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2,
                  'event': 'usage', 'call': index + 1} for index in range(18)]
        (self.root / 'model_usage.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in usage))
        (self.root / 'model_summary.json').write_text(json.dumps(
            {'mode': 'offline_scripted', 'model_calls': 18, 'model_usage': usage, 'total_tokens': 36}))

    def test_replays_all_saved_results_without_api(self):
        _, _, episodes, results = verify_saved(self.root)
        self.assertEqual(len(episodes), 18)
        self.assertEqual(len(results), 72)

    def test_changed_raw_response_is_not_accepted_as_model_evidence(self):
        (self.root / 'raw_episode_01.txt').write_text('{"actions":[{"op":"emit"}]}')
        with self.assertRaisesRegex(ValueError, 'saved_model_plan_mismatch'):
            verify_saved(self.root)

    def test_altered_snapshot_is_rejected_before_loading_it(self):
        (self.root / 'frozen_source/research/replay_engine.py').write_text('raise RuntimeError("modified")')
        with self.assertRaisesRegex(ValueError, 'frozen_snapshot_digest_mismatch'):
            verify_saved(self.root)


if __name__ == '__main__':
    unittest.main()
