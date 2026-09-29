from pathlib import Path
import copy
import json
import shutil
from unittest.mock import patch
import tempfile
import unittest

from run_replay_paper import ReplayPaperState, select_study_run, DEFAULT_RUN, HERE


class ReplayPaperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = ReplayPaperState(Path(self.temp.name), False)

    def test_verified_evidence_keeps_strict_and_posthoc_separate(self):
        e = self.state.evidence
        for policy in 'ABCD':
            self.assertEqual(sum(r['correct_completion'] for r in e['strict']['summary_by_scenario_policy'] if r['policy'] == policy), 10)
            self.assertEqual(sum(r['correct_completion'] for r in e['posthoc']['summary_by_scenario_policy'] if r['policy'] == policy), 18)
        self.assertEqual(e['strict']['noncompletion_reasons']['missing_terminal_action'], 8)
        self.assertEqual(e['posthoc']['model_calls'], 0)

    def test_relocated_study_is_explicit_and_content_bound(self):
        relocated = Path(self.temp.name) / 'relocated-study'
        shutil.copytree(DEFAULT_RUN, relocated)
        output = Path(self.temp.name) / 'new-paper'
        output.mkdir()
        saved = json.loads((self.state.root / 'input_provenance.json').read_text())
        state = ReplayPaperState(output, False, select_study_run(relocated), saved)
        self.assertEqual(state.evidence, self.state.evidence)
        actual = json.loads((output / 'input_provenance.json').read_text())
        self.assertEqual(actual['run'], str(relocated))
        self.assertIsNone(actual['study_run_relative'])

    def test_resume_missing_input_never_falls_back_to_historical_run(self):
        with self.assertRaisesRegex(ValueError, 'study_missing'):
            select_study_run(saved={'run': str(Path(self.temp.name) / 'missing')})
        self.assertEqual(select_study_run(saved={'study_run_relative': str(DEFAULT_RUN.relative_to(HERE))}), DEFAULT_RUN)
        with self.assertRaisesRegex(ValueError, 'unsafe_saved_study_path'):
            select_study_run(saved={'study_run_relative': '../outside'})

    def test_changed_input_rejected_before_saved_artifacts_are_overwritten(self):
        saved = json.loads((self.state.root / 'input_provenance.json').read_text())
        before = {p.name: p.read_bytes() for p in self.state.root.iterdir() if p.is_file()}
        changed = copy.deepcopy(self.state.evidence)
        changed['resource']['total_tokens'] += 1
        with patch('run_replay_paper.build_evidence', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'paper_input_changed'):
                ReplayPaperState(self.state.root, False, expected_provenance=saved)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.state.root.iterdir() if p.is_file()})

    def test_review_cannot_target_old_draft(self):
        self.state.accept('writer', self.state.offline_response('writer'))
        review = self.state.offline_response('reviewer')
        review['draft_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'review_target_mismatch'):
            self.state.accept('reviewer', review)

    def test_issues_must_quote_current_text(self):
        self.state.accept('writer', self.state.offline_response('writer'))
        review = self.state.offline_response('reviewer')
        review.update(verdict='revise', issues=[{'severity': 'major', 'section_id': 'abstract', 'message': 'Overclaim'}],
                      issue_quotes=['We prove superiority'])
        with self.assertRaisesRegex(ValueError, 'ungrounded_review'):
            self.state.accept('reviewer', review)

    def test_order_and_live_fixture_boundary(self):
        with self.assertRaisesRegex(ValueError, 'paper_role_order'):
            self.state.accept('reviser', {})
        self.state.live = True
        with self.assertRaisesRegex(ValueError, 'scripted_paper_in_live_mode'):
            self.state.offline_response('writer')

    def test_draft_exception_does_not_relax_final_limit(self):
        paper = self.state.offline_response('writer')
        paper['abstract'] = 'word ' * 1530
        self.state.accept('writer', paper)
        self.state.accept('reviewer', self.state.offline_response('reviewer'))
        self.state.accept('reviser', {**paper, 'response_to_review': []})
        from paper_contracts import validate_paper
        with self.assertRaisesRegex(ValueError, 'paper_word_limit'):
            validate_paper(self.state.outputs['reviser'], self.state.sources)


if __name__ == '__main__':
    unittest.main()
