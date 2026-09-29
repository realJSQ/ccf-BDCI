import copy
import tempfile
import unittest
from pathlib import Path

try:
    from .publication_render import render_publication, validate_publication, SOURCE_IDS
    from . import test_recovery_v2_paper_render as old_fixture
except ImportError:
    from publication_render import render_publication, validate_publication, SOURCE_IDS
    import test_recovery_v2_paper_render as old_fixture


class PublicationRenderTests(unittest.TestCase):
    def setUp(self):
        fixture = old_fixture.RecoveryV2RenderTests()
        fixture.setUp()
        self.paper, self.evidence = fixture.paper, fixture.evidence
        names = [['Aritra Mazumder', 'Nusrat jahan Lia'], ['Jesus Salas'], ['Bhaskar Gurram']]
        self.sources = {ref: {'id': ref, 'title': 'Verified title', 'authors': authors, 'year': 2026,
                             'url': 'https://arxiv.org/abs/' + ref[6:], 'evidence_kind': 'retrieved'}
                        for ref, authors in zip(SOURCE_IDS, names)}
        for sec in self.paper['sections']:
            sec.update(text='A supported claim [[cite:' + SOURCE_IDS[0] + ']].', source_ids=[SOURCE_IDS[0]])
        self.paper['sections'][1].update(text='A second source [[cite:' + SOURCE_IDS[1] + ']].', source_ids=[SOURCE_IDS[1]])
        for i, row in enumerate(self.evidence['paired_base_instances']):
            family = ('tabular', 'retrieval', 'classification')[i // 3]
            m, a = ((2, 2), (3, 2), (2, 3))[i % 3]
            row['case_id'] = f'recovery-v2-heldout-{family}-m{m}-a{a}-{i}'

    def test_inline_citations_and_real_person_bibliography(self):
        self.paper['sections'][0]['text'] = 'By [[citet:' + SOURCE_IDS[0] + ']], then another clause.'
        with tempfile.TemporaryDirectory() as root:
            tex = render_publication(root, self.paper, self.sources, self.evidence).read_text()
            bib = (Path(root) / 'references.bib').read_text()
            self.assertIn(r'By \citet{arxiv260711098v1}, then', tex)
            self.assertIn(r'claim \citep{arxiv260711098v1}.', tex)
            self.assertIn('author = {Mazumder, Aritra and Lia, Nusrat Jahan}', bib)
            self.assertNotIn('{Aritra Mazumder}', bib)
            self.assertEqual(tex.count(r'\begin{table}'), 2)
            self.assertEqual(tex.count(r'\caption{'), 2)
            self.assertIn(r'\label{tab:scenario}', tex)
            self.assertIn('Tabular (2, 2)', tex)
            for unwanted in ('Case mapping:', 'Rendering mode:', 'Self-authored structural holdout study',
                             'recovery-v2-heldout-', 'Study scope and limitations:', 'References:'):
                self.assertNotIn(unwanted, tex)
            self.assertIn(r'\lhead{}', tex)
            self.assertIn(r'\setlength{\bibsep}{0pt}', tex)
            self.assertEqual(tex.count(r'\citep{'), 4)  # Only markers, never section-end dumps.

    def test_markers_must_exactly_match_section_sources(self):
        edits = [lambda p: p['sections'][0].update(text='No marker here.'),
                 lambda p: p['sections'][0].update(text='Unknown [[cite:arxiv:9999.12345v1]].'),
                 lambda p: p['sections'][0].update(text='Broken [[cite:abc]].'),
                 lambda p: p['sections'][0].update(text='Broken [[cita:arxiv:2607.11098v1]].'),
                 lambda p: p['sections'][0].update(source_ids=list(SOURCE_IDS)),
                 lambda p: p['sections'][0].update(text='Bare arxiv:2607.11098v1.'),
                 lambda p: p.update(abstract='Citation [[cite:' + SOURCE_IDS[0] + ']].')]
        for edit in edits:
            with self.subTest(edit=edit), tempfile.TemporaryDirectory() as root:
                paper = copy.deepcopy(self.paper)
                edit(paper)
                with self.assertRaises(ValueError):
                    render_publication(root, paper, self.sources, self.evidence)
                self.assertFalse(list(Path(root).iterdir()))

    def test_internal_paths_and_adapter_diagnostics_fail_closed(self):
        for bad in ('replay_runs/live-old', 'this adapter', 'Rendering mode: live'):
            paper = copy.deepcopy(self.paper)
            paper['sections'][0]['text'] += ' ' + bad
            with self.assertRaises(ValueError):
                validate_publication(paper, self.sources, self.evidence)

    def test_tex_escaping_does_not_execute_manuscript_or_metadata(self):
        attack = r'\input{/tmp/private}%&_'
        self.paper['sections'][0]['text'] += ' ' + attack
        self.sources[SOURCE_IDS[0]]['title'] = attack
        with tempfile.TemporaryDirectory() as root:
            tex = render_publication(root, self.paper, self.sources, self.evidence).read_text()
            bib = (Path(root) / 'references.bib').read_text()
            self.assertNotIn(r'\input{', tex + bib)
            self.assertIn(r'\textbackslash{}input\{', tex + bib)

    def test_result_consistency_and_version_metadata_checked_before_writing(self):
        self.evidence['paired_base_instances'][0]['policies']['A']['tool_calls'] = 999
        with self.assertRaises(ValueError):
            validate_publication(self.paper, self.sources, self.evidence)
        self.setUp()
        self.sources[SOURCE_IDS[0]]['url'] = 'https://arxiv.org/abs/2607.11098v3'
        with self.assertRaises(ValueError):
            validate_publication(self.paper, self.sources, self.evidence)


if __name__ == '__main__':
    unittest.main()
