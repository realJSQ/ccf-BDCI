"""Render a model-reviewed manuscript and package its auditable submission materials.

This tool never changes manuscript prose and never calls a model. The external
review token is included only when it is explicitly bound to the final PDF.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from build_replay_bundle import validate_team_name
from paper_bundle import BASE_SHA, SECRET_PATTERN, STYLE_FILES
from publication_quality import audit_publication
from publication_render import render_publication
from replay_paper_evidence import digest
from run_replay_paper import compile_pdf
from run_topics import parse_object, write_json

HERE = Path(__file__).resolve().parent
BDCI = HERE.parent
TEAM = '真没招了'
IGNORED_RUN_SUFFIXES = {'.lock', '.wal', '.png', '.blg', '.log'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_copy(src, dest, base):
    src, dest, base = Path(src), Path(dest), Path(base)
    if src.is_symlink() or not src.is_file() or not src.resolve().is_relative_to(base.resolve()):
        raise ValueError('unsafe_submission_source')
    data = src.read_bytes()
    if SECRET_PATTERN.search(data):
        raise ValueError('credential_like_content_in_submission:' + src.name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def validate_model_source(source):
    """Accept only the saved, twice-approved model draft, including its exact raw reply."""
    source = Path(source).resolve()
    if source.parent != (HERE / 'replay_paper_runs').resolve():
        raise ValueError('invalid_publication_source_location')
    summary, paper = read(source / 'summary.json'), read(source / 'paper.json')
    sequence = summary.get('role_sequence', [])
    if (summary['mode'] != 'live' or summary['final_internal_review'] != 'pass'
            or summary['final_internal_review_issues'] != 0
            or summary['review_rounds'] < 2 or not sequence
            or not sequence[-1].startswith('reviewer_')):
        raise ValueError('model_review_not_complete')
    current = last_manuscript_role = None
    evidence_hash = digest(read(source / 'evidence.json'))
    reviews = 0
    for role in sequence:
        saved = read(source / f'{role}.json')
        raw = parse_object((source / f'raw_{role}.txt').read_text())
        if role == 'writer' or role.startswith('reviser_'):
            if raw != saved:
                raise ValueError('manuscript_not_exact_raw_model_output')
            current, last_manuscript_role = saved, role
        elif role.startswith('reviewer_'):
            model_review_path = source / f'{role}_model.json'
            if (current is None or raw != read(model_review_path if model_review_path.exists()
                                               else source / f'{role}.json')
                    or saved['draft_sha256'] != digest(current)
                    or saved['evidence_sha256'] != evidence_hash
                    or saved['external_reviewer']):
                raise ValueError('review_target_or_raw_changed')
            reviews += 1
        else:
            raise ValueError('invalid_model_role')
    if current != paper or reviews < 2:
        raise ValueError('paper_not_final_model_revision')
    final_review = read(source / f'{sequence[-1]}.json')
    if final_review['verdict'] != 'pass' or final_review['issues']:
        raise ValueError('final_internal_review_not_clean')
    quality = audit_publication(paper, read(source / 'sources.json'), source / 'paper.pdf')
    if quality != read(source / 'quality_audit.json'):
        raise ValueError('source_quality_changed')
    if {issue['code'] for issue in quality['findings']} not in (set(), {'sparse_last_page'}):
        raise ValueError('source_has_nonlayout_findings')
    return summary, paper, last_manuscript_role


def prepare_layout(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    summary, paper, manuscript_role = validate_model_source(source)
    if output.exists():
        raise FileExistsError('layout_output_exists')
    output.mkdir(parents=True)
    evidence, sources = read(source / 'evidence.json'), read(source / 'sources.json')
    rendered = copy.deepcopy(evidence)
    model = read(source / 'model_summary.json')
    rendered['resource'].update(writing_model_calls=model['model_calls'],
                                writing_total_tokens=model['total_tokens'])
    for name in ('paper.json', 'sources.json', 'evidence.json', 'model_summary.json',
                 'model_usage.jsonl'):
        safe_copy(source / name, output / name, source)
    tex = render_publication(output, paper, sources, rendered)
    same_tex = (source / 'paper.tex').read_bytes() == tex.read_bytes()
    if same_tex:
        safe_copy(source / 'paper.pdf', output / 'paper.pdf', source)
        pdf = summary['pdf']
        if pdf['sha256'] != sha(output / 'paper.pdf'):
            raise ValueError('source_pdf_digest_changed')
    else:
        pdf = compile_pdf(output, tex, study_kind='recovery_v2')
    quality = audit_publication(paper, sources, output / 'paper.pdf')
    write_json(output / 'quality_audit.json', quality)
    if quality['findings'] or quality['pages'] > read(source / 'quality_audit.json')['pages']:
        raise ValueError('layout_not_ready')
    provenance = {'schema': 'publication_layout/1',
                  'source_run_relative': str(source.relative_to(HERE)),
                  'source_paper_sha256': sha(source / 'paper.json'),
                  'source_raw_manuscript_role': manuscript_role,
                  'source_raw_manuscript_sha256': sha(source / f'raw_{manuscript_role}.txt'),
                  'source_pdf_sha256': sha(source / 'paper.pdf'),
                  'paper_content_unchanged': sha(source / 'paper.json') == sha(output / 'paper.json'),
                  'format_change': ('none; source TeX and PDF retained byte-for-byte'
                                    if same_tex
                                    else 'natbib bibsep 0pt; ICLR style, font, margins, prose and bibliography metadata unchanged'),
                  'renderer_sha256': sha(HERE / 'publication_render.py'),
                  'final_review_sha256': sha(source / f"{summary['role_sequence'][-1]}.json"),
                  'final_pdf_sha256': pdf['sha256'],
                  'external_review_completed': False}
    write_json(output / 'layout_provenance.json', provenance)
    write_json(output / 'summary.json', {**summary, 'status': 'ready_for_external_review',
        'pdf': pdf, 'quality_finding_codes': [], 'ready_for_external_review': True,
        'external_review_completed': False, 'submission_ready': False,
        'layout_only': True, 'new_model_calls': 0})
    return output


def run_chain(source):
    current = Path(source).resolve()
    seen, result = set(), []
    while current not in seen:
        seen.add(current)
        result.append(current)
        provenance = read(current / 'input_provenance.json')
        failed = provenance.get('failed_attempt_relative')
        if failed:
            extra = (HERE / failed).resolve()
            if extra.parent != (HERE / 'replay_paper_runs').resolve():
                raise ValueError('unsafe_failed_attempt_path')
            result.append(extra)
        parent = provenance.get('source_run_relative')
        if not parent:
            return result
        current = (HERE / parent).resolve()
        if current.parent != (HERE / 'replay_paper_runs').resolve():
            raise ValueError('unsafe_model_source_path')
    raise ValueError('cyclic_manuscript_lineage')


def audited_usage(runs):
    stages = []
    for run in runs:
        if not (run / 'model_summary.json').exists():
            continue
        model = read(run / 'model_summary.json')
        rows = [json.loads(line) for line in (run / 'model_usage.jsonl').read_text().splitlines() if line.strip()]
        if (model['mode'] != 'live' or model['model_calls'] != len(rows)
                or model['total_tokens'] != sum(row['total_tokens'] for row in rows)
                or model['model_usage'] != rows):
            raise ValueError('manuscript_usage_mismatch:' + run.name)
        stages.append({'run': run.name, 'status': model['status'],
                       'model_calls': model['model_calls'], 'total_tokens': model['total_tokens'],
                       'duration_seconds': model.get('duration_seconds'),
                       'usage_sha256': sha(run / 'model_usage.jsonl')})
    return stages


def copy_tree(source, target, *, exclude_run_noise=False):
    for path in sorted(Path(source).rglob('*')):
        if path.is_symlink():
            raise ValueError('symlink_in_submission_source')
        if path.is_file():
            if exclude_run_noise and (path.suffix in IGNORED_RUN_SUFFIXES
                                      or path.suffix == '.pyc' or '__pycache__' in path.parts):
                continue
            safe_copy(path, Path(target) / path.relative_to(source), source)


def manifest_files(stage):
    return {str(path.relative_to(stage)): sha(path) for path in sorted(stage.rglob('*'))
            if path.is_file() and path.name != 'manifest.json'}


def write_submission_docs(stage, study_name, source_name, layout_sha, *, pr_url=None):
    docs = {
        'architecture.md': '''# System architecture

This submission uses the JiuwenSwarm source extension and a native team skill to
produce a short research paper. The agent selects and critiques a topic within
the agent context-engineering direction. Human development work corrected the
protocol and froze the self-authored structural holdout before the live run;
the process is not claimed to be fully autonomous.

The reproducible path is: topic and protocol roles → frozen nine-instance
recovery study → OpenAlex discovery and versioned primary-text acquisition →
model writer → bounded model reviewer/reviser loop → deterministic evidence and
inline-citation checks → ICLR LaTeX/PDF → external review. Numerical tables are
generated from saved experiment evidence, never from model-supplied table cells.

ResearchBudgetRail in the JiuwenSwarm harness records request admission and
provider usage and stops a new request after an unresolved previous attempt.
ExperimentEvidenceRail validates selected tool receipts on its integrated smoke
path. The publication roles use JiuwenSwarm SwarmFlow/TeamWorkerBackend/DeepAgent
with tools disabled; OpenAlex and PDF verification are controlled pipeline steps.
The EvidenceRail is not claimed to validate the full study or literature claims.

The selected study is `code/BDCI/research/recovery_v2_runs/''' + study_name + '''`.
The final model manuscript and its source lineage are under
`code/BDCI/research/replay_paper_runs/`. The delivered PDF is the same model
manuscript as `''' + source_name + '''`, rendered deterministically in the ICLR
template without manual prose edits. Its SHA-256 is `''' + layout_sha + '''`.
''',
        'module_call.md': '''# Module calls and reproduction

1. `run_recovery_v2.py` freezes 36 model plans and executes five matched
   policies on nine self-authored base instances with four scenarios each.
   It stores 180 CPU policy executions and provider usage.
2. `openalex_literature.py` discovers bibliographic records; primary arXiv
   texts are saved and hashed. OpenAlex metadata alone does not certify claims.
3. `run_publication_loop.py` drives the native publication-loop team skill.
   Writer, reviewer, and reviser each receive source excerpts, current evidence,
   and the relevant bound review. At least two reviews are required. Draft and
   evidence hashes bind each review; failed responses are retained without
   automatic resend. The reviewer roles use one provider, so they are internal.
4. `publication_render.py` converts only valid inline `[[cite:arxiv:...]]` or
   `[[citet:arxiv:...]]` markers to ICLR-style author-year citations and BibTeX.
   `publication_quality.py` checks obvious citation grammar, presence of primary
   excerpts and page occupancy. It does not certify semantic citation support.
5. `build_publication_submission.py` rerenders the exact model JSON, compiles
   with Tectonic, checks hashes and bundles the study, prompts, raw outputs,
   reviews, usage and implementation. `submit_agentic_review.py` submits the
   frozen PDF through the official web form flow with a one-shot fence.

From the unpacked `code` directory, install the pinned requirements and obtain
the official JiuwenSwarm base noted in `README.md`. Then run the saved study
verifier with `python -S BDCI/research/recovery_v2_runs/''' + study_name +
'''/frozen_source/research/run_recovery_v2.py --verify-run BDCI/research/recovery_v2_runs/''' + study_name + '''`.
From the unpacked team directory, `python code/BDCI/research/build_publication_submission.py
--verify .` verifies file hashes, manuscript/model binding, usage and PDF layout
without provider requests. Tectonic compilation uses the lightweight local cache.
''',
        'innovation.md': '''# Contribution and measured boundary

The source change adds ResearchBudgetRail and ExperimentEvidenceRail to the
JiuwenSwarm harness and applies the native team-skill workflow to an auditable
paper-generation path. The system keeps scientific observations, source
excerpts, model drafts, critique, render rules and resource usage separately.
It rejects unbound reviews, unknown citation versions, inconsistent numeric
tables and failed requests that would otherwise be silently repeated.

In the selected study, the model-requested closure policy did not improve
correct completion or tool-call totals over either original-plan rerun or a
matched deterministic dependency-closure baseline. The paper reports this
bounded null finding rather than a positive performance claim. Nine
self-authored base instances are the paired units; 180 policy executions are
repeated measures and do not constitute independent external validation.

The code and review gates are engineering checks. They do not establish
novelty, statistical equivalence, external generalization or scientific
acceptance. The full prompt/response and usage lineage is included for audit.
''',
    }
    for name, content in docs.items():
        path = stage / 'docs' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    contribution = ('''# JiuwenSwarm contribution

The included `code/BDCI/contribution/research-rails.patch` adds the two Rail
implementations, tests and usage documentation against official JiuwenSwarm
commit `''' + BASE_SHA + '''`. The patch was also checked against the then-current
official develop branch; see `code/BDCI/contribution/validation.json`.
ResearchBudgetRail is used for sequential model admission and usage; the
ExperimentEvidenceRail's demonstrated integration scope is a selected smoke
tool path. The patch and validation are evidence of source modification, not
proof of maintainer acceptance.

Upstream PR: ''' + (pr_url or 'pending') + '\n')
    (stage / 'framework_contribution.md').write_text(contribution, encoding='utf-8')


def build_submission(layout, output, *, token=None, pr_url=None):
    layout, output = Path(layout).resolve(), Path(output).resolve()
    provenance, summary = read(layout / 'layout_provenance.json'), read(layout / 'summary.json')
    source = (HERE / provenance['source_run_relative']).resolve()
    validate_model_source(source)
    manuscript_role = provenance.get('source_raw_manuscript_role', 'reviser_0')
    raw_hash = provenance.get('source_raw_manuscript_sha256',
                              provenance.get('source_raw_revision_sha256'))
    if (sha(source / 'paper.json') != provenance['source_paper_sha256']
            or sha(layout / 'paper.json') != provenance['source_paper_sha256']
            or sha(source / f'raw_{manuscript_role}.txt') != raw_hash
            or sha(HERE / 'publication_render.py') != provenance['renderer_sha256']
            or sha(layout / 'paper.pdf') != provenance['final_pdf_sha256']
            or not summary['ready_for_external_review']):
        raise ValueError('layout_binding_changed')
    if audit_publication(read(layout / 'paper.json'), read(layout / 'sources.json'),
                         layout / 'paper.pdf') != read(layout / 'quality_audit.json'):
        raise ValueError('layout_quality_changed')
    if pr_url is not None and not re.fullmatch(
            r'https://(?:atomgit\.com|gitcode\.com)/openJiuwen/jiuwenswarm/pulls/\d+', pr_url):
        raise ValueError('invalid_upstream_pr_url')
    runs = run_chain(source)
    extensions = {}
    for run in runs:
        manifest_path = run / 'literature_manifest.json'
        if manifest_path.exists():
            extension = read(manifest_path).get('extension')
            if extension:
                relative = Path(extension['extension_run_relative'])
                if (relative.is_absolute() or '..' in relative.parts
                        or relative.parts[0] != 'replay_paper_runs'):
                    raise ValueError('unsafe_literature_extension_path')
                root = (HERE / relative).resolve()
                from prepare_publication_followup import verify_extension
                if digest(verify_extension(root)) != extension['extension_manifest_sha256']:
                    raise ValueError('literature_extension_changed')
                extensions[root.name] = root
    study = HERE / read(source / 'input_provenance.json')['study_run_relative']
    if not study.is_dir():
        raise ValueError('missing_selected_study')
    usage = audited_usage([study, *runs])
    if output.exists():
        raise FileExistsError('submission_output_exists')
    output.mkdir(parents=True)
    stage = output / validate_team_name(TEAM)
    stage.mkdir()
    for name in ('paper.pdf', 'paper.tex', 'paper.md', 'references.bib', 'paper.json',
                 'sources.json', 'evidence.json', 'quality_audit.json', 'layout_provenance.json',
                 'summary.json', *STYLE_FILES):
        safe_copy(layout / name, stage / 'paper' / name, layout)
    for run in runs:
        copy_tree(run, stage / 'code/BDCI/research/replay_paper_runs' / run.name,
                  exclude_run_noise=True)
    for name, extension_root in extensions.items():
        copy_tree(extension_root,
                  stage / 'code/BDCI/research/replay_paper_runs' / name,
                  exclude_run_noise=True)
    copy_tree(study, stage / 'code/BDCI/research/recovery_v2_runs' / study.name,
              exclude_run_noise=True)
    for path in sorted(HERE.glob('*.py')):
        safe_copy(path, stage / 'code/BDCI/research' / path.name, BDCI)
    copy_tree(HERE / 'skills', stage / 'code/BDCI/research/skills', exclude_run_noise=True)
    for name in ('README.md', 'resource_runs.json', 'model_capabilities.json',
                 'recovery_v2_planner.md'):
        src = HERE / name
        if src.exists():
            safe_copy(src, stage / 'code/BDCI/research' / name, BDCI)
    for src in (BDCI / 'activate.sh', BDCI / '任务要求.md',
                BDCI / 'tools/compile-latex.sh', BDCI / 'setup/requirements.repro.txt',
                BDCI / 'setup/latex-install.sh', BDCI / 'contribution/research-rails.patch'):
        safe_copy(src, stage / 'code/BDCI' / src.relative_to(BDCI), BDCI)
    for name in ('research_budget_rail.py', 'research_evidence_rail.py'):
        src = BDCI / 'jiuwenswarm/jiuwenswarm/agents/harness/common/rails' / name
        safe_copy(src, stage / 'code/framework_overlay/jiuwenswarm/agents/harness/common/rails' / name, BDCI)
    for name in ('README.md', 'PR_DESCRIPTION.md', 'upstream-usage.md', 'validation.json'):
        safe_copy(BDCI / 'contribution' / name,
                  stage / 'code/BDCI/contribution' / name, BDCI)
    write_submission_docs(stage, study.name, source.name, sha(layout / 'paper.pdf'),
                          pr_url=pr_url)
    study_usage = next((row for row in usage if row['run'] == study.name), None)
    if study_usage is None:
        raise ValueError('study_usage_missing')
    calls, tokens = sum(row['model_calls'] for row in usage), sum(row['total_tokens'] for row in usage)
    report = ('# Resource report\n\nSelected study and manuscript lineage, including failed calls. '
              'These are provider-reported usage figures, not a price estimate.\n\n'
              '| Stage | Status | Calls | Tokens | Duration (s) |\n| --- | --- | ---: | ---: | ---: |\n' +
              '\n'.join(f"| {row['run']} | {row['status']} | {row['model_calls']} | {row['total_tokens']:,} | {row['duration_seconds'] if row['duration_seconds'] is not None else 'unknown'} |"
                        for row in usage) +
              f'\n\nTotal: {calls} model calls and {tokens:,} tokens. '
              'The layout-only render and packaging used zero model calls. '
              'Recorded stage durations have different boundaries and are not summed. '
              'No GPU training was used; CPU replay, retrieval, development assistance, '
              'external review and actual monetary cost are outside this provider ledger.\n')
    (stage / 'resource_report.md').write_text(report, encoding='utf-8')
    (stage / 'resource_audit.json').write_text(json.dumps({'schema': 'publication_resource/1',
        'stages': usage, 'total_model_calls': calls, 'total_tokens': tokens,
        'selected_study': study.name}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (stage / 'code/README.md').write_text(
        '# Reproduction\n\nOfficial JiuwenSwarm base: https://atomgit.com/openJiuwen/jiuwenswarm\n'
        f'Pinned base commit: `{BASE_SHA}`. Overlay `framework_overlay` onto that checkout.\n\n'
        'From the repository root, run `source BDCI/activate.sh` and the relevant '
        '`BDCI/research/test_*.py` checks. Verify the frozen experiment with '
        f'`python -S BDCI/research/recovery_v2_runs/{study.name}/frozen_source/research/run_recovery_v2.py '
        f'--verify-run BDCI/research/recovery_v2_runs/{study.name}`. '
        'The manuscript raw responses and all selected usage summaries are archived '
        'under `replay_paper_runs`. Recompiling the PDF requires Tectonic and its cache; '
        'no API key is included.\n', encoding='utf-8')
    review_note = ('Final PDF SHA-256: `' + sha(layout / 'paper.pdf') + '`. '
                   'A Stanford Agentic Reviewer token for this exact PDF has not been supplied. '
                   'The prior token belongs to a different PDF and is excluded.\n')
    if token is not None:
        token_data = read(token)
        if (token_data.get('pdf_sha256') != sha(layout / 'paper.pdf')
                or not isinstance(token_data.get('access_token'), str)
                or not token_data['access_token'].strip()):
            raise ValueError('external_review_pdf_binding_mismatch')
        (stage / 'AgenticReviewer').mkdir()
        (stage / 'AgenticReviewer/PaperReview-AccessToken.txt').write_text(
            token_data['access_token'].strip() + '\n', encoding='utf-8')
        if token_data.get('review_completed'):
            review_path = Path(token).with_name(Path(token).stem + '-report.json')
            if (sha(review_path) != token_data.get('review_report_sha256')
                    or not read(review_path).get('success')):
                raise ValueError('external_review_report_binding_mismatch')
            safe_copy(review_path, stage / 'AgenticReviewer/review.json', review_path.parent)
            review_note = ('Stanford Agentic Reviewer completed for the final PDF hash; '
                           'its report is included without claiming acceptance.\n')
        else:
            review_note = ('Stanford Agentic Reviewer token supplied for the final PDF hash; '
                           'external review completion is not asserted here.\n')
    else:
        (stage / 'AgenticReviewer').mkdir()
        (stage / 'AgenticReviewer/README.md').write_text(review_note, encoding='utf-8')
    (stage / '提交说明.md').write_text(
        '# 提交说明\n\n队伍：真没招了。英文论文由模型生成并经过两轮内部审查；'
        '最终 PDF 由模型正文确定性渲染，没有人工修改正文。'
        '9 个自编结构留出基础实例不是外部独立验证；180 次策略执行不是 180 个独立样本。\n\n'
        + review_note + ('\n上游贡献 PR：' + pr_url + '\n' if pr_url else
                         '\n上游贡献 PR 链接尚未提供；补齐前本包是待完成的提交候选包。\n'),
        encoding='utf-8')
    manifest = {'schema': 'publication_submission/1', 'team_name': TEAM,
                'paper_sha256': sha(layout / 'paper.pdf'),
                'paper_model_source_sha256': sha(source / 'paper.json'),
                'external_review_submitted': token is not None,
                'external_review_completed': bool(token is not None and token_data.get('review_completed')),
                'upstream_pr_submitted': pr_url is not None,
                'submission_ready': token is not None and pr_url is not None,
                'missing_materials': (['Final-PDF Stanford Agentic Reviewer token'] if token is None else [])
                                     + ([] if pr_url else ['Upstream JiuwenSwarm contribution PR link']),
                'files': manifest_files(stage)}
    write_json(stage / 'manifest.json', manifest)
    archive = output / (TEAM + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                info = zipfile.ZipInfo(str(path.relative_to(output)), (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                zipped.writestr(info, path.read_bytes())
    return archive


def verify_bundle(stage):
    stage = Path(stage).resolve()
    manifest = read(stage / 'manifest.json')
    if (stage.name != manifest['team_name'] or manifest['files'] != manifest_files(stage)
            or sha(stage / 'paper/paper.pdf') != manifest['paper_sha256']
            or sha(stage / 'paper/paper.json') != manifest['paper_model_source_sha256']):
        raise ValueError('publication_submission_manifest_mismatch')
    quality = audit_publication(read(stage / 'paper/paper.json'),
                                read(stage / 'paper/sources.json'), stage / 'paper/paper.pdf')
    if quality != read(stage / 'paper/quality_audit.json') or quality['findings']:
        raise ValueError('publication_submission_quality_mismatch')
    provenance = read(stage / 'paper/layout_provenance.json')
    source_relative = Path(provenance['source_run_relative'])
    if (source_relative.is_absolute() or '..' in source_relative.parts
            or source_relative.parts[0] != 'replay_paper_runs'):
        raise ValueError('unsafe_bundled_source_path')
    research = stage / 'code/BDCI/research'
    source = research / source_relative
    paper = read(stage / 'paper/paper.json')
    manuscript_role = provenance.get('source_raw_manuscript_role', 'reviser_0')
    raw_hash = provenance.get('source_raw_manuscript_sha256',
                              provenance.get('source_raw_revision_sha256'))
    if (sha(source / 'paper.json') != provenance['source_paper_sha256']
            or sha(source / f'raw_{manuscript_role}.txt') != raw_hash
            or parse_object((source / f'raw_{manuscript_role}.txt').read_text()) != paper
            or sha(research / 'publication_render.py') != provenance['renderer_sha256']):
        raise ValueError('bundled_model_or_renderer_mismatch')
    evidence_hash = digest(read(source / 'evidence.json'))
    sequence = read(source / 'summary.json')['role_sequence']
    current = None
    for role in sequence:
        saved = read(source / f'{role}.json')
        raw = parse_object((source / f'raw_{role}.txt').read_text())
        if role == 'writer' or role.startswith('reviser_'):
            if saved != raw:
                raise ValueError('bundled_raw_manuscript_mismatch')
            current = saved
        elif role.startswith('reviewer_'):
            model_path = source / f'{role}_model.json'
            model_review = read(model_path if model_path.exists() else source / f'{role}.json')
            if (raw != model_review or saved['draft_sha256'] != digest(current)
                    or saved['evidence_sha256'] != evidence_hash):
                raise ValueError('bundled_internal_review_mismatch')
    final_review = read(source / f'{sequence[-1]}.json')
    if (current != paper or final_review['verdict'] != 'pass'
            or final_review['issues'] or len([r for r in sequence if r.startswith('reviewer_')]) < 2):
        raise ValueError('bundled_internal_review_mismatch')
    literature = read(source / 'literature_manifest.json')
    extension = literature.get('extension')
    if extension:
        relative = Path(extension['extension_run_relative'])
        if (relative.is_absolute() or '..' in relative.parts
                or relative.parts[0] != 'replay_paper_runs'):
            raise ValueError('unsafe_bundled_literature_path')
        from prepare_publication_followup import verify_extension
        if digest(verify_extension(research / relative)) != extension['extension_manifest_sha256']:
            raise ValueError('bundled_literature_extension_mismatch')
    audit = read(stage / 'resource_audit.json')
    calls = tokens = 0
    for row in audit['stages']:
        name = Path(row['run'])
        if name.name != row['run'] or name.name in ('', '.', '..'):
            raise ValueError('unsafe_bundled_usage_name')
        saved = (research / 'recovery_v2_runs' / name if row['run'] == audit['selected_study']
                 else research / 'replay_paper_runs' / name)
        model = read(saved / 'model_summary.json')
        usage = [json.loads(line) for line in (saved / 'model_usage.jsonl').read_text().splitlines() if line.strip()]
        if (model['model_calls'] != row['model_calls'] or model['total_tokens'] != row['total_tokens']
                or model['status'] != row['status'] or model['model_usage'] != usage
                or sha(saved / 'model_usage.jsonl') != row['usage_sha256']):
            raise ValueError('bundled_usage_mismatch')
        calls += row['model_calls']
        tokens += row['total_tokens']
    if calls != audit['total_model_calls'] or tokens != audit['total_tokens']:
        raise ValueError('bundled_usage_total_mismatch')
    token = stage / 'AgenticReviewer/PaperReview-AccessToken.txt'
    if manifest['external_review_submitted'] != token.exists():
        raise ValueError('external_review_material_mismatch')
    return {'files': len(manifest['files']), 'pages': quality['pages'],
            'paper_sha256': manifest['paper_sha256'],
            'submission_ready': manifest['submission_ready'],
            'missing_materials': manifest['missing_materials']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare-layout', type=Path)
    group.add_argument('--build', type=Path)
    group.add_argument('--verify', type=Path)
    parser.add_argument('--source-run', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--token-record', type=Path)
    parser.add_argument('--pr-url')
    args = parser.parse_args(argv)
    if args.prepare_layout:
        if not args.source_run:
            parser.error('--source-run required')
        print(prepare_layout(args.source_run, args.prepare_layout))
    elif args.build:
        if not args.output:
            parser.error('--output required')
        print(build_submission(args.build, args.output, token=args.token_record,
                               pr_url=args.pr_url))
    else:
        print(json.dumps(verify_bundle(args.verify), ensure_ascii=False))


if __name__ == '__main__':
    main()
