"""Render versioned recovery-v2 evidence; numeric tables never come from prose."""
from __future__ import annotations

import math
import shutil
from pathlib import Path

try:
    from .paper_contracts import SECTION_IDS, validate_paper
    from .paper_render import SECTION_NAMES, STYLE_FILES, TEMPLATE, tex_escape
    from .replay_paper_render import _bibliography
    from .recovery_v2_paper_evidence import SCHEMA, POLICIES, SCENARIOS
except ImportError:
    from paper_contracts import SECTION_IDS, validate_paper
    from paper_render import SECTION_NAMES, STYLE_FILES, TEMPLATE, tex_escape
    from replay_paper_render import _bibliography
    from recovery_v2_paper_evidence import SCHEMA, POLICIES, SCENARIOS

NOTICE = 'Self-authored structural holdout study'


def _count(value, label):
    if type(value) is not int or value < 0:
        raise ValueError('invalid_' + label)
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('invalid_' + label)
    return value.strip()


def _tables(evidence):
    if evidence.get('schema') != SCHEMA or evidence.get('study_kind') != 'recovery_v2':
        raise ValueError('recovery_v2_evidence_required')
    if evidence.get('base_instance_count') != 9:
        raise ValueError('invalid_base_instance_count')
    indexed = {}
    for row in evidence['summary_by_scenario_policy']:
        pair = (row['scenario'], row['policy'])
        if pair in indexed or pair[0] not in SCENARIOS or pair[1] not in POLICIES:
            raise ValueError('invalid_result_matrix')
        values = [_count(row[k], k) for k in ('episodes', 'correct_completion', 'wrong_completion', 'refusal', 'tool_calls', 'stale_completed')]
        n, correct, wrong, noncompletion, calls, stale = values
        if n != evidence['base_instance_count'] or correct + wrong + noncompletion != n or stale > correct + wrong:
            raise ValueError('inconsistent_outcomes')
        indexed[pair] = values
    if set(indexed) != {(s, p) for s in SCENARIOS for p in POLICIES}:
        raise ValueError('incomplete_result_matrix')
    paired, case_keys, totals = [], [], {p: [0, 0, 0] for p in POLICIES}
    for i, row in enumerate(evidence['paired_base_instances'], 1):
        case_id = _text(row['case_id'], 'case_id')
        if case_id in case_keys or set(row['policies']) != set(POLICIES):
            raise ValueError('invalid_paired_cases')
        case_keys.append(case_id)
        cells = [str(i)]
        for p in POLICIES:
            cell = row['policies'][p]
            n, correct, calls = [_count(cell[k], k) for k in ('episodes', 'correct', 'tool_calls')]
            if n != len(SCENARIOS) or correct > n:
                raise ValueError('invalid_paired_denominator')
            totals[p] = [a + b for a, b in zip(totals[p], (n, correct, calls))]
            cells.append(f'{correct}/{n}; {calls}')
        for metric in ('correct', 'tool_calls'):
            difference = row['policies']['E'][metric] - row['policies']['A'][metric]
            observed = row['E_minus_A_' + metric]
            if type(observed) is not int or observed != difference:
                raise ValueError('invalid_paired_difference')
            cells.append(str(difference))
        paired.append(cells)
    if len(paired) != evidence['base_instance_count']:
        raise ValueError('incomplete_paired_cases')
    for p in POLICIES:
        expected = [sum(indexed[s, p][k] for s in SCENARIOS) for k in (0, 1, 4)]
        if totals[p] != expected:
            raise ValueError('paired_summary_mismatch')
    plans = evidence['base_instance_count'] * len(SCENARIOS)
    for key, expected in (('completed_model_plans', plans), ('paired_model_policy_replays', plans * 4),
                          ('deterministic_g_replays', plans), ('completed_policy_replays', plans * 5)):
        if type(evidence.get(key)) is not int or evidence[key] != expected:
            raise ValueError('invalid_' + key)
    main = [[s.replace('_', ' '), p, *map(str, indexed[s, p])] for s in SCENARIOS for p in POLICIES]
    return main, paired, case_keys


