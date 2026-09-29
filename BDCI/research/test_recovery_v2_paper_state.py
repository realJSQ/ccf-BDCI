from pathlib import Path
import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from run_replay_paper import HERE, ReplayPaperState
from study_adapter import get_adapter
from paper_contracts import validate_paper

RUN = HERE / 'recovery_v2_runs/live-20260929T060132-126279'


class RecoveryPaperStateTests(unittest.TestCase):
    def test_new_profile_preserves_long_response_and_binds_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = ReplayPaperState(Path(temporary), False, RUN, study_kind='recovery_v2')
            paper = state.offline_response('writer')
            paper['abstract'] = 'Complete scientific explanation. ' * 2000
            decoded = state.decode_response(json.dumps(paper))
            self.assertEqual(decoded, paper)
            state.accept('writer', decoded)
            with self.assertRaises(ValueError):
                validate_paper(paper, state.sources)
            review = state.offline_response('reviewer')
            review['evidence_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'review_target_mismatch'):
                state.accept('reviewer', review)
            state.accept('reviewer', state.offline_response('reviewer'))
            state.accept('reviser', state.offline_response('reviser'))
            self.assertEqual(state.outputs['reviser']['abstract'], paper['abstract'])

    def test_saved_kind_and_profile_cannot_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = ReplayPaperState(root, False, RUN, study_kind='recovery_v2')
            saved = json.loads((root / 'input_provenance.json').read_text())
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with self.assertRaisesRegex(ValueError, 'paper_study_kind_changed'):
                ReplayPaperState(root, False, RUN, saved, study_kind='replay_v1')
            changed = copy.deepcopy(saved)
            changed['profile_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'paper_profile_changed'):
                ReplayPaperState(root, False, RUN, changed, study_kind='recovery_v2')
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            with patch.object(state.adapter, 'profile_sha256', return_value='changed'):
                with self.assertRaisesRegex(ValueError, 'paper_profile_changed_during_run'):
                    state.prompt('writer')

    def test_wrong_study_never_falls_back(self):
        with self.assertRaises(ValueError):
            get_adapter('unknown')
        from replay_paper_evidence import DEFAULT_RUN
        with self.assertRaises((ValueError, KeyError, FileNotFoundError)):
            get_adapter('recovery_v2').build_evidence(DEFAULT_RUN)


if __name__ == '__main__':
    unittest.main()
