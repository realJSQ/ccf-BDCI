"""Coordinate verified study -> native manuscript -> candidate -> unpacked verification.

This is the post-study portion of research automation, not autonomous topic or
experiment generation. Offline manuscripts are integration fixtures. No new
budget is created, and uncertain model requests are never automatically resent.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

sys.dont_write_bytecode = True

import build_replay_bundle as bundle
from replay_paper_evidence import build_evidence, digest
from study_adapter import get_adapter
from resource_accounting import audit_resources

HERE = Path(__file__).resolve().parent


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    temporary.replace(path)


def call_writer(paper, study, output, *, live, recover, study_kind='replay_v1'):
    command = [sys.executable, str(HERE / 'run_replay_paper.py'),
               '--study-run', str(study), '--no-latest']
    if study_kind != 'replay_v1':
        command += ['--study-kind', study_kind]
    command += ['--resume' if recover else '--output-run', str(paper)]
    if live and not recover:
        command.append('--live')
    attempt = uuid.uuid4().hex[:12]
    with (output / 'writer.lock').open('a') as lock, (
            output / f'writer-{attempt}.stdout').open('w') as stdout, (
            output / f'writer-{attempt}.stderr').open('w') as stderr:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # The child retains this lock if its coordinating parent dies. A later
        # recovery must not compile over an original writer still running.
        result = subprocess.run(command, cwd=HERE.parent.parent, stdout=stdout, stderr=stderr,
                                pass_fds=(lock.fileno(),))
    if result.returncode:
        raise RuntimeError('native_writing_failed_inspect_saved_run')


def manuscript_fingerprint(paper, study):
    bundle.validate_manuscript(paper, study)
    bundle.validate_rendered_sources(paper)
    chain = bundle.writing_chain(paper)
    return {str(Path(run.name) / name): bundle.sha(run / name)
            for run in chain for name in bundle.PAPER_FILES if (run / name).is_file()}


def register_writing_resources(paper):
    """Record terminal local writer usage, including measured failed calls.

    The inventory is accounting, not an inference permission or retry ledger.
    Unknown calls without complete usage remain explicitly unresolved.
    """
    paper = Path(paper).resolve()
    if paper.parent != (HERE / 'replay_paper_runs').resolve():
        raise ValueError('writing_resource_location_not_local')
    summary_path, usage_path = paper / 'model_summary.json', paper / 'model_usage.jsonl'
    if not summary_path.is_file():
        return {'status': 'no_terminal_summary'}
    summary = bundle.read(summary_path)
    if summary.get('mode') != 'live':
        return {'status': 'offline_not_live_usage'}
    if not usage_path.is_file():
        return {'status': 'usage_unresolved', 'admitted_calls': summary.get('model_calls')}
    rows = [json.loads(line) for line in usage_path.read_text().splitlines() if line.strip()]
    if not rows or summary.get('model_calls') != len(rows) or summary.get('model_usage') != rows:
        return {'status': 'usage_unresolved', 'admitted_calls': summary.get('model_calls'), 'measured_calls': len(rows)}
    inventory_path = HERE / 'resource_runs.json'
    with inventory_path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        inventory = bundle.read(inventory_path)
        entry = {'usage': str(usage_path.relative_to(HERE.parent)),
                 'summary': str(summary_path.relative_to(HERE.parent))}
        if entry not in inventory['runs']:
            inventory['runs'].append(entry)
        audit = audit_resources(HERE.parent, inventory)
        save(inventory_path, inventory)
    return {'status': 'registered', 'calls': len(rows), 'tokens': sum(r['total_tokens'] for r in rows),
            'historical_calls': audit['total_calls'], 'historical_tokens': audit['total_tokens']}


def verify_archive(archive):
    """Run the delivered verifier, not merely the development-tree version."""
    with tempfile.TemporaryDirectory(prefix='replay-pipeline-verify-') as temporary:
        with zipfile.ZipFile(archive) as zipped:
            top_levels = set()
            for name in zipped.namelist():
                path = Path(name)
                if path.is_absolute() or '..' in path.parts or not path.parts or '\\' in name:
                    raise ValueError('unsafe_candidate_archive')
                top_levels.add(path.parts[0])
            if len(top_levels) != 1:
                raise ValueError('candidate_requires_one_top_level_directory')
            folder = bundle.validate_team_name(top_levels.pop())
            zipped.extractall(temporary)
        stage = Path(temporary) / folder
        command = [sys.executable, str(stage / 'code/BDCI/research/build_replay_bundle.py'),
                   '--verify', str(stage)]
        result = subprocess.run(command, cwd=stage / 'code', capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise ValueError('unpacked_candidate_verification_failed')
        return json.loads(result.stdout)


def run_pipeline(study, output, *, paper=None, live=False, resume=False, team_name=None, study_kind=None):
    study, output = Path(study).resolve(), Path(output).resolve()
    if team_name is not None:
        bundle.validate_team_name(team_name)
    if resume:
        if not (output / 'pipeline.json').is_file():
            raise ValueError('missing_pipeline_state')
    else:
        output.mkdir(parents=True, exist_ok=False)
    with (output / 'pipeline.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = output / 'pipeline.json'
        if resume:
            state = bundle.read(state_path)
            if state.get('schema_version') != 1:
                raise ValueError('unsupported_pipeline_state')
            if live:
                raise ValueError('resume_uses_saved_mode')
            if paper is not None and Path(paper).resolve() != Path(state['paper_run']):
                raise ValueError('pipeline_paper_input_changed')
            if team_name is not None and team_name != state.get('team_name'):
                raise ValueError('pipeline_team_name_changed')
            if study_kind is not None and study_kind != state.get('study_kind', 'replay_v1'):
                raise ValueError('pipeline_study_kind_changed')
        else:
            kind = study_kind or (bundle.manuscript_adapter(paper).kind if paper else 'replay_v1')
            get_adapter(kind)
            identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-') + uuid.uuid4().hex[:8]
            state = {'schema_version': 1, 'status': 'running', 'stages': {},
                'study_run': str(study), 'paper_origin': 'saved' if paper else 'native',
                'paper_run': str(Path(paper).resolve()) if paper else str(
                    HERE / 'replay_paper_runs' / (('live' if live else 'offline') + '-pipeline-' + identifier)),
                'writing_live': live, 'submission_ready': False,
                'study_kind': kind,
                'team_name': team_name, 'bundle_name': team_name or 'replay-candidate',
                'scope': 'Completed compatible study through candidate packaging; topic and experiment stages are separate.'}
            save(state_path, state)
        stages = state['stages']
        current = 'evidence'
        started = time.monotonic()
        try:
            adapter = get_adapter(state.get('study_kind', 'replay_v1'))
            evidence = adapter.build_evidence(study) if adapter.is_v2 else build_evidence(study)
            signature = digest(evidence)
            if 'evidence_sha256' in state and signature != state['evidence_sha256']:
                raise ValueError('pipeline_study_input_changed')
            state.update(study_run=str(study), evidence_sha256=signature, status='running')
            stages['evidence'] = {'status': 'verified', 'evidence_sha256': signature}
            save(state_path, state)
            current = 'manuscript'
            paper = Path(state['paper_run'])
            previous = stages.get(current, {})
            if previous.get('status') == 'completed':
                if manuscript_fingerprint(paper, study) != previous['files']:
                    raise ValueError('pipeline_manuscript_changed')
            else:
                if state['paper_origin'] == 'native':
                    # A recorded attempt or existing directory may contain an API
                    # request whose outcome is unknown. Only replay complete raws.
                    recover = bool(previous) or paper.exists()
                    if recover and not all((paper / name).is_file() for name in (
                            'model_summary.json', 'raw_writer.txt', 'raw_reviewer.txt', 'raw_reviser.txt')):
                        raise ValueError('incomplete_writing_requires_explicit_recovery_no_automatic_retry')
                    stages[current] = {'status': 'running', 'paper_run': str(paper),
                                       'recovery_without_api': recover}
                    save(state_path, state)
                    try:
                        call_writer(paper, study, output, live=state['writing_live'], recover=recover,
                                    **({'study_kind': adapter.kind} if adapter.is_v2 else {}))
                    finally:
                        if state['writing_live']:
                            stages['writing_resource'] = register_writing_resources(paper)
                            save(state_path, state)
                if bundle.manuscript_adapter(paper).kind != adapter.kind:
                    raise ValueError('pipeline_manuscript_study_kind_mismatch')
                files = manuscript_fingerprint(paper, study)
                stages[current] = {'status': 'completed', 'files': files}
                save(state_path, state)
            current = 'bundle'
            bundle_name = state.get('bundle_name', 'replay-candidate')
            archive = output / 'bundle' / (bundle_name + '.zip')
            previous = stages.get(current, {})
            if previous.get('status') == 'completed':
                if not archive.is_file() or bundle.sha(archive) != previous['zip_sha256']:
                    raise ValueError('pipeline_archive_changed')
            elif archive.exists():
                # A complete archive may survive a crash before checkpointing.
                # Verify its manuscript binding before adopting, never overwrite.
                verify_archive(archive)
                with zipfile.ZipFile(archive) as zipped:
                    manifest = json.loads(zipped.read(bundle_name + '/manifest.json'))
                if (manifest['paper_run'] != paper.name
                        or manifest['paper_sha256'] != bundle.sha(paper / 'paper.pdf')
                        or any(manifest['files'].get('code/BDCI/research/replay_paper_runs/' + name) != expected
                               for name, expected in stages['manuscript']['files'].items())):
                    raise ValueError('pipeline_archive_target_mismatch')
                stages[current] = {'status': 'completed', 'zip_sha256': bundle.sha(archive)}
                save(state_path, state)
            else:
                stages[current] = {'status': 'running'}
                save(state_path, state)
                built = bundle.build_bundle(paper, output / 'bundle', study_run=study,
                                            team_name=state.get('team_name'))
                if built != archive:
                    raise ValueError('unexpected_pipeline_archive')
                stages[current] = {'status': 'completed', 'zip_sha256': bundle.sha(archive)}
                save(state_path, state)
            current = 'unpacked_verification'
            checked = verify_archive(archive)
            stages[current] = {'status': 'verified', 'result': checked}
            mode = bundle.read(paper / 'summary.json')['mode']
            state.update(status='saved_candidate_verified' if mode == 'live' else 'integration_candidate_verified',
                         writing_mode=mode, submission_ready=False,
                         last_invocation_duration_seconds=time.monotonic() - started)
            state.pop('last_error', None)
            save(state_path, state)
            return state
        except BaseException as error:
            state.update(status='failed', last_error={'stage': current, 'error_type': type(error).__name__,
                         'message': str(error) if isinstance(error, ValueError) else 'See saved stage artifacts'},
                         last_invocation_duration_seconds=time.monotonic() - started)
            save(state_path, state)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-run', type=Path, required=True)
    parser.add_argument('--study-kind', choices=('replay_v1', 'recovery_v2'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--paper-run', type=Path, help='Reuse saved manuscript; otherwise invoke native writing')
    parser.add_argument('--live', action='store_true', help='Use existing writing budget; never resets it')
    parser.add_argument('--resume', action='store_true', help='Verify checkpoints and recover without reissuing model requests')
    parser.add_argument('--team-name', help='ZIP and top-level directory name; does not certify submission readiness')
    args = parser.parse_args()
    try:
        state = run_pipeline(args.study_run, args.output, paper=args.paper_run,
                             live=args.live, resume=args.resume, team_name=args.team_name, study_kind=args.study_kind)
        print(json.dumps({'status': state['status'], 'output': str(args.output.resolve()),
                          'paper_run': state['paper_run'], 'submission_ready': False}))
        return 0
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__,
                          'output': str(args.output.resolve())}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
