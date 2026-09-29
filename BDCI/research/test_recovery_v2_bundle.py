"""V2 archive evidence remains independently replayable, without model APIs."""
import json
from pathlib import Path
import tempfile
import shutil
import subprocess
import sys
import unittest

import build_replay_bundle as bundle
from recovery_v2_paper_evidence import build_evidence
from resource_accounting import audit_resources, render_report


class RecoveryV2BundleTests(unittest.TestCase):
    study = bundle.HERE / 'recovery_v2_runs/live-20260929T060132-126279'

    def test_selected_copy_is_complete_and_frozen_verifiable(self):
        expected = build_evidence(self.study)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'relocated' / self.study.name
            bundle.base._copy_study_evidence(self.study, destination, 'recovery_v2')
            self.assertEqual(build_evidence(destination), expected)
            files = {str(p.relative_to(destination)) for p in destination.rglob('*') if p.is_file()}
            self.assertTrue(set(expected['artifact_sha256']).issubset(files))
            self.assertEqual(len(list(destination.glob('raw_episode_*.txt'))), 36)
            self.assertFalse(any('logs' in p.parts or '__pycache__' in p.parts for p in destination.rglob('*')))
            self.assertFalse((destination / 'workflow_journal.json').exists())
            inventory = bundle.read(bundle.HERE / 'resource_runs.json')
            relative, usage = bundle.registered_study(destination, inventory, bundle.base.BDCI, 'recovery_v2')
            self.assertEqual(relative, 'recovery_v2_runs/' + self.study.name)
            self.assertTrue(usage.endswith('/model_usage.jsonl'))
            with (destination / 'raw_episode_35.txt').open('a') as stream:
                stream.write('modified')
            with self.assertRaisesRegex(ValueError, 'registered_study_content_mismatch'):
                bundle.registered_study(destination, inventory, bundle.base.BDCI, 'recovery_v2')

    def test_bound_prompts_and_profile_reject_tampering(self):
        historical = bundle.HERE / 'replay_paper_runs/offline-20260929T002117-209322'
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / 'synthetic-paper'
            copied.mkdir()
            # This fixture tests binding only. Historical PDF bytes supply the
            # file/hash contract, not evidence of rendering this synthetic paper.
            for name in ('paper.pdf', 'summary.json'):
                shutil.copyfile(historical / name, copied / name)
            from run_replay_paper import ReplayPaperState
            state = ReplayPaperState(copied, False, self.study, study_kind='recovery_v2')
            for role in state.roles:
                (copied / f'prompt_{role}.txt').write_text(state.prompt(role))
                value = state.offline_response(role)
                (copied / f'raw_{role}.txt').write_text(json.dumps(value))
                state.accept(role, value)
            bundle.base._json(copied / 'paper.json', state.outputs['reviser'])
            bundle.validate_manuscript(copied, self.study)
            prompt = copied / 'prompt_writer.txt'
            prompt.write_text(prompt.read_text() + 'unbound text')
            with self.assertRaisesRegex(ValueError, 'saved_prompt_binding_mismatch:writer'):
                bundle.validate_manuscript(copied, self.study)

    def test_selected_submission_docs_are_v2_specific(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            bundle.write_v2_submission_docs(stage, 'recovery_v2_runs/' + self.study.name,
                'offline-fixture', {'mode': 'offline_scripted'}, build_evidence(self.study))
            architecture = (stage / 'docs/architecture.md').read_text()
            modules = (stage / 'docs/module_call.md').read_text()
            innovation = (stage / 'docs/innovation.md').read_text()
            self.assertIn('recovery_v2_evidence/1', architecture)
            self.assertIn('--study-kind recovery_v2', modules)
            self.assertIn('没有1600词或人为token上限', modules)
            self.assertIn('A: 36/36 正确', innovation)
            self.assertIn('不是 Stanford 外审', modules)
            self.assertNotIn('editorial-20260929', architecture + modules + innovation)

    def test_documented_relative_verify_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = bundle.build_bundle(bundle.HERE / 'replay_paper_runs/editorial-20260929',
                Path(temporary), team_name='真没招了')
            stage = archive.parent / '真没招了'
            result = subprocess.run([sys.executable, 'BDCI/research/build_replay_bundle.py',
                '--verify', '..'], cwd=stage / 'code', capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['new_model_calls'], 0)

    def test_copy_rejects_unsafe_snapshot_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle.base._json(root / 'pre_registration.json', {'frozen_snapshot_sha256': {'../escape': '0'}})
            with self.assertRaisesRegex(ValueError, 'unsafe_bundle_source'):
                bundle.base._copy_study_evidence(root, root / 'copy', 'recovery_v2')

    def test_kind_is_explicit_and_unknown_does_not_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle.base._json(root / 'input_provenance.json', {'study_kind': 'recovery_v2'})
            self.assertEqual(bundle.manuscript_adapter(root).study_kind, 'recovery_v2')
            bundle.base._json(root / 'input_provenance.json', {})
            self.assertEqual(bundle.manuscript_adapter(root).study_kind, 'replay_v1')
            bundle.base._json(root / 'input_provenance.json', {'study_kind': 'unknown'})
            with self.assertRaisesRegex(ValueError, 'unknown_study_kind'):
                bundle.manuscript_adapter(root)

    def test_resource_report_does_not_mislabel_v2_as_six_development_cases(self):
        audit = audit_resources(bundle.base.BDCI, bundle.read(bundle.HERE / 'resource_runs.json'))
        usage = 'research/recovery_v2_runs/' + self.study.name + '/model_usage.jsonl'
        writing = {'model_calls': 3, 'total_tokens': 6, 'mode': 'offline_scripted'}
        report = render_report(audit, usage, writing, study_kind='recovery_v2')
        self.assertIn('nine self-authored structurally held-out base instances', report)
        self.assertNotIn('six self-authored', report)
        self.assertIn('36 live API calls', report)
        self.assertIn('113,384 live API tokens', report)


if __name__ == '__main__':
    unittest.main()
