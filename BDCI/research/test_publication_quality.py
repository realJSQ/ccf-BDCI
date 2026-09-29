import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

try:
    from .publication_quality import audit_publication
except ImportError:
    from publication_quality import audit_publication


class _Page:
    def __init__(self, text): self.text = text
    def get_textpage(self): return SimpleNamespace(get_text_range=lambda: self.text, close=lambda: None)
    def close(self): pass


class _Document:
    def __init__(self, _): self.pages = [_Page('a' * 2000), _Page('b' * 300)]
    def __iter__(self): return iter(self.pages)
    def close(self): pass


class PublicationQualityTests(unittest.TestCase):
    def test_flags_narrative_grammar_missing_primary_evidence_and_sparse_page(self):
        paper = {'sections': [{'id': 'related_work',
            'text': '[[citet:arxiv:2604.16706v1]] study the question. '
                    '[[citet:arxiv:2608.10502v1]] presents a method.',
            'source_ids': ['arxiv:2604.16706v1', 'arxiv:2608.10502v1']}]}
        sources = {'arxiv:2604.16706v1': {'authors': ['Bhaskar Gurram'],
                    'verification_status': 'primary_fulltext', 'primary_text_excerpt': 'x' * 4000},
                   'arxiv:2608.10502v1': {'authors': ['Caili Yu', 'Yiqi Wang']}}
        with patch.dict(sys.modules, {'pypdfium2': SimpleNamespace(PdfDocument=_Document)}):
            audit = audit_publication(paper, sources, Path('/unused.pdf'))
        self.assertEqual(audit['pages'], 2)
        self.assertEqual(audit['primary_verified_cited_sources'], 1)
        self.assertEqual([x['code'] for x in audit['findings']],
                         ['narrative_citation_verb_agreement',
                          'narrative_citation_verb_agreement',
                          'cited_source_lacks_primary_excerpt', 'sparse_last_page'])


if __name__ == '__main__':
    unittest.main()
