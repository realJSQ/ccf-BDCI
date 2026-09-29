import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_publication_revision as runner
from paper_contracts import SECTION_IDS
from replay_paper_evidence import digest


class PublicationRevisionTests(unittest.TestCase):
    def test_model_admission_ledger_is_per_campaign(self):
        self.assertEqual(runner.publication_request_ledger(Path('/tmp/campaign-a')),
                         Path('/tmp/campaign-a/publication-paper-requests.jsonl'))
        self.assertNotEqual(runner.publication_request_ledger(Path('/tmp/campaign-a')),
                            runner.publication_request_ledger(Path('/tmp/campaign-b')))

    def test_posthoc_audit_uses_subprocess_and_rejects_archive_mismatch(self):
        from types import SimpleNamespace
        analysis = {'summary': {'plans': 36}}
        with tempfile.TemporaryDirectory() as folder:
            audit = Path(folder)
            (audit / 'analysis.json').write_text(json.dumps(analysis))
            def recompute(command, **kwargs):
                self.assertEqual(command[0], runner.sys.executable)
                self.assertIn('--run', command)
                Path(command[command.index('--output') + 1]).write_text(json.dumps(analysis))
                return SimpleNamespace(returncode=0)
            with patch.object(runner, 'PLAN_AUDIT', audit), patch.object(runner.subprocess, 'run', side_effect=recompute) as execute:
                self.assertEqual(runner.verified_plan_analysis(Path('/mock-study')), analysis)
                execute.assert_called_once()
                (audit / 'analysis.json').write_text('{}')
                with self.assertRaisesRegex(ValueError, 'archive_mismatch'):
                    runner.verified_plan_analysis(Path('/mock-study'))

    def test_posthoc_scientific_input_preserves_noncanonical_example_without_paths(self):
        analysis = {'scope': 'Post-hoc', 'summary': {'plans': 36},
                    'interpretation_limits': ['No new trials'],
                    'topology_scenario_representatives': [{'scenario': 'joint_update'}],
                    'action_sequence_groups': [{'actions': [{'op': 'emit'}]}],
                    'episodes': [{'episode_id': 'episode_18', 'requested_order_equals_actual_closure_order': False},
                                 {'episode_id': 'episode_00', 'requested_order_equals_actual_closure_order': True}],
                    'input_sha256': {'/private/path': 'hash'}, 'study_run_name': '/local/run'}
        context = runner.plan_analysis_context(analysis)
        self.assertEqual(context['noncanonical_order_examples'][0]['episode_id'], 'episode_18')
        self.assertNotIn('input_sha256', context)
        self.assertNotIn('study_run_name', context)
        self.assertIn('post-hoc', context['reporting_requirement'])

    def test_inline_reference_is_claim_local_and_exact(self):
        ids = ['arxiv:2607.11098v1', 'arxiv:2608.12761v1']
        paper = {'title': 'Study', 'abstract': 'Abstract', 'sections': [
            {'id': name, 'text': 'Claim [[cite:arxiv:2607.11098v1]].', 'source_ids': [ids[0]]}
            for name in SECTION_IDS]}
        runner.validate_inline_citations(paper, dict.fromkeys(ids))
        paper['sections'][0]['source_ids'].append(ids[1])
        with self.assertRaisesRegex(ValueError, 'source_mismatch'):
            runner.validate_inline_citations(paper, dict.fromkeys(ids))
        paper['sections'][0]['source_ids'].pop()
        paper['sections'][0]['text'] += ' [[cite:unknown]]'
        with self.assertRaisesRegex(ValueError, 'malformed'):
            runner.validate_inline_citations(paper, dict.fromkeys(ids))

    def test_author_fix_does_not_mutate_historical_sources(self):
        original = {'x': {'authors': ['Nusrat jahan Lia'], 'reading_note': 'preserved', 'id': 'x'}}
        revised = runner.checked_sources(original)
        self.assertEqual(revised['x']['authors'], ['Nusrat Jahan Lia'])
        self.assertEqual(original['x']['authors'], ['Nusrat jahan Lia'])
        self.assertEqual(revised['x']['reading_note'], 'preserved')

    def test_primary_literature_replaces_legacy_notes_by_versioned_id(self):
        ref = 'arxiv:2604.16706v1'
        old = {ref: {'id': ref, 'title': 'Outdated index title', 'authors': ['Bhaskar Gurram'],
                     'reading_note': 'Unverified claim',
                     'url': 'https://arxiv.org/abs/2604.16706v1', 'evidence_kind': 'retrieved'}}
        new = {'id': ref, 'title': 'Primary version title', 'authors': ['Bhaskar Gurram'],
               'url': old[ref]['url'], 'evidence_kind': 'retrieved',
               'verification_status': 'primary_fulltext', 'primary_text_excerpt': 'e' * 4000}
        result = runner.upgrade_verified_sources(old, {'sources': {ref: new}})
        self.assertEqual(result[ref]['title'], 'Primary version title')
        self.assertNotIn('reading_note', result[ref])
        self.assertEqual(old[ref]['title'], 'Outdated index title')
        with self.assertRaisesRegex(ValueError, 'require_primary_text_upgrade'):
            runner.upgrade_verified_sources(old, {'sources': {'another': new}})
        with self.assertRaisesRegex(ValueError, 'version_mismatch'):
            runner.upgrade_verified_sources(old, {'sources': {ref: {**new, 'url': 'https://arxiv.org/abs/2604.16706v2'}}})

    def test_prepare_is_zero_api_and_attempted_run_cannot_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            here = Path(folder)
            root = here / 'replay_paper_runs/new'
            class State:
                def __init__(self, root, source, live=False):
                    self.root = root
                    self.provenance = {'source_run_relative': 'old', 'stable': True}
                def archive_inputs(self):
                    runner.write_json(self.root / 'prepared.json', {'input_sha256': digest(self.provenance)})
                    runner.write_json(self.root / 'input_provenance.json', self.provenance)
            with patch.object(runner, 'HERE', here), patch.object(runner, 'PublicationState', State), patch.object(runner, 'native_run') as native:
                self.assertEqual(runner.main(['--source-run', str(here/'old'), '--output-run', str(root)]), 0)
                native.assert_not_called()
                (root / 'live_started.json').write_text('{}')
                with self.assertRaisesRegex(ValueError, 'cannot_be_resent'):
                    runner.main(['--output-run', str(root), '--live'])
                native.assert_not_called()

    def test_prepare_digest_refuses_changed_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            here = Path(folder); root = here / 'replay_paper_runs/new'; root.mkdir(parents=True)
            runner.write_json(root / 'prepared.json', {'input_sha256': 'old'})
            class State:
                def __init__(self, *args, **kwargs): self.provenance = {'changed': True}
            with patch.object(runner, 'HERE', here), patch.object(runner, 'PublicationState', State), patch.object(runner, 'native_run') as native:
                with self.assertRaisesRegex(ValueError, 'inputs_changed'):
                    runner.main(['--source-run', str(here/'old'), '--output-run', str(root), '--live'])
                native.assert_not_called()

    def test_resume_replays_saved_responses_without_native_call(self):
        import os
        original_cwd = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as folder:
                here = Path(folder); root = here / 'replay_paper_runs/new'; root.mkdir(parents=True)
                provenance = {'source_run_relative': 'old'}
                runner.write_json(root / 'prepared.json', {'input_sha256': digest(provenance)})
                runner.write_json(root / 'input_provenance.json', provenance)
                runner.write_json(root / 'model_summary.json', {'mode': 'live', 'model_calls': 3, 'total_tokens': 123})
                for role in ('writer', 'reviewer', 'reviser'):
                    (root / f'prompt_{role}.txt').write_text(role)
                    (root / f'raw_{role}.txt').write_text('{}')
                class State:
                    roles = ('writer', 'reviewer', 'reviser')
                    def __init__(self, *args, **kwargs):
                        self.provenance = provenance
                        self.outputs = {}; self.evidence = {'resource': {}}; self.sources = {}
                    def prompt(self, role): return role
                    def decode_response(self, text): return json.loads(text)
                    def accept(self, role, value): self.outputs[role] = value
                with patch.object(runner, 'HERE', here), patch.object(runner, 'PublicationState', State), patch.object(runner, 'native_run') as native, patch('publication_render.render_publication', return_value=root/'paper.tex'), patch.object(runner, 'compile_pdf', return_value={'sha256': 'new'}), patch('publication_quality.audit_publication', return_value={'findings': [], 'pages': 1}):
                    self.assertEqual(runner.main(['--resume', str(root)]), 0)
                    native.assert_not_called()
                summary = json.loads((root/'summary.json').read_text())
                self.assertEqual(summary['resume_new_model_calls'], 0)
                self.assertFalse(summary['external_review_token_reused'])
        finally:
            os.chdir(original_cwd)


if __name__ == '__main__':
    unittest.main()
