"""No new experiments or model calls: validate writing-state transitions."""
import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from run_paper import PaperState, DEFAULT_PILOT, compile_and_check


class PaperWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state=PaperState(Path(self.tmp.name),DEFAULT_PILOT,False)

    def test_existing_evidence_is_used_without_experiment(self):
        self.assertEqual(self.state.metrics['n'],24)
        self.assertFalse(self.state.context['new_experiments_allowed'])
        self.assertTrue((self.state.root/'input_scoring_verification.json').exists())
        self.assertNotIn('api_key',self.state.prompt('writer'))

    def test_live_cannot_use_scripted_writing(self):
        state=PaperState(self.state.root,DEFAULT_PILOT,True)
        with self.assertRaises(ValueError):state.offline_response('writer')

    def test_review_requires_draft_and_revision_requires_review(self):
        with self.assertRaises(ValueError):self.state.accept('reviewer',{})
        with self.assertRaises(ValueError):self.state.accept('reviser',{})

    def test_major_issue_requires_text_change(self):
        self.state.accept('writer',self.state.offline_response('writer'))
        self.state.accept('reviewer',self.state.offline_response('reviewer'))
        unchanged=copy.deepcopy(self.state.draft)
        unchanged['response_to_review']=[{'issue_index':0,'change':'Claimed but not done'}]
        with self.assertRaises(ValueError):self.state.accept('reviser',unchanged)
        self.state.accept('reviser',self.state.offline_response('reviser'))
        self.assertIsNotNone(self.state.paper)

    def test_compile_does_not_require_zip_preserved_executable_bit(self):
        with patch('run_paper.subprocess.run',side_effect=RuntimeError('stop_before_compile')) as call:
            with self.assertRaisesRegex(RuntimeError,'stop_before_compile'):
                compile_and_check(self.state.root,self.state.root/'paper.tex')
        self.assertEqual(call.call_args.args[0][0],'bash')


if __name__=='__main__':unittest.main()
