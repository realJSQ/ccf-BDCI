"""Prepare, run and verify a bounded model-only manuscript review loop."""
from __future__ import annotations

import argparse
import asyncio
import copy
import fcntl
import json
import os
from pathlib import Path
import re

from native_runner import native_run
from publication_loop_state import HERE, SKILL, FollowupState, LoopState, loop_profile_digest
from publication_quality import audit_publication
from publication_render import render_publication
from replay_paper_evidence import digest
from run_replay_paper import compile_pdf
from run_topics import write_json


def manuscript_words(paper):
    return sum(len(text.split()) for text in
               [paper['title'], paper['abstract'], *[row['text'] for row in paper['sections']]])


def paper_summary(state, metering, pdf, quality, *, resumed):
    sequence = list(state.outputs)
    reviews = [role for role in sequence if role.startswith('reviewer_')]
    revisions = [role for role in sequence if role.startswith('reviser_')]
    final_review = state.latest_review()
    internal_pass = final_review['verdict'] == 'pass' and not final_review['issues'] and len(reviews) >= 2
    ready_for_external_review = internal_pass and not quality['findings']
    return {'status': 'manuscript_generated' if ready_for_external_review else 'needs_more_revision',
            'mode': metering['mode'], 'study_kind': 'recovery_v2',
            'review_loop_profile': True, 'pdf': pdf,
            'source_paper_words': manuscript_words(state.previous),
            'final_paper_words': manuscript_words(state.current_paper()),
            'review_rounds': len(reviews), 'revision_rounds': len(revisions),
            'mechanical_review_issues_added': sum(len(control['mechanical_issues']) for control in
                getattr(state, 'review_controls', {}).values()),
            'final_internal_review': final_review['verdict'],
            'final_internal_review_issues': len(final_review['issues']),
            'role_sequence': sequence, 'writing_model_calls': metering['model_calls'],
            'writing_total_tokens': metering['total_tokens'],
            'quality_finding_codes': [row['code'] for row in quality['findings']],
            'continued_from_final_review': isinstance(state, FollowupState),
            'ready_for_external_review': ready_for_external_review,
            'external_review_completed': False, 'external_review_token_reused': False,
            'semantic_review_certified': False, 'submission_ready': False,
            'new_scientific_model_calls': 0, 'resume_new_model_calls': 0 if resumed else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run', type=Path, help='Completed model-written paper with six verified sources')
    parser.add_argument('--output-run', type=Path)
    parser.add_argument('--continue-review', action='store_true',
                        help='Start with a model revision of the source run final review')
    parser.add_argument('--failed-attempt', type=Path,
                        help='Prior failed model revision to use as repair material; no request is resent')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare-only', action='store_true')
    mode.add_argument('--live', action='store_true')
    mode.add_argument('--offline', action='store_true', help='Scripted framework integration; no paid model')
    mode.add_argument('--resume', type=Path, help='Zero-API revalidation of saved raw role responses')
    args = parser.parse_args(argv)
    if args.resume and args.output_run:
        raise ValueError('conflicting_publication_loop_locations')
    root = args.resume or args.output_run
    if root is None:
        parser.error('--output-run or --resume required')
    root = root.resolve()
    if root.parent != (HERE / 'replay_paper_runs').resolve():
        raise ValueError('invalid_publication_loop_run_location')
    source = args.source_run
    if source is None and (root / 'input_provenance.json').exists():
        source = HERE / json.loads((root / 'input_provenance.json').read_text())['source_run_relative']
    if source is None:
        parser.error('--source-run required for new run')
    source = source.resolve()
    if source.parent != (HERE / 'replay_paper_runs').resolve() or source == root:
        raise ValueError('invalid_publication_loop_source')
    existed = (root / 'prepared.json').exists()
    saved = json.loads((root / 'prepared.json').read_text()) if existed else None
    continue_review = args.continue_review or (saved and saved.get('initial_role') == 'reviser_0')
    failed_attempt = args.failed_attempt
    if failed_attempt is None and existed:
        relative = json.loads((root / 'input_provenance.json').read_text()).get('failed_attempt_relative')
        if relative is not None:
            failed_attempt = HERE / relative
    if failed_attempt is not None and not continue_review:
        raise ValueError('failed_attempt_requires_followup')
    state = (FollowupState(root, source, live=args.live, failed_attempt=failed_attempt)
             if continue_review else LoopState(root, source, live=args.live))
    if existed:
        if (saved['input_sha256'] != digest(state.provenance)
                or saved.get('initial_role', 'writer') != state.expected_next()
                or loop_profile_digest() != state.profile_hash):
            raise ValueError('prepared_publication_loop_inputs_changed')
        if not args.resume and (not (args.live or args.offline)
                or (root / 'live_started.json').exists()
                or (root / 'model_summary.json').exists()
                or any(root.glob('raw_*'))):
            raise ValueError('existing_publication_loop_cannot_be_resent')
    else:
        if args.live or args.offline or args.resume:
            raise ValueError('prepare_publication_loop_before_execution')
        root.mkdir(parents=True, exist_ok=False)
        state.archive_inputs()
    if not (args.live or args.offline or args.resume):
        print(json.dumps({'status': 'prepared', 'output': str(root), 'model_calls': 0,
                          'planned_calls_maximum': 6, 'initial_role': state.expected_next()}))
        return 0
    os.chdir(root)
    try:
        if args.resume:
            sequence = json.loads((root / 'role_sequence.json').read_text())
            if not isinstance(sequence, list) or not 3 <= len(sequence) <= 6:
                raise ValueError('invalid_saved_role_sequence')
            for role in sequence:
                prompt = state.prompt(role)
                if (root / f'prompt_{role}.txt').read_text() != prompt:
                    raise ValueError('saved_publication_loop_prompt_changed')
                state.accept(role, state.decode_response((root / f'raw_{role}.txt').read_text()))
            if list(state.outputs) != sequence:
                raise ValueError('saved_role_sequence_changed')
        else:
            ledger = root / 'publication-loop-requests.jsonl'
            with ledger.with_suffix('.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with (root / 'live_started.json').open('x') as fence:
                    json.dump({'input_sha256': digest(state.provenance),
                               'automatic_retry': False, 'mode': 'live' if args.live else 'offline'}, fence)
                key = 'offline-placeholder'
                if args.live:
                    keys = re.findall(r'\bsk-[A-Za-z0-9_-]{16,}\b', (HERE.parent / 'apis.txt').read_text())
                    if len(keys) != 1:
                        raise ValueError('expected_one_credential')
                    key = keys[0]
                from run_recovery_v2 import provider_output_capacity
                asyncio.run(native_run(root, SKILL / 'scripts/workflow.py', state,
                    live=args.live, key=key, ledger=ledger, max_calls=6, token_stop=None,
                    timeout=3600, max_output_tokens=provider_output_capacity(),
                    team_name='publication_loop',
                    workflow_args={'initial_role': state.expected_next()}))
        if state.expected_next() is not None:
            raise ValueError('publication_loop_did_not_reach_final_review')
        metering = json.loads((root / 'model_summary.json').read_text())
        if (metering.get('status') != 'completed'
                or metering['model_calls'] != len(state.outputs)
                or len(metering['model_usage']) != len(state.outputs)):
            raise ValueError('publication_loop_usage_or_role_mismatch')
        paper = state.current_paper()
        write_json(root / 'paper.json', paper)
        rendered = copy.deepcopy(state.evidence)
        rendered['resource'].update(writing_model_calls=metering['model_calls'],
                                    writing_total_tokens=metering['total_tokens'])
        tex = render_publication(root, paper, state.sources, rendered)
        pdf = compile_pdf(root, tex, study_kind='recovery_v2')
        quality = audit_publication(paper, state.sources, root / 'paper.pdf')
        write_json(root / 'quality_audit.json', quality)
        summary = paper_summary(state, metering, pdf, quality, resumed=bool(args.resume))
        write_json(root / 'summary.json', summary)
        print(json.dumps({'output': str(root), **summary}, ensure_ascii=False))
        return 0
    except BaseException as error:
        write_json(root / 'failure.json', {'error_type': type(error).__name__,
            'model_summary_available': (root / 'model_summary.json').exists(),
            'automatic_retry': False})
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__,
                          'output': str(root)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
