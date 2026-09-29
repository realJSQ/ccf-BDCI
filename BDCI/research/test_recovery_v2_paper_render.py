import copy
import tempfile
import unittest
from pathlib import Path

try:
    from .recovery_v2_paper_render import render, POLICIES, SCENARIOS, SCHEMA
    from .paper_contracts import SECTION_IDS
except ImportError:
    from recovery_v2_paper_render import render, POLICIES, SCENARIOS, SCHEMA
    from paper_contracts import SECTION_IDS


class RecoveryV2RenderTests(unittest.TestCase):
    def setUp(self):
        self.sources = {key: {'id': key, 'title': 'Retrieved source ' + key,
            'authors': ['Author'], 'year': 2026, 'url': 'https://example.org/' + key,
            'evidence_kind': 'retrieved'} for key in ('s1', 's2')}
        self.paper = {'title': 'A recovery study', 'abstract': 'Descriptive evidence.',
            'sections': [{'id': sid, 'text': 'A scientific argument.', 'source_ids': ['s1', 's2']} for sid in SECTION_IDS]}
        self.evidence = {'schema': SCHEMA, 'study_kind': 'recovery_v2', 'base_instance_count': 9,
            'completed_model_plans': 36, 'paired_model_policy_replays': 144,
            'deterministic_g_replays': 36, 'completed_policy_replays': 180,
            'summary_by_scenario_policy': [{'scenario': s, 'policy': p, 'episodes': 9,
                'correct_completion': 9, 'wrong_completion': 0, 'refusal': 0,
                'tool_calls': 18, 'stale_completed': 0} for s in SCENARIOS for p in POLICIES],
            'paired_base_instances': [{'case_id': f'case-{i}', 'policies': {p: {'episodes': 4,
                'correct': 4, 'tool_calls': 8} for p in POLICIES}, 'E_minus_A_correct': 0,
                'E_minus_A_tool_calls': 0} for i in range(9)],
            'policies': dict(POLICIES), 'resource': {'model_calls': 36, 'total_tokens': 123456,
                'duration_seconds': 15.5, 'initial_cache_tool_calls': 100, 'cost': None,
                'duration_scope': 'Study only, excludes writing.'},
            'development_assistance': {'description': 'Agent proposals; developer-assisted protocol.'},
            'information_condition': 'Matched actual and declared graph information.',
            'limitations': ['Self-authored structural holdout, not external validation.']}

    def test_dynamic_matrix_paired_rows_and_no_fixed_conclusion(self):
        # Change a single outcome in both aggregation views: no fixed all-correct claim.
        self.evidence['summary_by_scenario_policy'][0].update(correct_completion=8, wrong_completion=1)
        self.evidence['paired_base_instances'][0]['policies']['A']['correct'] = 3
        self.evidence['paired_base_instances'][0]['E_minus_A_correct'] = 1
        with tempfile.TemporaryDirectory() as root:
            tex = render(root, self.paper, self.evidence, self.sources).read_text()
            md = (Path(root) / 'paper.md').read_text()
            self.assertEqual(tex.count(r'\begin{tabular}'), 2)
            self.assertIn('| clean | A | 9 | 8 | 1 | 0 | 18 | 0 |', md)
            self.assertIn('| 1 | 3/4; 8 | 4/4; 8 | 4/4; 8 | 4/4; 8 | 4/4; 8 | 1 | 0 |', md)
            self.assertIn('case-8', md)
            self.assertIn('G requires zero model calls', md)
            self.assertIn('36 saved model plans', md)
            self.assertIn('180 executions are not independent samples', md)
            self.assertNotIn('Published as', tex)
            self.assertNotIn('post-hoc', md)
            self.assertIn('123456', tex)
            self.assertIn('developer-assisted', md)

    def test_reject_inconsistent_or_wrong_version_before_writing(self):
        edits = [lambda e: e.update(schema='replay_v1'),
                 lambda e: e['summary_by_scenario_policy'].pop(),
                 lambda e: e['summary_by_scenario_policy'].append(e['summary_by_scenario_policy'][0]),
                 lambda e: e['summary_by_scenario_policy'][0].update(refusal=1),
                 lambda e: e['paired_base_instances'].pop(),
                 lambda e: e['paired_base_instances'][0].update(E_minus_A_correct=1),
                 lambda e: e['paired_base_instances'][0]['policies']['A'].update(tool_calls=999),
                 lambda e: e.update(completed_policy_replays=179),
                 lambda e: e['resource'].update(total_tokens=float('nan'))]
        for i, edit in enumerate(edits):
            with self.subTest(i=i), tempfile.TemporaryDirectory() as root:
                evidence = copy.deepcopy(self.evidence)
                edit(evidence)
                with self.assertRaises(ValueError): render(root, self.paper, evidence, self.sources)
                self.assertFalse(list(Path(root).iterdir()))

    def test_no_artificial_manuscript_size_limit(self):
        self.paper['sections'][0]['text'] = 'Evidence discussion. ' * 6000
        with tempfile.TemporaryDirectory() as root:
            render(root, self.paper, self.evidence, self.sources)
            self.assertIn(self.paper['sections'][0]['text'], (Path(root) / 'paper.md').read_text())

    def test_escape_untrusted_text_and_bibliography(self):
        attack = r'\input{/tmp/private}%&_'
        self.paper['title'] = attack
        self.sources['s1']['title'] = attack
        self.evidence['paired_base_instances'][0]['case_id'] = attack
        with tempfile.TemporaryDirectory() as root:
            tex = render(root, self.paper, self.evidence, self.sources).read_text()
            bib = (Path(root) / 'references.bib').read_text()
            self.assertNotIn(r'\input{', tex + bib)
            self.assertIn(r'\textbackslash{}input\{', tex + bib)

    def test_unverified_citation_rejected(self):
        self.sources['s1']['evidence_kind'] = 'synthetic'
        with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError):
            render(root, self.paper, self.evidence, self.sources)


if __name__ == '__main__':
    unittest.main()
