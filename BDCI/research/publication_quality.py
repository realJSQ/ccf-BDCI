"""Deterministic post-render diagnostics; never edits a model-written paper."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


NARRATIVE = re.compile(r'\[\[citet:(arxiv:\d{4}\.\d{4,5}v\d+)\]\]\s+([A-Za-z]+)')
PLURAL_VERBS = frozenset(('study', 'examine', 'present', 'introduce', 'build', 'report',
                          'show', 'argue', 'find', 'describe', 'note', 'survey',
                          'discuss', 'use', 'propose', 'compare', 'separate'))
SINGULAR_VERBS = frozenset(('studies', 'examines', 'presents', 'introduces', 'builds',
                            'reports', 'shows', 'argues', 'finds', 'describes',
                            'notes', 'surveys', 'discusses', 'uses', 'proposes',
                            'compares', 'separates'))


def narrative_citation_findings(paper: dict, sources: dict) -> list[dict]:
    """Report obvious author-number/verb mismatches before PDF rendering."""
    findings = []
    for section in paper['sections']:
        for match in NARRATIVE.finditer(section['text']):
            ref, verb = match.groups()
            authors = sources.get(ref, {}).get('authors', [])
            if not authors:
                continue
            if ((len(authors) == 1 and verb.casefold() in PLURAL_VERBS)
                    or (len(authors) > 1 and verb.casefold() in SINGULAR_VERBS)):
                findings.append({'code': 'narrative_citation_verb_agreement',
                                 'section_id': section['id'], 'source_id': ref,
                                 'verb': verb})
    return findings


def audit_publication(paper: dict, sources: dict, pdf_path: Path) -> dict:
    """Flag mechanically detectable citation/layout defects, not claim truth."""
    findings = narrative_citation_findings(paper, sources)
    cited = {ref for section in paper['sections'] for ref in section['source_ids']}
    for ref in sorted(cited):
        source = sources[ref]
        if (source.get('verification_status') != 'primary_fulltext'
                or len(source.get('primary_text_excerpt', '')) < 4000):
            findings.append({'code': 'cited_source_lacks_primary_excerpt', 'source_id': ref})
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(str(pdf_path))
    counts = []
    for page in document:
        textpage = page.get_textpage()
        counts.append(len(textpage.get_text_range().strip()))
        textpage.close()
        page.close()
    document.close()
    if len(counts) > 1 and counts[-1] < 700:
        findings.append({'code': 'sparse_last_page', 'page': len(counts),
                         'text_chars': counts[-1]})
    return {'schema': 'publication_quality/1', 'pages': len(counts),
            'page_text_chars': counts, 'cited_sources': len(cited),
            'primary_verified_cited_sources': sum(
                sources[ref].get('verification_status') == 'primary_fulltext' for ref in cited),
            'findings': findings,
            'scope': 'Mechanical grammar, primary-excerpt presence, and page occupancy only; no semantic citation certification.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    args = parser.parse_args(argv)
    root = args.run.resolve()
    report = audit_publication(json.loads((root / 'paper.json').read_text()),
                               json.loads((root / 'sources.json').read_text()),
                               root / 'paper.pdf')
    (root / 'quality_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'pages': report['pages'], 'cited_sources': report['cited_sources'],
                      'findings': report['findings']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
