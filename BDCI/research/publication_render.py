"""Publication renderer with claim-local citations and checked numeric tables.

This separate renderer leaves historical, profile-bound writing artifacts intact.
It validates citation placement syntax, not whether a source supports a claim.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

try:
    from .paper_contracts import SECTION_IDS, validate_paper
    from .paper_render import SECTION_NAMES, STYLE_FILES, TEMPLATE, tex_escape
    from .recovery_v2_paper_render import _tables
except ImportError:
    from paper_contracts import SECTION_IDS, validate_paper
    from paper_render import SECTION_NAMES, STYLE_FILES, TEMPLATE, tex_escape
    from recovery_v2_paper_render import _tables

SOURCE_IDS = ('arxiv:2607.11098v1', 'arxiv:2608.12761v1', 'arxiv:2604.16706v1')
AUTHOR_NAMES = {'Aritra Mazumder': 'Mazumder, Aritra', 'Nusrat jahan Lia': 'Lia, Nusrat Jahan',
                'Nusrat Jahan Lia': 'Lia, Nusrat Jahan', 'Jesus Salas': 'Salas, Jesus', 'Bhaskar Gurram': 'Gurram, Bhaskar'}
MARKER = re.compile(r'\[\[(cite|citet):(arxiv:\d{4}\.\d{4,5}v\d+)\]\]')
INTERNAL = re.compile(r'replay_runs/|replay_paper_runs/|submission_runs/|recovery_v2_runs/|this adapter|rendering mode|supplied reading notes|supplied notes', re.I)
CASE = re.compile(r'recovery-v2-heldout-(tabular|retrieval|classification)-m(\d+)-a(\d+)-\d+')


def _clean(text):
    if INTERNAL.search(text):
        raise ValueError('internal_workflow_text_in_manuscript')


def _inline(text, keys, *, markdown=False):
    """Escape ordinary prose; only validated citation markers become TeX commands."""
    if re.search(r'arxiv\s*:', MARKER.sub('', text), re.I):
        raise ValueError('bare_arxiv_id_in_prose')
    output, cursor, refs = [], 0, set()
    for match in MARKER.finditer(text):
        prefix = text[cursor:match.start()]
        if '[[' in prefix or ']]' in prefix:
            raise ValueError('unresolved_citation_marker')
        ref = match[2]
        if ref not in keys:
            raise ValueError('unknown_citation_id:' + ref)
        output.append(prefix if markdown else tex_escape(prefix))
        command = 'citep' if match[1] == 'cite' else 'citet'
        output.append('[' + ref + ']' if markdown else '\\' + command + '{' + keys[ref] + '}')
        refs.add(ref)
        cursor = match.end()
    tail = text[cursor:]
    if '[[' in tail or ']]' in tail:
        raise ValueError('unresolved_citation_marker')
    output.append(tail if markdown else tex_escape(tail))
    return ''.join(output), refs


def _bibliography(sources, cited):
    keys, bib, md = {}, [], []
    for ref in sorted(cited):
        if ref not in cited:
            continue
        if not re.fullmatch(r'arxiv:\d{4}\.\d{4,5}v\d+', ref):
            raise ValueError('unsupported_citation_id')
        source = sources[ref]
        if source.get('url') != 'https://arxiv.org/abs/' + ref.removeprefix('arxiv:'):
            raise ValueError('source_version_url_mismatch')
        names = source.get('authors', [])
        if not names or any(not isinstance(name, str) or len(name.split()) < 2 for name in names):
            raise ValueError('unverified_author_name')
        year = source.get('year')
        if type(year) is not int or not 2020 <= year <= 2030 or not isinstance(source.get('title'), str) or not source['title'].strip():
            raise ValueError('invalid_source_metadata')
        def bib_author(name):
            if name in AUTHOR_NAMES:
                return AUTHOR_NAMES[name]
            given, family = name.rsplit(' ', 1)
            return family + ', ' + given
        key = 'arxiv' + ref.removeprefix('arxiv:').replace('.', '')
        keys[ref] = key
        # Braces protect title capitalization; individual people must remain parseable names.
        bib.append('@misc{' + key + ',\n  title = {{' + tex_escape(source['title']) + '}},\n  author = {' +
                   ' and '.join(tex_escape(bib_author(n)) for n in names) + '},\n  year = {' + str(year) + '},\n  note = {arXiv preprint arXiv:' +
                   ref.removeprefix('arxiv:') + '},\n  url = {' + source['url'] + '}\n}')
        md.append('- ' + '; '.join(names) + '. (' + str(year) + '). ' + source['title'] + '. ' + source['url'])
    return keys, bib, md


def _prepare(paper, sources, evidence):
    validate_paper(paper, sources, max_words=None, max_field_chars=None)
    cited = {ref for sec in paper['sections'] for ref in sec['source_ids']}
    if not cited <= set(sources):
        raise ValueError('unknown_citation_id')
    keys, bibliography, references = _bibliography(sources, cited)
    for field in ('title', 'abstract'):
        _clean(paper[field])
        _, refs = _inline(paper[field], keys)
        if refs:
            raise ValueError('title_abstract_must_be_citation_free')
    sections = {}
    for sec in paper['sections']:
        _clean(sec['text'])
        body, refs = _inline(sec['text'], keys)
        if refs != set(sec['source_ids']):
            raise ValueError('section_citation_marker_mismatch:' + sec['id'])
        sections[sec['id']] = (body, _inline(sec['text'], keys, markdown=True)[0])
    main, paired, cases = _tables(evidence)
    for row, case in zip(paired, cases):
        match = CASE.fullmatch(case)
        if not match:
            raise ValueError('invalid_publication_case_id')
        row[0] = match[1].capitalize() + ' (' + match[2] + ', ' + match[3] + ')'
    resource = evidence['resource']
    for name in ('model_calls', 'total_tokens'):
        if type(resource[name]) is not int or resource[name] < 0:
            raise ValueError('invalid_resource_' + name)
    return keys, bibliography, references, sections, main, paired, resource


def validate_publication(paper, sources, evidence):
    """Validate inputs without writing files (does not certify claim semantics)."""
    _prepare(paper, sources, evidence)


def render_publication(root, paper, sources, evidence):
    """Write official ICLR-style paper.tex/md/bib; return the TeX Path.

    Each section's source_ids must equal the set of inline [[cite:ID]] or
    [[citet:ID]] markers. Title/abstract must be citation-free. No API is used.
    """
    keys, bibliography, references, sections, main, paired, resource = _prepare(paper, sources, evidence)
    tex = [r'\documentclass{article}', r'\usepackage[T1]{fontenc}',
           r'\usepackage{iclr2026_conference,times}', r'\usepackage{url}', r'\iclrfinalcopy',
           r'\title{' + tex_escape(paper['title']) + '}', r'\author{Anonymous authors}',
           r'\begin{document}', r'\maketitle',
           # Neither publication nor ICLR review has occurred; suppress template status header.
           r'\lhead{}', r'\begin{abstract}', tex_escape(paper['abstract']), r'\end{abstract}']
    md = ['# ' + paper['title'], '## Abstract', paper['abstract']]

    def table(caption, label, headers, rows, columns):
        tex.extend([r'\begin{table}[t]', r'\centering',
                    r'\caption{' + tex_escape(caption) + '}', r'\label{' + label + '}',
                    r'{\footnotesize\setlength{\tabcolsep}{3pt}', r'\begin{tabular}{' + columns + r'}\hline',
                    ' & '.join(tex_escape(h) for h in headers) + r' \\\hline',
                    *[' & '.join(tex_escape(c) for c in row) + r' \\' for row in rows],
                    r'\hline\end{tabular}}', r'\end{table}'])
        md.extend([caption, '| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |',
                   *['| ' + ' | '.join(row) + ' |' for row in rows]])

    for sid in SECTION_IDS:
        if sid == 'discussion':
            tex.append(r'\section{Results}')
            md.append('## Results')
            note = ('The nine base instances are the paired statistical units; the 180 policy executions are not independent samples. '
                    'Correct denotes a numerically correct completion. Noncompletion includes invalid or refused plans. '
                    'Stale denotes a completed output with outdated source provenance, counted separately from correctness. '
                    'Tool calls count recovery execution only and exclude shared initial-cache construction.')
            tex.append(tex_escape(note) + '\n\n' + r'Table~\ref{tab:scenario} reports each scenario; Table~\ref{tab:paired} aggregates the four scenarios per instance.')
            md.append(note)
            table('Scenario results. Each row contains nine episodes. Noncomp. denotes noncompletion; calls count recovery tool invocations.',
                  'tab:scenario', ['Scenario', 'Policy', 'n', 'Correct', 'Wrong', 'Noncomp.', 'Calls', 'Stale'], main, 'llrrrrrr')
            table('Paired results. Instance labels give task family and topology (m, a), the numbers of main and auxiliary shards. '
                  'Policy cells show correct/episodes; calls. The final columns give E minus A differences in correct completions and calls.',
                  'tab:paired', ['Instance', 'A', 'D', 'E', 'F', 'G', 'Diff. correct', 'Diff. calls'], paired, 'llllllrr')
            note = (f"Study planning used {resource['model_calls']:,} model calls and {resource['total_tokens']:,} tokens; "
                    'these figures exclude development and manuscript preparation.')
            tex.append(tex_escape(note))
            md.append(note)
        tex.extend([r'\section{' + SECTION_NAMES[sid] + '}', sections[sid][0]])
        md.extend(['## ' + SECTION_NAMES[sid], sections[sid][1]])
    tex.extend([r'\bibliographystyle{iclr2026_conference}', r'\bibliography{references}', r'\end{document}'])
    md.extend(['## References', *references])
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name in STYLE_FILES:
        shutil.copyfile(TEMPLATE / name, root / name)
    for name, chunks in (('paper.tex', tex), ('paper.md', md), ('references.bib', bibliography)):
        (root / name).write_text('\n\n'.join(chunks) + '\n', encoding='utf-8')
    return root / 'paper.tex'
