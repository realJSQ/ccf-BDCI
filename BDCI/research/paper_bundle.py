"""Build an explicitly incomplete competition-shaped workflow-validation bundle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

try:
    from .paper_contracts import validate_review, validate_revision_response
except ImportError:
    from paper_contracts import validate_review, validate_revision_response

BDCI = Path(__file__).resolve().parents[1]
BASE_SHA = 'fc18e5c572a6b3b62bb42ea843cce674140e4266'
STYLE_FILES = ('iclr2026_conference.sty', 'iclr2026_conference.bst', 'natbib.sty', 'fancyhdr.sty')
SUBMISSION_DOCS = ('architecture.md', 'module_call.md', 'innovation.md', 'framework_contribution.md')
CONTRIBUTION_FILES = ('README.md', 'PR_DESCRIPTION.md', 'upstream-usage.md',
                      'research-rails.patch', 'validation.json')
REVISION_RUN = 'revision_runs/live-20260928T141945-771317'
REVISION_PILOT = 'pilot_runs/live-20260928T084134-196833'
PROTOCOL_RUNS = ('protocol_runs/live-20260928T143347-906294',
                 'protocol_runs/live-20260928T143721-035518')
PROTOCOL_EVIDENCE_FILES = (
    'designer.json', 'auditor.json', 'context.json', 'handoff.json',
    'input_provenance.json', 'model_summary.json', 'model_usage.jsonl', 'resumption.json',
    'prompt_designer.txt', 'raw_designer.txt', 'prompt_auditor.txt', 'raw_auditor.txt',
)
REPLAY_RUN = 'replay_runs/live-20260928T144804-532140'
REPLAY_EVIDENCE_FILES = (
    'base_cases.json', 'episodes.json', 'frozen_workflow.py', 'pre_registration.json',
    'report.json', 'results.json', 'decision.json', 'model_summary.json', 'model_usage.jsonl',
) + tuple(name for i in range(18) for name in (
    f'episode_{i:02d}.json', f'results_episode_{i:02d}.json',
    f'prompt_episode_{i:02d}.txt', f'raw_episode_{i:02d}.txt'))
POSTHOC_FILES = ('summary.json', 'results.json', 'transformations.json', 'analysis_implementation.py')
PRIOR_WORK_FILES = ('fulltext_check.json', 'fulltext_check.md',
                    'revision_seed_sources.json', 'revision_followup.json',
                    'followup_design_source_check.json')
REVISION_EVIDENCE_FILES = (
    'context.json', 'proposer.json', 'critic.json', 'refiner.json', 'handoff.json',
    'input_provenance.json', 'input_scoring_verification.json', 'summary.json',
    'model_summary.json', 'model_usage.jsonl', 'workflow_events.jsonl',
) + tuple(f'{prefix}_{role}.txt' for prefix in ('prompt', 'raw')
          for role in ('proposer', 'critic', 'refiner'))
# These are inputs hard-coded by the runners, not whichever pilot was used to
# generate the PDF being packaged. Fail rather than ship a broken entry point.
RUNNER_INPUTS = {
    'run_method_revision.py': ('prior_work/revision_seed_sources.json',) + tuple(
        f'{REVISION_PILOT}/{name}.json' for name in (
            'pre_registration', 'designer', 'dataset_inputs', 'oracle_private',
            'peer', 'baseline', 'intervention', 'metrics', 'decision', 'run_review')),
    'run_protocol_design.py': ('prior_work/revision_followup.json',
                               f'{REVISION_RUN}/refiner.json'),
    'run_replay_study.py': ('replay_protocol.json',),
    'run_followup_design.py': (
        'prior_work/revision_followup.json', 'prior_work/followup_design_source_check.json',
        'followup_design_runs/live-20260929T003516-680636/followup_assessment.json',
        'protocol_examples/inconsistent.json', 'protocol_examples/consistent.json'),
}
EVIDENCE_FILES = (
    'paper.json', 'writer.json', 'reviewer.json', 'reviser.json', 'model_summary.json',
    'final_checks.json', 'summary.json', 'decision.json', 'metrics.json', 'pre_registration.json',
    'dataset_inputs.json', 'oracle_private.json', 'context_sources.json', 'sources.json',
    'previous_criticism.json', 'prior_work_check.json', 'designer.json', 'critic.json',
    'peer.json', 'baseline.json', 'intervention.json', 'analyst.json', 'artifact_hashes.json',
    'planner.json', 'proposer.json', 'revision_queue.json', 'pilot_handoff.json',
    'workflow_events.jsonl', 'model_usage.jsonl', 'requests.jsonl', 'retrieval_events.jsonl',
    'run_review.json', 'scoring_replay.json', 'next_iteration.json',
    'input_provenance.json', 'input_scoring_verification.json', 'pdf_validation.json',
    'recovery.json',
    'report.md', 'paper.md',
) + tuple(f'{prefix}_{role}.txt' for prefix in ('prompt', 'raw')
          for role in ('designer', 'critic', 'peer', 'baseline', 'intervention', 'analyst',
                       'writer', 'reviewer', 'reviser'))
SECRET_PATTERN = re.compile(rb'\bsk-[A-Za-z0-9_-]{16,}\b')


def _copy(source, destination, base):
    source, base = Path(source), Path(base)
    if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(base.resolve()):
        raise ValueError('unsafe_bundle_source')
    relative = source.absolute().relative_to(base.absolute())
    if any((base / Path(*relative.parts[:i])).is_symlink()
           for i in range(1, len(relative.parts))):
        raise ValueError('unsafe_bundle_source')
    if source.stat().st_size > 8_000_000:
        raise ValueError('bundle_file_too_large')
    data = source.read_bytes()
    if SECRET_PATTERN.search(data):
        raise ValueError('credential_like_content_in_bundle_source')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    if source.stat().st_mode & 0o111:
        destination.chmod(0o755)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _json(path, value):
    _write(path, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def _evidence(source_root, destination):
    for name in EVIDENCE_FILES:
        source = source_root / name
        if source.exists() or source.is_symlink():
            _copy(source, destination / name, source_root)


def _saved_replay_evidence(research, destination):
    """Selected immutable runs only; no runtime, journals, logs or ledgers."""
    for relative in PROTOCOL_RUNS:
        for name in PROTOCOL_EVIDENCE_FILES:
            source = research / relative / name
            if source.exists() or source.is_symlink():
                _copy(source, destination / relative / name, research)
    _copy_replay_evidence(research / REPLAY_RUN, destination / REPLAY_RUN)


def _copy_replay_evidence(saved, destination):
    """Copy a verified compatible study to an explicit archive location."""
    saved = Path(saved)
    if not saved.exists() and not saved.is_symlink():
        return
    if saved.is_symlink():
        raise ValueError('unsafe_bundle_source')
    # A selected replay must remain verifiable rather than silently dropping
    # missing evidence required by analyze_replay.py --verify-only.
    for name in REPLAY_EVIDENCE_FILES:
        _copy(saved / name, destination / name, saved)
    frozen = saved / 'frozen_source'
    if not frozen.is_dir() or frozen.is_symlink():
        raise ValueError('unsafe_bundle_frozen_source')
    for source in sorted(frozen.rglob('*')):
        if source.is_symlink():
            raise ValueError('unsafe_bundle_source')
        relative = source.relative_to(frozen)
        if (source.is_file() and source.suffix in ('.py', '.json', '.md')
                and not source.name.startswith(('workflow_journal', 'requests.', 'ledger.'))
                and not any(part.startswith('.') or part in ('logs', 'runtime', '__pycache__')
                            for part in relative.parts)):
            _copy(source, destination / 'frozen_source' / relative, frozen)
    posthoc = saved / 'posthoc_report_terminal'
    for name in POSTHOC_FILES:
        _copy(posthoc / name, destination / 'posthoc_report_terminal' / name, saved)


def build_bundle(root: Path, *, pilot_root: Path, summary: dict) -> Path:
    """Package saved evidence only; never install, contact APIs, or submit.

    Copies a fixed evidence whitelist plus local research source and skill text.
    Model credentials, runtime/logs, virtualenvs, repository metadata, and TeX
    binary/package caches are deliberately outside that whitelist.
    """
    root, pilot_root = Path(root), Path(pilot_root)
    required = ('paper.pdf', 'paper.tex', 'references.bib', 'paper.json', 'reviewer.json', 'reviser.json')
    for name in required:
        if not (root / name).is_file() or (root / name).is_symlink():
            raise ValueError(f'missing_or_unsafe_required_artifact:{name}')
    if not (root / 'paper.pdf').read_bytes().startswith(b'%PDF-'):
        raise ValueError('invalid_pdf_header')
    paper = json.loads((root / 'paper.json').read_text())
    review = json.loads((root / 'reviewer.json').read_text())
    revised = json.loads((root / 'reviser.json').read_text())
    validate_review(review, paper)
    validate_revision_response(revised, review)
    if not isinstance(summary, dict):
        raise ValueError('invalid_resource_summary')
    delivery = root / 'delivery' / 'workflow-validation'
    if delivery.exists():
        raise FileExistsError('validation_delivery_already_exists')
    with tempfile.TemporaryDirectory(prefix='.bundle-', dir=root) as temporary:
        stage = Path(temporary) / 'workflow-validation'
        stage.mkdir()
        for name in ('paper.pdf', 'paper.tex', 'references.bib', 'paper.md'):
            if (root / name).exists():
                _copy(root / name, stage / 'paper' / name, root)
        template = BDCI / 'validation/latex/iclr-template/iclr2026'
        for name in STYLE_FILES:
            source, base = (root / name, root) if (root / name).exists() else (template / name, template)
            _copy(source, stage / 'paper' / name, base)
            _copy(source, stage / 'code/BDCI/validation/latex/iclr-template/iclr2026' / name, base)
        _evidence(root, stage / 'internal_review')
        _evidence(pilot_root, stage / 'evidence/pilot')
        _evidence(pilot_root, stage / 'code/BDCI/research/pilot_runs' / pilot_root.name)
        research = BDCI / 'research'
        for source in sorted(research.glob('*.py')):
            _copy(source, stage / 'code/BDCI/research' / source.name, research)
        if (research / 'replay_protocol.json').exists():
            _copy(research / 'replay_protocol.json', stage / 'code/BDCI/research/replay_protocol.json', research)
        for name in ('README.md', 'PAPER.md', 'PILOT.md', 'REVISION.md', 'REPLAY_PAPER.md', 'FOLLOWUP.md', 'PIPELINE.md'):
            if (research / name).exists():
                _copy(research / name, stage / 'code/BDCI/research' / name, research)
        for name in ('README.md', 'consistent.json', 'inconsistent.json', 'graph-cache.json'):
            source = research / 'protocol_examples' / name
            if source.exists() or source.is_symlink():
                _copy(source, stage / 'code/BDCI/research/protocol_examples' / name, research)
        for source in sorted((BDCI / 'validation').glob('*.py')):
            _copy(source, stage / 'code/BDCI/validation' / source.name, BDCI)
        for source in sorted((BDCI / 'validation/skills').rglob('*')):
            if source.is_file() and source.suffix in ('.md', '.py', '.yaml', '.yml'):
                _copy(source, stage / 'code/BDCI/validation/skills' /
                      source.relative_to(BDCI / 'validation/skills'), BDCI)
        for source in sorted((BDCI / 'docs/superpowers/specs').glob('*.md')):
            _copy(source, stage / 'code/BDCI/docs/superpowers/specs' / source.name, BDCI)
        for name in CONTRIBUTION_FILES:
            _copy(BDCI / 'contribution' / name, stage / 'code/BDCI/contribution' / name, BDCI)
        submission = BDCI / 'docs/submission'
        for name in SUBMISSION_DOCS:
            destination = stage / 'code/BDCI/docs/submission' / name
            _copy(submission / name, destination, BDCI)
            # Retain canonical relative links in the source copy and adapt only
            # the copy at the competition-required top-level location.
            doc = destination.read_text(encoding='utf-8')
            doc = doc.replace('](../../', '](../code/BDCI/')
            doc = doc.replace('](../code/BDCI/jiuwenswarm/', '](../code/framework_overlay/')
            doc = doc.replace('](../superpowers/', '](../code/BDCI/docs/superpowers/')
            for audit in ('clean-environment-validation.json', 'historical-resource-audit.json'):
                doc = doc.replace('](' + audit + ')', '](../code/BDCI/docs/submission/' + audit + ')')
            if name == 'framework_contribution.md':
                # This required file lives one level above docs/ in the ZIP.
                doc = doc.replace('](../code/', '](code/')
                _write(stage / name, doc)
            else:
                _write(stage / 'docs' / name, doc)
        for name in ('clean-environment-validation.json', 'historical-resource-audit.json'):
            if (submission / name).exists():
                _copy(submission / name, stage / 'code/BDCI/docs/submission' / name, BDCI)
        for source in sorted((research / 'skills').rglob('*')):
            if source.is_file() and source.suffix in ('.md', '.py', '.yaml', '.yml'):
                _copy(source, stage / 'code/BDCI/research/skills' / source.relative_to(research / 'skills'), research)
        previous = research / 'runs/live-20260928T081927-158480'
        _evidence(previous, stage / 'code/BDCI/research/runs' / previous.name)
        _evidence(research / REVISION_PILOT, stage / 'code/BDCI/research' / REVISION_PILOT)
        for name in REVISION_EVIDENCE_FILES:
            source = research / REVISION_RUN / name
            if source.exists() or source.is_symlink():
                _copy(source, stage / 'code/BDCI/research' / REVISION_RUN / name, research)
        _saved_replay_evidence(research, stage / 'code/BDCI/research')
        # The current documentation cites this historical validation draft.
        # Include only its evidence/PDF, never its ZIP or nested delivery tree.
        archived_paper = research / 'paper_runs/live-20260928T104912-411414'
        if archived_paper.exists():
            archived_destination = stage / 'code/BDCI/research/paper_runs' / archived_paper.name
            _evidence(archived_paper, archived_destination)
            for name in ('paper.pdf', 'paper.tex', 'references.bib', *STYLE_FILES):
                if (archived_paper / name).exists():
                    _copy(archived_paper / name, archived_destination / name, research)
        for name in PRIOR_WORK_FILES:
            source = research / 'prior_work' / name
            if source.exists() or source.is_symlink():
                _copy(source, stage / 'code/BDCI/research/prior_work' / name, research)
        for runner, inputs in RUNNER_INPUTS.items():
            if (research / runner).exists():
                for relative in inputs:
                    _copy(research / relative, stage / 'code/BDCI/research' / relative, research)
        for name in ('research_budget_rail.py', 'research_evidence_rail.py'):
            relative = Path('jiuwenswarm/agents/harness/common/rails') / name
            _copy(BDCI / 'jiuwenswarm' / relative, stage / 'code/framework_overlay' / relative, BDCI)
        for name in ('activate.sh', 'setup/requirements.repro.txt', 'setup/requirements.freeze.txt',
                     'setup/pyproject.toml', 'setup/latex-install.sh', 'setup/latex-provenance.json',
                     'setup/latex-environment.md', 'setup/latex-gnu-provenance.json',
                     'tools/compile-latex.sh', 'tools/TECTONIC-LICENSE'):
            if (BDCI / name).exists():
                _copy(BDCI / name, stage / 'code/BDCI' / name, BDCI)
        _write(stage / 'code/README.md', f'''# Reproduction
Official base: https://atomgit.com/openJiuwen/jiuwenswarm
Pinned commit: `{BASE_SHA}`. The official base is not duplicated in this archive.

From this `code` directory, obtain the base and overlay the two source Rails:
```bash
git clone https://atomgit.com/openJiuwen/jiuwenswarm BDCI/jiuwenswarm
git -C BDCI/jiuwenswarm checkout {BASE_SHA}
cp -R framework_overlay/jiuwenswarm/. BDCI/jiuwenswarm/jiuwenswarm/
python3.13 -m venv BDCI/.venv
BDCI/.venv/bin/python -m pip install --no-deps -r BDCI/setup/requirements.repro.txt
BDCI/.venv/bin/python -m pip check
BDCI/.venv/bin/python -m pip install --no-deps -e BDCI/jiuwenswarm
source BDCI/activate.sh
```
No Git global configuration is required. Dependency installation and lightweight
TeX setup require network access; no installer was run by this packaging step.
Use `bash BDCI/setup/latex-install.sh`, then compile the delivered source with
`bash BDCI/tools/compile-latex.sh --outdir ../paper ../paper/paper.tex`.
The archive contains saved source, paper, internal review and pilot evidence.
Offline script modes are simulations; they do not establish a research result.
Do not run `--live` to reproduce the saved paper: live modes spend new API calls.
Credentials are intentionally absent. Restore paths or pass an explicit saved
pilot path if a runner default points to a differently named local run.
''')
        _write(stage / 'AgenticReviewer/README.md', '''# External review missing
No Stanford Agentic Reviewer submission was performed. No access token or
external review is included. Internal model review is stored in internal_review
and must not be presented as an external review. This archive is not ready to submit.
''')
        _write(stage / 'resource_report.md', '# Resource report\n\nSaved paper-workflow accounting (not a new experiment):\n\n```json\n' +
               json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) +
               '\n```\n\nPilot accounting is preserved in evidence/pilot/summary.json and model_usage.jsonl when available.\n'
               'Historical campaign totals and timing caveats are in code/BDCI/docs/submission/historical-resource-audit.json; they are not the cost of a new final submission run.\n'
               'Actual monetary cost is unknown unless independently supplied; token totals are not a currency estimate.\n')
        _write(stage / '提交说明.md', '''# 流程验证包，禁止当作正式参赛提交
固定目录名 workflow-validation 不是队伍名称。包内英文 PDF 用于验证论文产出流程。
尚缺外部 Agentic Reviewer 访问 Token 与真实外审记录、上游贡献 PR 链接、
研究新颖性及科学质量验收。正式提交前须复核比赛当前模板、队伍命名和材料要求。
未执行上传、比赛提交或外部审稿，也未重新运行模型能力实验。
''')
        manifest = {'status': 'not_submission_ready', 'bundle_kind': 'workflow_validation_dry_run',
                    'external_review_performed': False, 'upstream_pr_submitted': False,
                    'scientific_acceptance': False, 'base_repository': 'https://atomgit.com/openJiuwen/jiuwenswarm',
                    'base_commit': BASE_SHA,
                    'missing_materials': ['External Agentic Reviewer access token and actual review',
                                          'Upstream contribution PR URL',
                                          'Scientific novelty and quality acceptance',
                                          'Final team naming and competition submission validation'],
                    'files': {str(path.relative_to(stage)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in sorted(stage.rglob('*')) if path.is_file()}}
        _json(stage / 'manifest.json', manifest)
        for path in stage.rglob('*'):
            if path.is_file() and SECRET_PATTERN.search(path.read_bytes()):
                raise ValueError('credential_like_content_in_bundle')
        delivery.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(stage), delivery)
    archive = root / 'workflow-validation.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(delivery.rglob('*')):
            if path.is_file():
                zipped.write(path, arcname=str(path.relative_to(delivery.parent)))
    return archive