def render_recovery_v2_paper(root: Path, paper: dict, sources: dict, evidence: dict, mode: str) -> Path:
    """Render verified v2 evidence. Structural checks do not certify prose claims."""
    validate_paper(paper, sources, max_words=None, max_field_chars=None)
    mode = _text(mode, 'mode')
    main, paired, case_keys = _tables(evidence)
    keys, bibliography, references = _bibliography(paper, sources)
    resources = []
    for key in ('model_calls', 'total_tokens', 'duration_seconds', 'initial_cache_tool_calls', 'cost'):
        value = evidence['resource'][key]
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise ValueError('invalid_resource_' + key)
        resources.append(key.replace('_', ' ') + ': ' + ('unavailable' if value is None else (f'{value:.3f}' if key == 'duration_seconds' else str(value))))
    resources.append(_text(evidence['resource']['duration_scope'], 'duration_scope'))
    if set(evidence['policies']) != set(POLICIES):
        raise ValueError('invalid_policy_labels')
    policy_text = ' '.join(p + ': ' + _text(evidence['policies'][p], 'policy_label') for p in POLICIES)
    assistance = _text(evidence['development_assistance']['description'], 'development_assistance')
    information = _text(evidence['information_condition'], 'information_condition')
    limitations = [_text(item, 'limitation') for item in evidence['limitations']]
    limitations = [item.replace('Report E versus A and G as well as F;',
                  'Comparisons include E versus A and G as well as F;') for item in limitations]
    if not limitations:
        raise ValueError('missing_limitations')
    note = (f"{evidence['completed_model_plans']} saved model plans are shared by A/D/E/F, yielding "
            f"{evidence['paired_model_policy_replays']} model-policy replays. G requires zero model calls and "
            f"has {evidence['deterministic_g_replays']} separate deterministic executions. The "
            f"{evidence['completed_policy_replays']} executions are not independent samples; "
            f"{evidence['base_instance_count']} base instances are the paired units. Calls exclude shared initial-cache "
            'construction. Noncompletion includes malformed plans and does not imply voluntary refusal. '
            'Stale counts completed outputs with outdated source provenance, separately from numerical correctness.')
    tex = [r'\documentclass{article}', r'\usepackage[T1]{fontenc}', r'\usepackage{iclr2026_conference,times}',
           r'\usepackage{url}', r'\iclrfinalcopy', r'\title{' + tex_escape(paper['title']) + '}',
           r'\author{Anonymous authors}', r'\begin{document}', r'\maketitle',
           r'\lhead{' + tex_escape(NOTICE) + '}', r'\begin{abstract}', tex_escape(paper['abstract']), r'\end{abstract}']
    md = ['# ' + paper['title'], '**' + NOTICE + '**', 'Anonymous authors.', '## Abstract', paper['abstract']]
    sections = {s['id']: s for s in paper['sections']}

    def table(title, headers, rows, columns):
        tex.extend([r'\noindent\begin{minipage}{\linewidth}', r'\paragraph{' + tex_escape(title) + '}',
                    r'\begin{center}{\footnotesize\setlength{\tabcolsep}{3pt}\begin{tabular}{' + columns + r'}\hline',
                    ' & '.join(tex_escape(h) for h in headers) + r' \\\hline',
                    *[' & '.join(tex_escape(c) for c in row) + r' \\' for row in rows],
                    r'\hline\end{tabular}}\end{center}\end{minipage}\par\medskip'])
        md.extend(['### ' + title, '| ' + ' | '.join(headers) + ' |\n|' + '|'.join(['---'] * len(headers)) + '|\n' +
                   '\n'.join('| ' + ' | '.join(row) + ' |' for row in rows)])

    for sid in SECTION_IDS:
        if sid == 'discussion':
            tex.extend([r'\section{Results}', tex_escape('Rendering mode: ' + mode + '. ' + policy_text)])
            md.extend(['## Results', 'Rendering mode: ' + mode + '. ' + policy_text])
            table('Scenario-by-policy results', ['Scenario', 'Policy', 'n', 'Correct', 'Wrong', 'Noncompl.', 'Calls', 'Stale'], main, 'llrrrrrr')
            table('Paired base-instance results', ['Case', 'A', 'D', 'E', 'F', 'G', 'E-A correct', 'E-A calls'], paired, 'rlllllrr')
            paired_note = 'Each policy cell is correct/episodes; calls, aggregated over the four scenarios. Differences are paired raw counts, not significance tests.'
            mapping = 'Case mapping: ' + '; '.join(f'{i}: {case}' for i, case in enumerate(case_keys, 1)) + '.'
            for paragraph in (paired_note, mapping, note, information, assistance, 'Study scope and limitations: ' + ' '.join(limitations),
                              'Recorded study resources: ' + '; '.join(resources)):
                tex.append(tex_escape(paragraph))
                md.append(paragraph)
        section = sections[sid]
        tex.extend([r'\section{' + SECTION_NAMES[sid] + '}', tex_escape(section['text'])])
        md.extend(['## ' + SECTION_NAMES[sid], section['text']])
        if section['source_ids']:
            cite = ','.join(keys[s] for s in section['source_ids'])
            tex.append(r'\citep{' + cite + '}.')
            md.append('References: ' + cite)
    tex.extend([r'\bibliographystyle{iclr2026_conference}', r'\bibliography{references}', r'\end{document}'])
    md.extend(['## References', *references])
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name in STYLE_FILES:
        shutil.copyfile(TEMPLATE / name, root / name)
    for name, chunks in (('paper.tex', tex), ('paper.md', md), ('references.bib', bibliography)):
        (root / name).write_text('\n\n'.join(chunks) + '\n', encoding='utf-8')
    return root / 'paper.tex'


def render(root, manuscript, evidence, sources, mode='live'):
    return render_recovery_v2_paper(root, manuscript, sources, evidence, mode)
