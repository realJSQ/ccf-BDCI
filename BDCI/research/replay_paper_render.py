"""Safe ICLR rendering of separate original and post-hoc development evidence.

Numeric tables are provided by the evidence builder, not model prose. Structural
validation here is not independent reproduction or scientific claim verification.
"""
from __future__ import annotations

import math
import shutil
from pathlib import Path

try:
    from .paper_contracts import SECTION_IDS, validate_paper
    from .paper_render import SECTION_NAMES, STYLE_FILES, TEMPLATE, tex_escape
except ImportError:
    from paper_contracts import SECTION_IDS, validate_paper
    from paper_render import SECTION_NAMES, STYLE_FILES, TEMPLATE, tex_escape

NOTICE = 'Development study / internal draft'
LIMITATION = ('These are descriptive results on self-authored development instances. '
              'Shared model plans and repeated policies are not independent samples. '
              'The post-hoc compatibility replay reuses saved plans and is not a new model experiment '
              'or a preregistered result. Neither table establishes generalization, statistical '
              'equivalence, algorithmic novelty, or competition submission readiness.')
POLICIES = ('A', 'B', 'C', 'D')
SCENARIOS = ('clean', 'update', 'incomplete_lineage')


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('invalid_' + label)
    return value.strip()


def _count(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError('invalid_' + label)
    return value


def _rows(summary, label):
    rows = summary.get('summary_by_scenario_policy')
    if not isinstance(rows, list):
        raise ValueError('invalid_' + label + '_rows')
    indexed = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('invalid_result_row')
        pair = (row.get('scenario'), row.get('policy'))
        if pair[0] not in SCENARIOS or pair[1] not in POLICIES or pair in indexed:
            raise ValueError('invalid_or_duplicate_result_key')
        numbers = [_count(row.get(key), key) for key in
                   ('episodes', 'correct_completion', 'wrong_completion', 'refusal', 'tool_calls')]
        if numbers[0] <= 0 or sum(numbers[1:4]) != numbers[0]:
            raise ValueError('inconsistent_outcome_counts')
        indexed[pair] = [pair[0].replace('_', ' '), pair[1], *map(str, numbers)]
    if set(indexed) != {(s, p) for s in SCENARIOS for p in POLICIES}:
        raise ValueError('incomplete_result_matrix')
    for scenario in SCENARIOS:
        if len({indexed[(scenario, p)][2] for p in POLICIES}) != 1:
            raise ValueError('unpaired_policy_denominators')
    return [indexed[(s, p)] for s in SCENARIOS for p in POLICIES]


def _bibliography(paper, sources):
    cited = list(dict.fromkeys(ref for section in paper['sections'] for ref in section['source_ids']))
    keys = {ref: f'ref{i:04d}' for i, ref in enumerate(cited, 1)}
    bib, markdown = [], []
    for ref in cited:
        source = sources[ref]
        title = _text(source.get('title'), 'source_title')
        authors = source.get('authors')
        if not isinstance(authors, list) or not authors or any(not isinstance(a, str) or not a.strip() for a in authors):
            raise ValueError('missing_or_invalid_source_authors')
        year = source.get('year')
        if type(year) is not int or not 1000 <= year <= 3000:
            raise ValueError('missing_or_invalid_source_year')
        url = _text(source.get('url'), 'source_url')
        fields = ['title = {{' + tex_escape(title) + '}}',
                  'author = {' + ' and '.join('{' + tex_escape(a) + '}' for a in authors) + '}',
                  'year = {' + str(year) + '}', 'note = {' + tex_escape(url) + '}']
        bib.append('@misc{' + keys[ref] + ',\n  ' + ',\n  '.join(fields) + '\n}')
        markdown.append(f'- [{keys[ref]}] {title}. {"; ".join(authors)}. {year}. {url}')
    return keys, bib, markdown


def render_replay_paper(root: Path, paper: dict, sources: dict, evidence: dict, mode: str) -> Path:
    """Write paper.tex/md, references.bib and official style files.

    evidence contains strict/posthoc summaries, each with a complete
    summary_by_scenario_policy matrix, and optionally resource and policy_labels.
    The caller must independently verify the saved evidence before rendering.
    """
    validate_paper(paper, sources)
    mode = _text(mode, 'mode')
    strict = _rows(evidence['strict'], 'strict')
    posthoc = _rows(evidence['posthoc'], 'posthoc')
    if [r[:3] for r in strict] != [r[:3] for r in posthoc]:
        raise ValueError('strict_posthoc_denominator_mismatch')
    keys, bib, refs = _bibliography(paper, sources)
    policy_labels = evidence.get('policy_labels', {})
    if not isinstance(policy_labels, dict) or set(policy_labels) - set(POLICIES):
        raise ValueError('invalid_policy_labels')
    labels = '; '.join(p + ': ' + _text(policy_labels[p], 'policy_label') for p in POLICIES if p in policy_labels)
    resource = evidence.get('resource', {})
    if not isinstance(resource, dict):
        raise ValueError('invalid_resource')
    resources = []
    for key in ('model_calls', 'total_tokens', 'duration_seconds', 'cost', 'writing_model_calls', 'writing_total_tokens'):
        if key not in resource:
            continue
        value = resource[key]
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise ValueError('invalid_resource_' + key)
        resources.append(key.replace('_', ' ') + ': ' + ('unavailable' if value is None else str(value)))
    if 'changed_plan_count' in evidence['posthoc']:
        changed = _count(evidence['posthoc']['changed_plan_count'], 'changed_plan_count')
        resources.append('post-hoc plans changed: ' + str(changed))
    reasons = evidence['strict'].get('noncompletion_reasons', {})
    if not isinstance(reasons, dict):
        raise ValueError('invalid_strict_noncompletion_reasons')
    reason_text = '; '.join(_text(reason, 'noncompletion_reason') + ': ' +
                            str(_count(count, 'noncompletion_reason_count')) for reason, count in reasons.items())
    if sum(reasons.values()) > sum(int(row[5]) for row in strict if row[1] == 'A'):
        raise ValueError('noncompletion_reasons_exceed_original_plan_noncompletion')
    resource_text = '; '.join(resources) or 'See the separate run ledgers for recorded resource usage.'
    title = paper['title']
    tex = [r'\documentclass{article}', r'\usepackage[T1]{fontenc}',
           r'\usepackage{iclr2026_conference,times}', r'\usepackage{url}', r'\iclrfinalcopy',
           r'\title{' + tex_escape(title) + r'\\[0.4em]{\small ' + tex_escape(NOTICE) + '}}',
           r'\author{Anonymous authors}', r'\begin{document}', r'\maketitle',
           r'\lhead{Development study / internal draft}', r'\begin{abstract}',
           tex_escape(paper['abstract']), r'\end{abstract}']
    md = ['# ' + title, '**' + NOTICE + '**', 'Anonymous authors.', '## Abstract', paper['abstract']]
    section_map = {s['id']: s for s in paper['sections']}
    for sid in SECTION_IDS:
        if sid == 'discussion':
            tex += [r'\section{Results}', tex_escape('Rendering mode: ' + mode + '. ' + labels)]
            md += ['## Results', 'Rendering mode: ' + mode + '. ' + labels]
            for caption, rows in (('Original strict execution', strict),
                                  ('Post-hoc compatibility replay (not preregistered)', posthoc)):
                tex += [r'\paragraph{' + tex_escape(caption) + '}', r'\begin{center}',
                        r'{\footnotesize\setlength{\tabcolsep}{3pt}\begin{tabular}{llrrrrr}\hline',
                        r'Scenario & Policy & $n$ & Correct & Wrong & Noncompletion & Calls \\\hline',
                        *[' & '.join(tex_escape(v) for v in row) + r' \\' for row in rows],
                        r'\hline\end{tabular}}\end{center}']
                md += ['### ' + caption, '| Scenario | Policy | n | Correct | Wrong | Noncompletion | Calls |\n'
                       '|---|---|---:|---:|---:|---:|---:|\n' + '\n'.join('| ' + ' | '.join(r) + ' |' for r in rows)]
            note = ('Calls count replay tool executions; cached initial construction is shared and excluded. '
                    'The two tables reuse the same model plans. Noncompletion includes malformed plan outputs and does not imply voluntary refusal. ' + LIMITATION)
            if reason_text:
                note += ' Original noncompletion reasons counted once per model-plan episode: ' + reason_text + '.'
            tex += [tex_escape(note), r'\paragraph{Recorded study resources.}' + tex_escape(resource_text)]
            md += [note, 'Recorded study resources: ' + resource_text]
        section = section_map[sid]
        tex += [r'\section{' + SECTION_NAMES[sid] + '}', tex_escape(section['text'])]
        md += ['## ' + SECTION_NAMES[sid], section['text']]
        if section['source_ids']:
            cite = ','.join(keys[i] for i in section['source_ids'])
            tex += [r'\citep{' + cite + '}.']
            md += ['References: ' + cite]
    tex += [r'\bibliographystyle{iclr2026_conference}', r'\bibliography{references}', r'\end{document}']
    md += ['## References', *refs]
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name in STYLE_FILES:
        shutil.copyfile(TEMPLATE / name, root / name)
    for name, chunks in (('paper.tex', tex), ('paper.md', md), ('references.bib', bib)):
        (root / name).write_text('\n\n'.join(chunks) + '\n', encoding='utf-8')
    return root / 'paper.tex'
