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
            delivered = bundle.read(stage / 'internal_review/reviewer.json')
            self.assertEqual(delivered, bundle.read(self.root / 'reviewer.json'))
            (stage / 'paper/paper.pdf').write_bytes(b'%PDF-tampered')
            with self.assertRaisesRegex(ValueError, 'manifest_mismatch'):
                bundle.verify_bundle(stage)

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
