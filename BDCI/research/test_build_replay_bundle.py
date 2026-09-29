"""Integrity and reproducibility checks using the saved development evidence."""
import copy
import json
from pathlib import Path
import tempfile
import shutil
import subprocess
import sys
import unittest
import zipfile

import build_replay_bundle as bundle


class ReplayBundleTests(unittest.TestCase):
    root = bundle.HERE / 'replay_paper_runs/live-20260928T151550-319349'

    def review_inputs(self):
        return [bundle.read(self.root / f'{name}.json') for name in ('writer', 'reviewer', 'evidence')]

    def test_team_name_rejects_unsafe_and_nonportable_names(self):
        self.assertEqual(bundle.validate_team_name('真没招了'), '真没招了')
        for name in ('', '.', '..', '../escape', 'a/b', 'a\\b', '/absolute',
                     'C:escape', 'a\n', 'a\x00b', 'a\u202eb', ' a', 'a ',
                     'a.', 'NUL', 'con.txt', 'COM1', None, 7):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'invalid_team_name'):
                bundle.validate_team_name(name)

    def test_chinese_team_archive_and_declared_name_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            current = bundle.HERE / 'replay_paper_runs/editorial-20260929'
            archive_path = bundle.build_bundle(current, tmp / 'build', team_name='真没招了')
            self.assertEqual(archive_path.name, '真没招了.zip')
            with zipfile.ZipFile(archive_path) as archive:
                self.assertTrue(all(name.startswith('真没招了/') for name in archive.namelist()))
                archive.extractall(tmp / 'unpacked')
            stage = tmp / 'unpacked/真没招了'
            manifest = bundle.read(stage / 'manifest.json')
            self.assertEqual(manifest['bundle_name'], '真没招了')
            self.assertEqual(manifest['team_name'], '真没招了')
            self.assertFalse(bundle.verify_bundle(stage)['submission_ready'])
            note = (stage / '提交说明.md').read_text()
            self.assertIn('队伍名称：真没招了', note)
            self.assertNotIn('缺正式队伍信息', note)
            self.assertIn('Reviewer Access Token', note)
            self.assertIn('官方贡献 PR URL', note)
            result = subprocess.run([sys.executable,
                str(stage / 'code/BDCI/research/build_replay_bundle.py'), '--verify', str(stage)],
                cwd=stage / 'code', capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(list(stage.rglob('__pycache__')))
            manifest['team_name'] = '另一支队伍'
            bundle.base._json(stage / 'manifest.json', manifest)
            with self.assertRaisesRegex(ValueError, 'team_name_mismatch'):
                bundle.verify_bundle(stage)
            manifest['team_name'] = '真没招了'
            manifest['bundle_name'] = '../真没招了'
            bundle.base._json(stage / 'manifest.json', manifest)
            with self.assertRaisesRegex(ValueError, 'invalid_team_name'):
                bundle.verify_bundle(stage)
            manifest['bundle_name'] = '真没招了'
            bundle.base._json(stage / 'manifest.json', manifest)
            moved = stage.rename(stage.with_name('renamed'))
            with self.assertRaisesRegex(ValueError, 'bundle_name_mismatch'):
                bundle.verify_bundle(moved)

    def test_bound_review_rejects_wrong_draft_and_invented_quote(self):
        writer, review, evidence = self.review_inputs()
        invalid = copy.deepcopy(review)
        invalid['draft_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'target_mismatch'):
            bundle.validate_bound_review(writer, invalid, evidence)
        invalid = copy.deepcopy(review)
        invalid['issue_quotes'][0] = 'A fabricated passage absent from the draft.'
        with self.assertRaisesRegex(ValueError, 'ungrounded_review'):
            bundle.validate_bound_review(writer, invalid, evidence)

    def test_redundant_note_only_allowed_when_exact(self):
        writer, review, evidence = self.review_inputs()
        bundle.validate_bound_review(writer, review, evidence)
        review['issues'][0]['section_id_note'] = 'invented_section'
        with self.assertRaisesRegex(ValueError, 'conflicting_section_annotation'):
            bundle.validate_bound_review(writer, review, evidence)

    def test_reproducible_archive_and_unpacked_integrity(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            current = bundle.HERE / 'replay_paper_runs/editorial-20260929'
            first = bundle.build_bundle(current, tmp / 'first')
            second = bundle.build_bundle(current, tmp / 'second')
            self.assertEqual(bundle.sha(first), bundle.sha(second))
            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
                self.assertTrue(all(name.startswith('replay-candidate/') for name in names))
                self.assertFalse(any('/runtime/' in name or '/logs/' in name
                    or name.endswith('apis.txt') or 'requests.jsonl' in name for name in names))
                archive.extractall(tmp / 'unpacked')
            stage = tmp / 'unpacked/replay-candidate'
            command = [sys.executable, str(stage / 'code/BDCI/research/build_replay_bundle.py'),
                       '--verify', str(stage)]
            result = subprocess.run(command, cwd=stage / 'code', capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['new_model_calls'], 0)
            self.assertFalse(list(stage.rglob('__pycache__')))
            report = bundle.verify_bundle(stage)
            self.assertFalse(report['submission_ready'])
            self.assertEqual(report['writing'], {'model_calls': 3, 'total_tokens': 24015})
            self.assertEqual(report['archived_live_usage'], {'model_calls': 44, 'total_tokens': 145585})
            # Even a freshly hashed manifest cannot legitimize an incorrect total.
            resource = stage / 'resource_audit.json'
            original = resource.read_bytes()
            stale = json.loads(original)
            stale['total_calls'] = 42
            resource.write_text(json.dumps(stale))
            manifest = bundle.read(stage / 'manifest.json')
            manifest['files']['resource_audit.json'] = bundle.sha(resource)
            bundle.base._json(stage / 'manifest.json', manifest)
            with self.assertRaisesRegex(ValueError, 'resource_audit_mismatch'):
                bundle.verify_bundle(stage)
            resource.write_bytes(original)
            manifest['files']['resource_audit.json'] = bundle.sha(resource)
            bundle.base._json(stage / 'manifest.json', manifest)
            delivered = bundle.read(stage / 'internal_review/reviewer.json')
            self.assertEqual(delivered, bundle.read(self.root / 'reviewer.json'))
            (stage / 'paper/paper.pdf').write_bytes(b'%PDF-tampered')
            with self.assertRaisesRegex(ValueError, 'manifest_mismatch'):
                bundle.verify_bundle(stage)

    def test_relocated_study_preserves_history_and_usage(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            moved = tmp / 'external/deep/study'
            shutil.copytree(bundle.HERE / bundle.base.REPLAY_RUN, moved)
            paper = bundle.HERE / 'replay_paper_runs/editorial-20260929'
            archive = bundle.build_bundle(paper, tmp / 'built', study_run=moved)
            stage = archive.parent / 'replay-candidate'
            manifest = bundle.read(stage / 'manifest.json')
            self.assertEqual(manifest['study_run'], bundle.base.REPLAY_RUN)
            self.assertEqual(bundle.verify_bundle(stage)['archived_live_usage'],
                             {'model_calls': 44, 'total_tokens': 145585})
            self.assertFalse((stage / 'code/BDCI/research/study').exists())
            # Same usage but edited raw evidence cannot replace historical records.
            with (moved / 'prompt_episode_00.txt').open('a') as stream:
                stream.write('changed')
            with self.assertRaisesRegex(ValueError, 'registered_study_content_mismatch'):
                bundle.registered_study(moved, bundle.read(bundle.HERE / 'resource_runs.json'), bundle.base.BDCI)

    def test_missing_saved_input_and_wrong_explicit_input_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            paper = tmp / 'paper'
            shutil.copytree(self.root, paper)
            provenance = bundle.read(paper / 'input_provenance.json')
            provenance['run'] = str(tmp / 'missing')
            provenance.pop('study_run_relative', None)
            bundle.base._json(paper / 'input_provenance.json', provenance)
            with self.assertRaisesRegex(ValueError, 'study_missing_supply_study_run'):
                bundle.build_bundle(paper, tmp / 'missing-build')
            study = tmp / 'wrong'
            shutil.copytree(bundle.HERE / bundle.base.REPLAY_RUN, study)
            model = bundle.read(study / 'model_summary.json')
            model['duration_seconds'] += 1
            bundle.base._json(study / 'model_summary.json', model)
            with self.assertRaisesRegex(ValueError, 'saved_evidence_mismatch'):
                bundle.build_bundle(paper, tmp / 'wrong-build', study_run=study)
            with self.assertRaisesRegex(ValueError, 'unregistered_live_run'):
                bundle.registered_usage(study, bundle.read(bundle.HERE / 'resource_runs.json'), bundle.base.BDCI)

    def test_offline_writing_is_integration_only(self):
        paper = bundle.HERE / 'replay_paper_runs/offline-20260929T002117-209322'
        with tempfile.TemporaryDirectory() as temporary:
            archive = bundle.build_bundle(paper, Path(temporary), study_run=bundle.HERE / bundle.base.REPLAY_RUN)
            stage = archive.parent / 'replay-candidate'
            manifest = bundle.read(stage / 'manifest.json')
            self.assertTrue(manifest['integration_only'])
            result = bundle.verify_bundle(stage)
            self.assertEqual(result['writing_mode'], 'offline_scripted')
            self.assertEqual(result['writing'], {'model_calls': 3, 'total_tokens': 6})
            report = (stage / 'resource_report.md').read_text()
            self.assertIn('Scripted integration fixture (not live API)', report)
            self.assertIn('18 live API calls', report)

    def test_rendered_sources_are_bound_to_final_paper(self):
        current = bundle.HERE / 'replay_paper_runs/editorial-20260929'
        bundle.validate_rendered_sources(current)
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / 'paper'
            shutil.copytree(current, copied)
            with (copied / 'paper.tex').open('a') as output:
                output.write('Unaccounted manuscript modification')
            with self.assertRaisesRegex(ValueError, 'rendered_source_mismatch'):
                bundle.validate_rendered_sources(copied)

    def test_editorial_derivation_requires_original_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle.base._json(root / 'editorial_assistance.json', {'source_directory': '../escape'})
            with self.assertRaisesRegex(ValueError, 'unsafe_editorial_source'):
                bundle.editorial_source(root, bundle.HERE)


if __name__ == '__main__':
    unittest.main()
