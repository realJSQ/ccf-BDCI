"""Protect protocol rejection and resource boundaries; no API calls."""
from pathlib import Path
import tempfile
import unittest

from run_protocol_design import ProtocolState


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = ProtocolState(Path(temporary.name), False)

    def test_decline_is_preserved_and_cannot_be_promoted(self):
        self.state.accept('designer', self.state.offline_response('designer'))
        response = self.state.offline_response('auditor')
        response.update(verdict='implement_development', resource_arithmetic_checked=True)
        with self.assertRaisesRegex(ValueError, 'declined_protocol_promoted'):
            self.state.accept('auditor', response)
        self.assertFalse((self.state.root / 'auditor.json').exists())
        self.state.accept('auditor', self.state.offline_response('auditor'))

    def test_unknown_source_and_premature_readiness_fail(self):
        self.state.accept('designer', self.state.offline_response('designer'))
        response = self.state.offline_response('auditor')
        response['source_ids'][0] = 'invented-source'
        with self.assertRaisesRegex(ValueError, 'unknown_protocol_reference'):
            self.state.accept('auditor', response)
        response = self.state.offline_response('auditor')
        response['formal_study_ready'] = True
        with self.assertRaisesRegex(ValueError, 'premature_formal_readiness'):
            self.state.accept('auditor', response)

    def test_cannot_skip_designer_or_use_scripted_live_output(self):
        with self.assertRaisesRegex(ValueError, 'role_order'):
            self.state.accept('auditor', self.state.offline_response('auditor'))
        live = ProtocolState(self.state.root, True)
        with self.assertRaisesRegex(ValueError, 'scripted_protocol_in_live_mode'):
            live.offline_response('designer')

    def test_review_excludes_superseded_proposal_and_binds_target(self):
        self.state.context['proposal']['stale_canary'] = 'NEVER_REVIEW_OLD_PROPOSAL'
        self.state.accept('designer', self.state.offline_response('designer'))
        self.assertNotIn('NEVER_REVIEW_OLD_PROPOSAL', self.state.prompt('auditor'))
        response = self.state.offline_response('auditor')
        response['review_target_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'review_target_mismatch'):
            self.state.accept('auditor', response)

    def test_blocker_cannot_quote_nonexistent_target_text(self):
        self.state.accept('designer', self.state.offline_response('designer'))
        response = self.state.offline_response('auditor')
        response['blocking_issues'] = ['Invented blocker']
        response['blocking_evidence'] = [{'field': 'reason', 'quote': 'constant-label evaluator',
                                           'explanation': 'This was only in a superseded proposal.'}]
        with self.assertRaisesRegex(ValueError, 'ungrounded_review_evidence'):
            self.state.accept('auditor', response)

    def test_resume_only_auditor_keeps_saved_design(self):
        design = self.state.offline_response('designer')
        self.state.accept('designer', design)
        self.state.roles = ('auditor',)
        self.state.accept('auditor', self.state.offline_response('auditor'))
        self.assertEqual(self.state.outputs['designer'], design)


if __name__ == '__main__':
    unittest.main()
