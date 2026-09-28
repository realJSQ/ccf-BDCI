"""Scientific-state integrity checks; no model, network or new experiment."""
import copy
from pathlib import Path
import tempfile
import unittest

from run_method_revision import RevisionState


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = RevisionState(Path(self.directory.name), False)

    def propose(self):
        self.state.accept('proposer', self.state.offline_response('proposer'))

    def critique(self):
        self.propose()
        self.state.accept('critic', self.state.offline_response('critic'))

    def test_state_preserves_negative_pilot_and_requires_role_order(self):
        self.assertEqual(self.state.context['previous_pilot_decision']['status'],
                         'hypothesis_not_supported_in_pilot')
        with self.assertRaisesRegex(ValueError, 'role_order'):
            self.state.accept('refiner', {})
        self.critique()
        self.state.accept('refiner', self.state.offline_response('refiner'))
        self.assertEqual(self.state.outputs['refiner']['novelty_status'], 'unestablished')

    def test_unretrieved_citation_cannot_ground_candidate(self):
        candidate = self.state.offline_response('proposer')
        candidate['candidates'][0]['source_ids'][0] = 'invented:paper'
        with self.assertRaisesRegex(ValueError, 'reference'):
            self.state.accept('proposer', candidate)
        self.assertFalse((self.state.root / 'proposer.json').exists())

    def test_critic_cannot_promote_rejected_candidate(self):
        self.propose()
        review = self.state.offline_response('critic')
        review['reviews'][0]['verdict'] = 'reject'
        with self.assertRaisesRegex(ValueError, 'rejected_or_unknown'):
            self.state.accept('critic', review)

    def test_refiner_cannot_evade_selection_or_unanswered_objection(self):
        self.critique()
        refined = self.state.offline_response('refiner')
        refined['candidate_id'] = 'C2'
        with self.assertRaisesRegex(ValueError, 'evades_critique'):
            self.state.accept('refiner', refined)
        refined['candidate_id'] = 'C1'
        refined['response_to_critique'] = []
        with self.assertRaisesRegex(ValueError, 'incomplete_critique'):
            self.state.accept('refiner', refined)

    def test_synthetic_response_unavailable_in_live_mode(self):
        live = RevisionState(self.state.root, True)
        with self.assertRaisesRegex(ValueError, 'scripted_revision_in_live_mode'):
            live.offline_response('proposer')

    def test_schema_acceptance_cannot_certify_novelty(self):
        self.critique()
        refined = self.state.offline_response('refiner')
        refined['novelty_status'] = 'proven'
        with self.assertRaisesRegex(ValueError, 'premature_revision_claim'):
            self.state.accept('refiner', refined)

    def test_protocol_needs_independent_reference_and_bounded_calls(self):
        proposed = self.state.offline_response('proposer')
        bad = copy.deepcopy(proposed)
        bad['candidates'][0]['experiment'].pop('independent_reference')
        with self.assertRaises(ValueError):
            self.state.accept('proposer', bad)
        proposed['candidates'][0]['experiment']['pilot_api_calls'] = 10000
        with self.assertRaisesRegex(ValueError, 'unsupported_revision_resources'):
            self.state.accept('proposer', proposed)


if __name__ == '__main__':
    unittest.main()
