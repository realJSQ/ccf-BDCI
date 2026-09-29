from pathlib import Path
import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from run_replay_paper import HERE, ReplayPaperState, restore_saved_roles
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

    def test_duplicate_quote_is_allowed_only_when_identical_and_grounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = ReplayPaperState(Path(temporary), False, RUN, study_kind='recovery_v2')
            state.accept('writer', state.offline_response('writer'))
            review = state.offline_response('reviewer')
            quote = state.outputs['writer']['abstract']
            review.update(verdict='revise', issues=[{'severity':'minor','section_id':'abstract',
                'message':'Clarify this statement.', 'quote':quote}], issue_quotes=[quote])
            bad = copy.deepcopy(review);bad['issues'][0]['quote'] = 'different'
            with self.assertRaisesRegex(ValueError, 'conflicting_quote_annotation'):
                state.accept('reviewer', bad)
            bad = copy.deepcopy(review);bad['issues'][0]['quote'] = bad['issue_quotes'][0] = 'invented quotation'
            with self.assertRaisesRegex(ValueError, 'ungrounded_review'):
                state.accept('reviewer', bad)
            state.accept('reviewer', review)
            self.assertEqual(state.outputs['reviewer'], review)

    def test_continuation_preserves_raws_and_rejects_changed_inherited_prompt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / 'parent';parent.mkdir()
            source = ReplayPaperState(parent, False, RUN, study_kind='recovery_v2')
            for role in ('writer','reviewer'):
                (parent/f'prompt_{role}.txt').write_text(source.prompt(role))
                value = source.offline_response(role)
                (parent/f'raw_{role}.txt').write_text(json.dumps(value))
                source.accept(role,value)
            output = root/'child';output.mkdir()
            child = ReplayPaperState(output,False,RUN,study_kind='recovery_v2')
            raws,prompts = restore_saved_roles(child,parent,('writer','reviewer'))
            self.assertEqual(set(raws),set(prompts))
            self.assertEqual(child.outputs,source.outputs)
            for role in raws:
                self.assertEqual((output/f'raw_{role}.txt').read_bytes(),(parent/f'raw_{role}.txt').read_bytes())
            wrong = root/'wrong';wrong.mkdir()
            incompatible = ReplayPaperState(wrong,False,RUN,study_kind='recovery_v2')
            (parent/'prompt_writer.txt').write_text('different scientific context')
            with self.assertRaisesRegex(ValueError,'inherited_prompt_incompatible'):
                restore_saved_roles(incompatible,parent,('writer',))


if __name__ == '__main__':
    unittest.main()
