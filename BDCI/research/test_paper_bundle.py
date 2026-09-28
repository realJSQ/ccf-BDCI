"""Dry-run package tests with local fixtures; no install, network or model."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

try:
    from . import paper_bundle
except ImportError:
    import paper_bundle


class PaperBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.project, self.root, self.pilot = self.base / 'BDCI', self.base / 'paper_run', self.base / 'pilot_run'
        for path in (self.project, self.root, self.pilot):
            path.mkdir()
        self.patch = patch.object(paper_bundle, 'BDCI', self.project)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.write(self.root / 'paper.pdf', b'%PDF-1.4\nlocal fixture\n')
        self.write(self.root / 'paper.tex', 'Safe TeX fixture')
        self.write(self.root / 'references.bib', '@article{test,title={Local fixture}}')
        paper = {'title': 'Local paper fixture', 'abstract': 'Local fixture.',
                 'sections': [{'id': name, 'text': 'Local fixture', 'source_ids': ['a', 'b']}
                              for name in ('introduction', 'related_work', 'methods', 'discussion', 'conclusion')]}
        review = {'verdict': 'revise', 'external_reviewer': False,
                  'issues': [{'severity': 'minor', 'section_id': 'methods', 'message': 'Clarify.'}],
                  'revision_instructions': ['Clarify the workflow.']}
        revised = dict(paper, response_to_review=[{'issue_index': 0, 'change': 'Clarified.'}])
        for name, value in (('paper.json', paper), ('reviewer.json', review), ('reviser.json', revised)):
            self.write(self.root / name, json.dumps(value))
        self.write(self.pilot / 'metrics.json', json.dumps({'n': 24}))
        self.write(self.pilot / 'summary.json', json.dumps({'model_calls': 6}))
        self.write(self.project / 'research/example.py', '# Reproducible local source\n')
        self.write(self.project / 'research/skills/example/SKILL.md', '# Local skill\n')
        for name in paper_bundle.STYLE_FILES:
            self.write(self.project / 'validation/latex/iclr-template/iclr2026' / name, '% template fixture\n')
        for name in ('research_budget_rail.py', 'research_evidence_rail.py'):
            self.write(self.project / 'jiuwenswarm/jiuwenswarm/agents/harness/common/rails' / name, '# Source overlay\n')
        for name in paper_bundle.SUBMISSION_DOCS:
            self.write(self.project / 'docs/submission' / name,
                       '# Fixture documentation\n[Source](../../research/example.py)\n')
        for name in paper_bundle.CONTRIBUTION_FILES:
            self.write(self.project / 'contribution' / name, 'Local contribution fixture\n')
        self.summary = {'mode': 'offline_scripted', 'model_calls': 3, 'total_tokens': 6, 'cost': None}

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else value.encode())

    def build(self):
        return paper_bundle.build_bundle(self.root, pilot_root=self.pilot, summary=self.summary)

    def test_competition_shape_is_explicitly_incomplete_and_zip_paths_safe(self):
        archive = self.build()
        self.assertEqual(archive.name, 'workflow-validation.zip')
        with zipfile.ZipFile(archive) as zipped:
            names = zipped.namelist()
            for name in names:
                self.assertTrue(name.startswith('workflow-validation/'))
                self.assertFalse(name.startswith('/'))
                self.assertNotIn('..', Path(name).parts)
            for name in ('paper/paper.pdf', 'paper/paper.tex', 'paper/references.bib',
                         'AgenticReviewer/README.md', 'docs/architecture.md', 'docs/module_call.md',
                         'docs/innovation.md', 'framework_contribution.md', 'resource_report.md', '提交说明.md',
                         'internal_review/reviewer.json', 'internal_review/reviser.json',
                         'evidence/pilot/metrics.json', 'code/BDCI/research/example.py'):
                self.assertIn('workflow-validation/' + name, names)
            manifest = json.loads(zipped.read('workflow-validation/manifest.json'))
            self.assertEqual(manifest['status'], 'not_submission_ready')
            self.assertFalse(manifest['external_review_performed'])
            self.assertFalse(manifest['upstream_pr_submitted'])
            self.assertFalse(manifest['scientific_acceptance'])
            self.assertIn('../code/BDCI/research/example.py',
                          zipped.read('workflow-validation/docs/architecture.md').decode())
            self.assertIn('](code/BDCI/research/example.py)',
                          zipped.read('workflow-validation/framework_contribution.md').decode())
            self.assertGreaterEqual(len(manifest['missing_materials']), 3)
            self.assertTrue(all(not name.endswith('/token.txt') for name in names))

    def test_private_and_unlisted_material_is_excluded(self):
        sensitive = 'sk-' + 'FAKESECRET' * 4
        for parent in (self.root, self.pilot, self.project):
            for name in ('apis.txt', '.env', 'runtime/private.json', 'logs/request.json',
                         '.git/config', '.venv/config', 'tools/tectonic-cache/private.json', 'requests.lock'):
                self.write(parent / name, sensitive)
        archive = self.build()
        with zipfile.ZipFile(archive) as zipped:
            for name in zipped.namelist():
                self.assertFalse(any(part in ('.env', 'apis.txt', '.git', '.venv', 'runtime', 'logs', 'tectonic-cache')
                                     for part in Path(name).parts))
                self.assertNotIn(sensitive.encode(), zipped.read(name))

    def test_missing_pdf_rejected_without_output(self):
        (self.root / 'paper.pdf').unlink()
        with self.assertRaisesRegex(ValueError, 'paper.pdf'):
            self.build()
        self.assertFalse((self.root / 'workflow-validation.zip').exists())

    def test_revision_runner_inputs_and_selected_evidence_survive_packaging(self):
        research = self.project / 'research'
        for runner, inputs in paper_bundle.RUNNER_INPUTS.items():
            self.write(research / runner, '# Runner fixture\n')
            for relative in inputs:
                self.write(research / relative, json.dumps({'saved_input': relative}))
        self.write(research / 'REVISION.md', '# Revision workflow\n')
        self.write(research / paper_bundle.REVISION_RUN / 'raw_refiner.txt', 'Saved revision response')
        secret = 'sk-' + 'FAKESECRET' * 4
        for relative in ('prior_work/unlisted.json',
                         paper_bundle.REVISION_RUN + '/logs/request.json',
                         paper_bundle.REVISION_RUN + '/workflow_journal.json',
                         'revision_runs/unselected/refiner.json'):
            self.write(research / relative, secret)
        with zipfile.ZipFile(self.build()) as zipped:
            prefix = 'workflow-validation/code/BDCI/research/'
            for inputs in paper_bundle.RUNNER_INPUTS.values():
                for relative in inputs:
                    self.assertEqual(json.loads(zipped.read(prefix + relative)),
                                     {'saved_input': relative})
            self.assertIn(prefix + 'REVISION.md', zipped.namelist())
            self.assertEqual(zipped.read(prefix + paper_bundle.REVISION_RUN + '/raw_refiner.txt'),
                             b'Saved revision response')
            self.assertTrue(all(secret.encode() not in zipped.read(name) for name in zipped.namelist()))
            self.assertEqual(json.loads(zipped.read('workflow-validation/manifest.json'))['status'],
                             'not_submission_ready')

    def test_runner_with_missing_fixed_input_is_not_packaged_as_working(self):
        self.write(self.project / 'research/run_protocol_design.py', '# Runner fixture\n')
        self.write(self.project / 'research/prior_work/revision_followup.json', '{}')
        with self.assertRaisesRegex(ValueError, 'unsafe_bundle_source'):
            self.build()
        self.assertFalse((self.root / 'workflow-validation.zip').exists())

    def replay_fixture(self):
        research = self.project / 'research'
        saved = research / paper_bundle.REPLAY_RUN
        for name in paper_bundle.REPLAY_EVIDENCE_FILES:
            self.write(saved / name, '{}')
        for name in paper_bundle.POSTHOC_FILES:
            self.write(saved / 'posthoc_report_terminal' / name, '{}')
        self.write(saved / 'frozen_source/research/replay_engine.py', '# Frozen implementation\n')
        self.write(saved / 'frozen_source/research/replay_protocol.json', '{}')
        self.write(saved / 'frozen_source/research/skills/recovery-replay/roles/planner.md', '# Frozen prompt\n')
        return saved

    def test_selected_replay_is_complete_and_private_run_material_is_excluded(self):
        saved = self.replay_fixture()
        research = self.project / 'research'
        for relative in paper_bundle.PROTOCOL_RUNS:
            self.write(research / relative / 'auditor.json', '{}')
        secret = 'sk-' + 'FAKESECRET' * 4
        for relative in ('logs/private.json', 'runtime/private.json', 'requests.jsonl',
                         'workflow_journal.json', 'unlisted.json', 'apis.txt',
                         'frozen_source/runtime/private.json', 'frozen_source/.env',
                         'frozen_source/research/__pycache__/private.pyc'):
            self.write(saved / relative, secret)
        with zipfile.ZipFile(self.build()) as zipped:
            prefix = 'workflow-validation/code/BDCI/research/'
            for name in paper_bundle.REPLAY_EVIDENCE_FILES:
                self.assertIn(prefix + paper_bundle.REPLAY_RUN + '/' + name, zipped.namelist())
            for name in paper_bundle.POSTHOC_FILES:
                self.assertIn(prefix + paper_bundle.REPLAY_RUN + '/posthoc_report_terminal/' + name,
                              zipped.namelist())
            self.assertIn(prefix + paper_bundle.REPLAY_RUN + '/frozen_source/research/replay_engine.py',
                          zipped.namelist())
            for relative in paper_bundle.PROTOCOL_RUNS:
                self.assertIn(prefix + relative + '/auditor.json', zipped.namelist())
            self.assertTrue(all(secret.encode() not in zipped.read(name) for name in zipped.namelist()))

    def test_missing_selected_replay_evidence_is_rejected(self):
        saved = self.replay_fixture()
        (saved / 'raw_episode_17.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'unsafe_bundle_source'):
            self.build()

    def test_frozen_source_directory_symlink_is_rejected(self):
        saved = self.replay_fixture()
        (saved / 'frozen_source/aliased').symlink_to(saved / 'frozen_source/research', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'unsafe_bundle_source'):
            self.build()

    def test_revision_input_symlink_is_rejected(self):
        research = self.project / 'research'
        self.write(research / 'prior_work/revision_seed_sources.json', '{}')
        path = research / 'prior_work/revision_seed_sources.json'
        path.unlink()
        path.symlink_to(self.root / 'paper.json')
        with self.assertRaisesRegex(ValueError, 'unsafe_bundle_source'):
            self.build()

    def test_fake_external_review_rejected(self):
        path = self.root / 'reviewer.json'
        review = json.loads(path.read_text())
        review['external_reviewer'] = True
        path.write_text(json.dumps(review))
        with self.assertRaisesRegex(ValueError, 'external_reviewer'):
            self.build()

    def test_missing_revision_response_rejected(self):
        path = self.root / 'reviser.json'
        revised = json.loads(path.read_text())
        revised['response_to_review'] = []
        path.write_text(json.dumps(revised))
        with self.assertRaisesRegex(ValueError, 'missing_issue_response'):
            self.build()

    def test_symlink_in_whitelisted_evidence_rejected(self):
        outside = self.base / 'private.txt'
        outside.write_text('Do not package')
        (self.pilot / 'raw_peer.txt').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'unsafe_bundle_source'):
            self.build()

    def test_credential_like_content_in_allowed_file_is_rejected(self):
        self.write(self.pilot / 'prompt_peer.txt', 'sk-' + 'FAKESECRET' * 4)
        with self.assertRaisesRegex(ValueError, 'credential_like_content'):
            self.build()
        self.assertFalse((self.root / 'workflow-validation.zip').exists())


if __name__ == '__main__':
    unittest.main()
