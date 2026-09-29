"""Build and verify an explicitly incomplete recovery-paper candidate, without APIs."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import sys
import zipfile

# Verification must not mutate an unpacked archive by creating bytecode caches.
sys.dont_write_bytecode = True

import paper_bundle as base
from paper_contracts import validate_paper, validate_review, validate_revision_response
from replay_paper_evidence import build_evidence, digest
from run_topics import parse_object
from resource_accounting import audit_resources, render_report, source_path

HERE = Path(__file__).resolve().parent
PAPER_FILES = ('paper.pdf', 'paper.tex', 'paper.md', 'references.bib', 'paper.json',
    'writer.json', 'reviewer.json', 'reviser.json', 'evidence.json', 'sources.json',
    'input_provenance.json', 'summary.json', 'model_summary.json', 'model_usage.jsonl',
    'continuation.json', 'recovery.json', 'failure.json', 'editorial_revision.json',
    'editorial_assistance.json', 'pdf_validation.json') + base.STYLE_FILES + tuple(
    f'{prefix}_{role}.txt' for prefix in ('raw', 'prompt') for role in ('writer', 'reviewer', 'reviser'))


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_bound_review(writer, review, evidence):
    if set(review) != {'verdict', 'external_reviewer', 'issues', 'revision_instructions',
                      'draft_sha256', 'evidence_sha256', 'issue_quotes'}:
        raise ValueError('invalid_bound_review')
    if review['draft_sha256'] != digest(writer) or review['evidence_sha256'] != digest(evidence):
        raise ValueError('review_target_mismatch')
    normalized = copy.deepcopy({k: review[k] for k in
        ('verdict', 'external_reviewer', 'issues', 'revision_instructions')})
    for issue in normalized['issues']:
        if 'section_id_note' in issue:
            if issue.pop('section_id_note') != issue.get('section_id'):
                raise ValueError('conflicting_section_annotation')
    validate_review(normalized, writer)
    quotes = review['issue_quotes']
    if not isinstance(quotes, list) or len(quotes) != len(normalized['issues']):
        raise ValueError('unanchored_review')
    sections = {s['id']: s['text'] for s in writer['sections']}
    sections['abstract'] = writer['abstract']
    for issue, quote in zip(normalized['issues'], quotes):
        if not isinstance(quote, str) or not quote.strip() or quote not in sections[issue['section_id']]:
            raise ValueError('ungrounded_review')
    return normalized


def editorial_source(root, research):
    metadata = root / 'editorial_assistance.json'
    if not metadata.exists() or 'source_directory' not in read(metadata):
        return None
    relative = Path(read(metadata)['source_directory'])
    if len(relative.parts) != 2 or relative.parts[0] != 'replay_paper_runs' or relative.name in ('.', '..'):
        raise ValueError('unsafe_editorial_source')
    source = research / relative
    if source == root or not source.is_dir() or source.is_symlink():
        raise ValueError('unsafe_editorial_source')
    if 'source_directory' in read(source / 'editorial_assistance.json'):
        raise ValueError('nested_editorial_source')
    return source


def validate_manuscript(root, replay_root, research=HERE):
    root = Path(root)
    source = editorial_source(root, research)
    if source is not None:
        normalized, inherited = validate_manuscript(source, replay_root, research)
        meta = read(root / 'editorial_assistance.json')
        paper, summary = read(root / 'paper.json'), read(root / 'summary.json')
        validate_paper(paper, read(root / 'sources.json'))
        validate_revision_response(paper, read(source / 'reviewer.json'))
        if (meta['source_paper_sha256'] != digest(read(source / 'paper.json'))
                or meta['source_pdf_sha256'] != sha(source / 'paper.pdf')
                or meta['final_paper_sha256'] != digest(paper)
                or meta['new_model_calls'] != 0 or meta['measurements_changed'] is not False
                or read(root / 'evidence.json') != read(source / 'evidence.json')
                or read(root / 'sources.json') != read(source / 'sources.json')
                or summary['pdf']['sha256'] != sha(root / 'paper.pdf')
                or not (root / 'paper.pdf').read_bytes().startswith(b'%PDF-')
                or summary['submission_ready'] is not False
                or summary['external_review_completed'] is not False
                or summary['new_model_calls'] != 0
                or any(summary[k] != inherited[k] for k in ('writing_model_calls', 'writing_total_tokens'))):
            raise ValueError('editorial_source_binding_mismatch')
        return normalized, summary
    evidence, sources = read(root / 'evidence.json'), read(root / 'sources.json')
    previous_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        rebuilt = build_evidence(replay_root)
    finally:
        sys.dont_write_bytecode = previous_bytecode
    if evidence != rebuilt:
        raise ValueError('saved_evidence_mismatch')
    provenance = read(root / 'input_provenance.json')
    if provenance['evidence_sha256'] != digest(evidence) or provenance['sources_sha256'] != digest(sources):
        raise ValueError('input_provenance_mismatch')
    outputs = {}
    for role in ('writer', 'reviewer', 'reviser'):
        outputs[role] = read(root / f'{role}.json')
        if outputs[role] != parse_object((root / f'raw_{role}.txt').read_text()):
            raise ValueError('raw_response_mismatch')
    validate_paper(outputs['writer'], sources, max_words=1800)
    normalized = validate_bound_review(outputs['writer'], outputs['reviewer'], evidence)
    validate_paper(outputs['reviser'], sources, max_words=1800)
    validate_revision_response(outputs['reviser'], outputs['reviewer'])
    paper = read(root / 'paper.json')
    validate_paper(paper, sources)
    validate_revision_response(paper, outputs['reviewer'])
    if paper != outputs['reviser']:
        assistance = read(root / 'editorial_assistance.json')
        if (assistance['original_model_revision_sha256'] != digest(outputs['reviser'])
                or assistance['final_paper_sha256'] != digest(paper)
                or assistance['new_model_calls'] != 0
                or read(root / 'editorial_revision.json') != paper):
            raise ValueError('editorial_provenance_mismatch')
    summary = read(root / 'summary.json')
    if (summary['pdf']['sha256'] != sha(root / 'paper.pdf')
            or not (root / 'paper.pdf').read_bytes().startswith(b'%PDF-')
            or summary['submission_ready'] is not False
            or summary['external_review_completed'] is not False):
        raise ValueError('invalid_candidate_summary')
    return normalized, summary


def validate_rendered_sources(root):
    from replay_paper_render import render_replay_paper
    root = Path(root)
    summary = read(root / 'summary.json')
    evidence = copy.deepcopy(read(root / 'evidence.json'))
    evidence['resource'].update({key: summary[key] for key in ('writing_model_calls', 'writing_total_tokens')})
    with tempfile.TemporaryDirectory(prefix='replay-render-check-') as temporary:
        rendered = Path(temporary)
        render_replay_paper(rendered, read(root / 'paper.json'), read(root / 'sources.json'), evidence, summary['mode'])
        for name in ('paper.tex', 'paper.md', 'references.bib'):
            if (root / name).read_bytes() != (rendered / name).read_bytes():
                raise ValueError('rendered_source_mismatch:' + name)


def writing_chain(root, research=HERE):
    """Resolve only selected local run names; never trust saved absolute paths."""
    chain, seen = [], set()
    current = Path(root)
    original = editorial_source(current, research)
    if original is not None:
        chain.append(current)
        current = original
    while True:
        if current.name in seen:
            raise ValueError('cyclic_continuation')
        seen.add(current.name)
        chain.append(current)
        if not (current / 'continuation.json').exists():
            return chain
        name = Path(read(current / 'continuation.json')['source']).name
        current = research / 'replay_paper_runs' / name
        if not current.is_dir() or current.is_symlink():
            raise ValueError('missing_or_unsafe_continuation')


def select_study(root, explicit=None):
    """A missing saved input is an error; explicit relocation stays content-bound."""
    if explicit is not None:
        selected = Path(explicit).resolve()
    else:
        original = editorial_source(root, HERE)
        provenance = read((original or root) / 'input_provenance.json')
        relative = provenance.get('study_run_relative')
        if relative is not None:
            selected = source_path(HERE, relative)
        else:
            selected = Path(provenance['run'])
            if not selected.is_absolute():
                raise ValueError('ambiguous_legacy_study_path')
    if not selected.is_dir() or selected.is_symlink():
        raise ValueError('study_missing_supply_study_run')
    return selected


def registered_usage(run, inventory, bdci):
    """Relocated copies resolve to one inventory entry, never additional usage."""
    for entry in inventory['runs']:
        if (sha(run / 'model_usage.jsonl') == sha(source_path(bdci, entry['usage']))
                and sha(run / 'model_summary.json') == sha(source_path(bdci, entry['summary']))):
            return entry['usage']
    raise ValueError('unregistered_live_run_update_resource_inventory:' + run.name)


def registered_study(run, inventory, bdci):
    usage = registered_usage(run, inventory, bdci)
    canonical = source_path(bdci, usage).parent
    # Same usage is not permission to overwrite history with edited evidence.
    with tempfile.TemporaryDirectory(prefix='study-binding-') as temporary:
        left, right = Path(temporary) / 'selected', Path(temporary) / 'registered'
        base._copy_replay_evidence(run, left)
        base._copy_replay_evidence(canonical, right)
        signature = lambda root: {str(p.relative_to(root)): sha(p) for p in root.rglob('*') if p.is_file()}
        if signature(left) != signature(right):
            raise ValueError('registered_study_content_mismatch')
    relative = str(canonical.relative_to(Path(bdci) / 'research'))
    return relative, usage


def verify_bundle(stage):
    stage = Path(stage)
    manifest = read(stage / 'manifest.json')
    if manifest.get('submission_ready') is not False or manifest['status'] != 'not_submission_ready':
        raise ValueError('invalid_readiness_claim')
    actual = {str(p.relative_to(stage)): sha(p) for p in stage.rglob('*')
              if p.is_file() and p != stage / 'manifest.json'}
    if any(p.is_symlink() for p in stage.rglob('*')) or actual != manifest['files']:
        raise ValueError('manifest_mismatch')
    research = stage / 'code/BDCI/research'
    paper = research / 'replay_paper_runs' / manifest['paper_run']
    study_relative = manifest.get('study_run', base.REPLAY_RUN)
    study = source_path(research, study_relative)
    _, summary = validate_manuscript(paper, study, research)
    validate_rendered_sources(paper)
    if ('integration_only' in manifest and (manifest['integration_only'] is not (summary['mode'] != 'live')
            or manifest.get('writing_mode') != summary['mode'])):
        raise ValueError('writing_mode_claim_mismatch')
    if sha(stage / 'paper/paper.pdf') != summary['pdf']['sha256']:
        raise ValueError('delivered_pdf_mismatch')
    chain = writing_chain(paper, research)
    model_runs = [run for run in chain if (run / 'model_summary.json').exists()]
    totals = {'model_calls': 0, 'total_tokens': 0}
    for run in reversed(model_runs):
        model = read(run / 'model_summary.json')
        usage = [json.loads(line) for line in (run / 'model_usage.jsonl').read_text().splitlines() if line.strip()]
        if (model['model_calls'] != len(usage)
                or model['total_tokens'] != sum(row['total_tokens'] for row in usage)
                or model['model_usage'] != usage):
            raise ValueError('raw_usage_accounting_mismatch')
        if (run / 'continuation.json').exists():
            continued = read(run / 'continuation.json')
            if any(continued['source_summary'][key] != totals[key] for key in totals):
                raise ValueError('continuation_accounting_mismatch')
            parent = research / 'replay_paper_runs' / Path(continued['source']).name
            hashes = continued.get('saved_raw_sha256') or {'writer': continued['writer_sha256']}
            for role, saved_hash in hashes.items():
                if role not in ('writer', 'reviewer') or saved_hash != sha(parent / f'raw_{role}.txt') or saved_hash != sha(run / f'raw_{role}.txt'):
                    raise ValueError('continuation_raw_mismatch')
        for key in totals:
            totals[key] += model[key]
    if totals != {'model_calls': summary['writing_model_calls'], 'total_tokens': summary['writing_total_tokens']}:
        raise ValueError('writing_accounting_mismatch')
    inventory = read(research / 'resource_runs.json')
    audit = audit_resources(stage / 'code/BDCI', inventory)
    if read(stage / 'resource_audit.json') != audit:
        raise ValueError('resource_audit_mismatch')
    registered_relative, study_usage = registered_study(study, inventory, stage / 'code/BDCI')
    if registered_relative != study_relative:
        raise ValueError('noncanonical_study_inventory_binding')
    for run in model_runs:
        if read(run / 'model_summary.json')['mode'] == 'live':
            registered_usage(run, inventory, stage / 'code/BDCI')
    if (stage / 'resource_report.md').read_text() != render_report(
            audit, study_usage, {**totals, 'mode': summary['mode']}):
        raise ValueError('resource_report_mismatch')
    return {'status': 'verified_saved_candidate', 'files': len(actual),
            'submission_ready': False, 'new_model_calls': 0, 'writing': totals,
            'writing_mode': summary['mode'], 'study_run': study_relative, 'archived_live_usage': {
                'model_calls': audit['total_calls'], 'total_tokens': audit['total_tokens']}}


def build_bundle(root, output, study_run=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    study = select_study(root, study_run)
    review, summary = validate_manuscript(root, study)
    inventory = read(HERE / 'resource_runs.json')
    study_relative, study_usage = registered_study(study, inventory, base.BDCI)
    validate_rendered_sources(root)
    chain = writing_chain(root)
    for run in chain:
        if (run / 'model_summary.json').exists() and read(run / 'model_summary.json')['mode'] == 'live':
            registered_usage(run, inventory, base.BDCI)
    output.mkdir(parents=True, exist_ok=True)
    delivery, archive = output / 'replay-candidate', output / 'replay-candidate.zip'
    if delivery.exists() or archive.exists():
        raise FileExistsError('candidate_output_already_exists')
    with tempfile.TemporaryDirectory(prefix='.replay-bundle-', dir=output) as temporary:
        adapter = Path(temporary) / 'adapter'
        adapter.mkdir()
        original = editorial_source(root, HERE)
        for source_root in ([original, root] if original else [root]):
            for name in PAPER_FILES:
                if (source_root / name).exists() or (source_root / name).is_symlink():
                    base._copy(source_root / name, adapter / name, source_root)
        # This compatibility projection follows the complete bound-review checks
        # above. The delivered internal review is restored to the original.
        base._json(adapter / 'reviewer.json', review)
        base.build_bundle(adapter, pilot_root=HERE / base.REVISION_PILOT, summary=summary)
        stage = adapter / 'delivery/workflow-validation'
        base._copy_replay_evidence(study, stage / 'code/BDCI/research' / study_relative)
        for run in chain:
            destination = stage / 'code/BDCI/research/replay_paper_runs' / run.name
            for name in PAPER_FILES:
                if (run / name).exists() or (run / name).is_symlink():
                    base._copy(run / name, destination / name, run)
        for source_root in ([original, root] if original else [root]):
            for name in PAPER_FILES:
                if (source_root / name).exists() or (source_root / name).is_symlink():
                    base._copy(source_root / name, stage / 'internal_review' / name, source_root)
        inventory = read(HERE / 'resource_runs.json')
        audit = audit_resources(base.BDCI, inventory)
        base._copy(HERE / 'resource_runs.json',
                   stage / 'code/BDCI/research/resource_runs.json', base.BDCI)
        for entry in inventory['runs']:
            for key in ('usage', 'summary'):
                relative = entry[key]
                base._copy(source_path(base.BDCI, relative), stage / 'code/BDCI' / relative, base.BDCI)
        base._json(stage / 'resource_audit.json', audit)
        base._write(stage / 'resource_report.md', render_report(audit,
            study_usage,
            {'model_calls': summary['writing_model_calls'], 'total_tokens': summary['writing_total_tokens'], 'mode': summary['mode']}))
        base._write(stage / '提交说明.md', '''# 开发候选包，尚不能正式提交
本包保存真实恢复实验与辅助编辑论文，研究新颖性及正式科学验收未完成。
replay-candidate 不是队伍名称。缺正式队伍信息、当前赛题模板复核、
最终 PDF 对应的外部 Reviewer Access Token、官方贡献 PR URL。
内部模型审阅不是外部评审；本次打包不调用模型、不上传、不提交。
''')
        if summary['mode'] != 'live':
            note = stage / '提交说明.md'
            base._write(note, note.read_text() + '\n本包论文为离线脚本集成测试产物，不是真实模型生成的新论文。不可用于正式投稿。\n')
        base._write(stage / 'code/REPLAY_REPRODUCTION.md', f'''# Saved recovery evidence
From this code directory, using Python 3.13 and the installed project dependencies:
```bash
python BDCI/research/build_replay_bundle.py --verify ..
python BDCI/research/analyze_replay.py BDCI/research/{study_relative} --verify-only
```
These commands use saved responses and CPU replay, without model APIs or credentials.
The first verifies file hashes, raw-response equality, review bindings, editorial
provenance, PDF hash, writing accounting and strict/post-hoc replay evidence.
It does not certify scientific novelty or external review. Dependency installation
and framework setup are documented in README.md. TeX recompilation requires the
lightweight Tectonic installation and its font/package cache; neither is bundled.
Original absolute paths in provenance are historical metadata; verification resolves
selected run names relative to this archive. No live run is needed for verification.
''')
        manifest = read(stage / 'manifest.json')
        manifest.update(bundle_kind='recovery_paper_development_candidate', submission_ready=False,
                        paper_run=root.name, study_run=study_relative,
                        integration_only=summary['mode'] != 'live', writing_mode=summary['mode'],
                        paper_sha256=summary['pdf']['sha256'],
                        editorial_assistance=summary.get('editorial_assistance', False))
        manifest['missing_materials'].extend(['Unified end-to-end automatic research entry point', 'Independent scientific validation'])
        manifest['files'] = {str(p.relative_to(stage)): sha(p) for p in sorted(stage.rglob('*'))
                             if p.is_file() and p.name != 'manifest.json'}
        base._json(stage / 'manifest.json', manifest)
        for p in stage.rglob('*'):
            if p.is_file() and base.SECRET_PATTERN.search(p.read_bytes()):
                raise ValueError('credential_like_content_in_bundle')
        verify_bundle(stage)
        shutil.move(str(stage), delivery)
    # Fixed ZIP timestamp/order gives reproducible bytes for identical inputs.
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(delivery.rglob('*')):
            if path.is_file():
                info = zipfile.ZipInfo(str(path.relative_to(output)), date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (path.stat().st_mode & 0xffff) << 16
                zipped.writestr(info, path.read_bytes())
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paper-run', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--study-run', type=Path, help='Content-bound relocation of the saved compatible study')
    parser.add_argument('--verify', type=Path, help='Verify an unpacked replay-candidate directory')
    args = parser.parse_args()
    if args.verify:
        if args.paper_run or args.output or args.study_run:
            parser.error('--verify cannot be combined with build arguments')
        print(json.dumps(verify_bundle(args.verify)))
    else:
        if not args.paper_run or not args.output:
            parser.error('--paper-run and --output required')
        print(build_bundle(args.paper_run, args.output, args.study_run))
