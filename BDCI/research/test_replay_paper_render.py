import copy
import tempfile
import unittest
from pathlib import Path

try:
    from .replay_paper_render import render_replay_paper, SCENARIOS, POLICIES
    from .paper_contracts import SECTION_IDS
except ImportError:
    from replay_paper_render import render_replay_paper, SCENARIOS, POLICIES
    from paper_contracts import SECTION_IDS


class ReplayPaperRenderTests(unittest.TestCase):
    def setUp(self):
        self.sources = {key: {'id': key, 'title': 'Recorded source ' + key,
            'authors': ['Recorded Author'], 'year': 2026, 'url': 'https://example.org/' + key,
            'evidence_kind': 'retrieved'} for key in ('s1', 's2')}
        self.paper = {'title': 'Replay development study', 'abstract': 'A descriptive study.',
                      'sections': [{'id': sid, 'text': 'Discussion of limitations.',
                                    'source_ids': ['s1', 's2']} for sid in SECTION_IDS]}
        rows = [{'scenario': s, 'policy': p, 'episodes': 6, 'correct_completion': 2,
                 'wrong_completion': 0, 'refusal': 4, 'tool_calls': 8} for s in SCENARIOS for p in POLICIES]
        self.evidence = {'strict': {'summary_by_scenario_policy': copy.deepcopy(rows),
                                     'noncompletion_reasons': {'missing_terminal_action': 8}},
                         'posthoc': {'summary_by_scenario_policy': copy.deepcopy(rows), 'changed_plan_count': 8},
                         'resource': {'model_calls': 18, 'total_tokens': 14878}}

    def render(self, root):
        return render_replay_paper(Path(root), self.paper, self.sources, self.evidence, 'live')

    def test_distinct_evidence_tables_and_anonymous_header(self):
        self.evidence['posthoc']['summary_by_scenario_policy'][0].update(correct_completion=6, refusal=0)
        with tempfile.TemporaryDirectory() as root:
            tex = self.render(root).read_text()
            md = (Path(root) / 'paper.md').read_text()
            self.assertIn('Original strict execution', tex)
            self.assertIn('Post-hoc compatibility replay (not preregistered)', tex)
            self.assertIn('Noncompletion', tex)
            self.assertIn('does not imply voluntary refusal', tex)
            self.assertNotIn('Published as', tex)
            self.assertIn(r'\lhead{Development study / internal draft}', tex)
            self.assertIn(r'\author{Anonymous authors}', tex)
            self.assertIn('| clean | A | 6 | 2 | 0 | 4 | 8 |', md)
            self.assertIn('| clean | A | 6 | 6 | 0 | 0 | 8 |', md)
            self.assertEqual(tex.count(r'\begin{tabular}'), 2)
            self.assertIn('14878', tex)
            self.assertIn('missing_terminal_action: 8', md)
            self.assertIn('post-hoc plans changed: 8', tex)

    def test_tex_injection_escaped_in_paper_and_reference(self):
        attack = r'\input{/tmp/private} % & _'
        self.paper['title'] = attack
        self.sources['s1']['title'] = attack
        self.sources['s1']['authors'] = [attack]
        with tempfile.TemporaryDirectory() as root:
            tex = self.render(root).read_text()
            bib = (Path(root) / 'references.bib').read_text()
            self.assertNotIn(r'\input{', tex + bib)
            self.assertIn(r'\textbackslash{}input\{', tex + bib)

    def test_invalid_evidence_fails_before_output(self):
        for kind in ('duplicate', 'missing', 'count', 'denominator', 'nan_resource', 'diagnostic'):
            with self.subTest(kind=kind):
                original = copy.deepcopy(self.evidence)
                rows = self.evidence['strict']['summary_by_scenario_policy']
                if kind == 'duplicate': rows.append(copy.deepcopy(rows[0]))
                if kind == 'missing': rows.pop()
                if kind == 'count': rows[0]['refusal'] = 5
                if kind == 'denominator':
                    for row in rows[:4]: row.update(episodes=7, refusal=5)
                if kind == 'diagnostic': self.evidence['strict']['noncompletion_reasons']['missing_terminal_action'] = 13
                if kind == 'nan_resource': self.evidence['resource']['total_tokens'] = float('nan')
                with tempfile.TemporaryDirectory() as root:
                    with self.assertRaises(ValueError): self.render(root)
                    self.assertEqual(list(Path(root).iterdir()), [])
                self.evidence = original

    def test_missing_bibliographic_metadata_not_invented(self):
        for key in ('authors', 'year', 'title', 'url'):
            source = self.sources['s1'].copy()
            del self.sources['s1'][key]
            with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError):
                self.render(root)
            self.sources['s1'] = source

    def test_synthetic_citation_rejected(self):
        self.sources['s1']['evidence_kind'] = 'synthetic'
        with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError): self.render(root)


if __name__ == '__main__':
    unittest.main()
