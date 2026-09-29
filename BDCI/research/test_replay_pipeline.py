import copy
import fcntl
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_replay_pipeline as pipeline
from replay_paper_evidence import DEFAULT_RUN


class ReplayPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / 'pipeline'
        self.paper = pipeline.HERE / 'replay_paper_runs/editorial-20260929'

    def saved(self):
        return pipeline.run_pipeline(DEFAULT_RUN, self.output, paper=self.paper)

    def test_saved_chain_and_completed_resume_never_call_writer(self):
        with patch.object(pipeline, 'call_writer') as writer:
            state = self.saved()
            signature = state['stages']['bundle']['zip_sha256']
            resumed = pipeline.run_pipeline(DEFAULT_RUN, self.output, resume=True)
            writer.assert_not_called()
        self.assertEqual(resumed['status'], 'saved_candidate_verified')
        self.assertEqual(resumed['stages']['bundle']['zip_sha256'], signature)
        self.assertFalse(resumed['submission_ready'])

    def test_ambiguous_writer_failure_is_not_reissued(self):
        with patch.object(pipeline, 'call_writer', side_effect=RuntimeError('interrupted')) as writer:
            with self.assertRaises(RuntimeError):
                pipeline.run_pipeline(DEFAULT_RUN, self.output)
            self.assertEqual(writer.call_count, 1)
        with patch.object(pipeline, 'call_writer') as writer:
            with self.assertRaisesRegex(ValueError, 'no_automatic_retry'):
                pipeline.run_pipeline(DEFAULT_RUN, self.output, resume=True)
            writer.assert_not_called()
        state = json.loads((self.output / 'pipeline.json').read_text())
        self.assertEqual(state['last_error']['stage'], 'manuscript')

    def test_input_change_rejected_before_new_work(self):
        self.saved()
        changed = copy.deepcopy(pipeline.build_evidence(DEFAULT_RUN))
        changed['resource']['total_tokens'] += 1
        with patch.object(pipeline, 'build_evidence', return_value=changed), patch.object(pipeline, 'call_writer') as writer:
            with self.assertRaisesRegex(ValueError, 'study_input_changed'):
                pipeline.run_pipeline(DEFAULT_RUN, self.output, resume=True)
            writer.assert_not_called()

    def test_completed_archive_corruption_not_overwritten(self):
        self.saved()
        archive = self.output / 'bundle/replay-candidate.zip'
        archive.write_bytes(b'broken archive')
        with self.assertRaisesRegex(ValueError, 'archive_changed'):
            pipeline.run_pipeline(DEFAULT_RUN, self.output, resume=True)
        self.assertEqual(archive.read_bytes(), b'broken archive')

    def test_saved_paper_input_cannot_switch_on_resume(self):
        self.saved()
        with self.assertRaisesRegex(ValueError, 'paper_input_changed'):
            pipeline.run_pipeline(DEFAULT_RUN, self.output, paper=self.paper.parent / 'another', resume=True)

    def test_scripted_paper_is_not_labeled_live_candidate(self):
        paper = pipeline.HERE / 'replay_paper_runs/offline-20260929T002117-209322'
        state = pipeline.run_pipeline(DEFAULT_RUN, self.output, paper=paper)
        self.assertEqual(state['status'], 'integration_candidate_verified')
        self.assertEqual(state['writing_mode'], 'offline_scripted')

    def test_active_writer_lock_prevents_second_process(self):
        self.output.mkdir()
        with (self.output / 'writer.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(pipeline.subprocess, 'run') as launch:
                with self.assertRaises(BlockingIOError):
                    pipeline.call_writer(self.paper, DEFAULT_RUN, self.output, live=False, recover=True)
                launch.assert_not_called()

    def test_complete_raws_allow_only_zero_api_recovery(self):
        paper = pipeline.HERE / 'replay_paper_runs/offline-20260929T002117-209322'
        state = pipeline.run_pipeline(DEFAULT_RUN, self.output, paper=paper)
        state['paper_origin'] = 'native'
        state['stages']['manuscript'] = {'status': 'running'}
        pipeline.save(self.output / 'pipeline.json', state)
        with patch.object(pipeline, 'call_writer') as writer:
            result = pipeline.run_pipeline(DEFAULT_RUN, self.output, resume=True)
            self.assertEqual(writer.call_count, 1)
            self.assertTrue(writer.call_args.kwargs['recover'])
        self.assertEqual(result['status'], 'integration_candidate_verified')

    def test_named_candidate_and_resume_keep_team_identity(self):
        state = pipeline.run_pipeline(DEFAULT_RUN, self.output, paper=self.paper, team_name='真没招了')
        self.assertTrue((self.output / 'bundle/真没招了.zip').is_file())
        result = pipeline.run_pipeline(DEFAULT_RUN, self.output, resume=True)
        self.assertEqual(result['bundle_name'], '真没招了')
        self.assertEqual(result['stages']['bundle']['zip_sha256'], state['stages']['bundle']['zip_sha256'])
        with self.assertRaisesRegex(ValueError, 'team_name_changed'):
            pipeline.run_pipeline(DEFAULT_RUN, self.output, resume=True, team_name='另一队')


if __name__ == '__main__':
    unittest.main()
