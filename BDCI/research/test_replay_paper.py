from pathlib import Path
import tempfile
import unittest

from run_replay_paper import ReplayPaperState


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
