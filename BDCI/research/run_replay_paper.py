"""Native writing/review/revision of verified recovery-study evidence."""
import argparse
import asyncio
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from native_runner import native_run
from paper_contracts import validate_paper, validate_review, validate_revision_response, SECTION_IDS
from replay_paper_evidence import build_evidence, sources, digest, DEFAULT_RUN
from run_topics import write_json, parse_object
from study_adapter import get_adapter

HERE = Path(__file__).resolve().parent
SKILL = HERE / 'skills/replay-paper'


def select_study_run(explicit=None, saved=None):
    """Select local study inputs without silently replacing missing saved inputs."""
    if explicit is not None:
        selected = Path(explicit).resolve()
    elif saved is not None:
        relative = saved.get('study_run_relative')
        if relative is not None:
            relative = Path(relative)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('unsafe_saved_study_path')
            selected = (HERE / relative).resolve()
            if not selected.is_relative_to(HERE):
                raise ValueError('unsafe_saved_study_path')
        else:
            selected = Path(saved['run'])
            if not selected.is_absolute():
                raise ValueError('ambiguous_legacy_study_path')
    else:
        selected = DEFAULT_RUN
    if not selected.is_dir():
        raise ValueError('study_missing_supply_study_run')
    return selected.resolve()


class ReplayPaperState:
    roles = ('writer', 'reviewer', 'reviser')

    def __init__(self, root, live, run=DEFAULT_RUN, expected_provenance=None, study_kind='replay_v1'):
        if type(live) is not bool:
            raise ValueError('invalid_paper_mode')
        self.root, self.live, self.outputs = Path(root), live, {}
        self.adapter = get_adapter(study_kind)
        self.profile_hash = self.adapter.profile_sha256() if self.adapter.is_v2 else None
        if expected_provenance is not None and expected_provenance.get('study_kind', 'replay_v1') != study_kind:
            raise ValueError('paper_study_kind_changed')
        if self.adapter.is_v2 and expected_provenance is not None and expected_provenance.get('profile_sha256') != self.adapter.profile_sha256():
            raise ValueError('paper_profile_changed')
        run = Path(run).resolve()
        self.evidence = self.adapter.build_evidence(run) if self.adapter.is_v2 else build_evidence(run)
        self.sources = sources()
        if expected_provenance is not None and (
                expected_provenance['evidence_sha256'] != digest(self.evidence)
                or expected_provenance['sources_sha256'] != digest(self.sources)):
            raise ValueError('paper_input_changed')
        write_json(self.root / 'evidence.json', self.evidence)
        write_json(self.root / 'sources.json', self.sources)
        provenance = {'run': str(run),
            'evidence_sha256': digest(self.evidence), 'sources_sha256': digest(self.sources),
            'study_run_relative': str(run.relative_to(HERE)) if run.is_relative_to(HERE) else None,
            'new_scientific_model_calls': 0}
        if self.adapter.is_v2:
            provenance.update(study_kind=study_kind, evidence_schema=self.evidence['schema'],
                              profile_sha256=self.adapter.profile_sha256())
        write_json(self.root / 'input_provenance.json', provenance)

    def decode_response(self, raw):
        return self.adapter.decode(raw)

    def prompt(self, role):
        if self.adapter.is_v2 and self.adapter.profile_sha256() != self.profile_hash:
            raise ValueError('paper_profile_changed_during_run')
        data = {'current_evidence': self.evidence, 'sources': self.sources,
                'evidence_sha256': digest(self.evidence)}
        if self.adapter.is_v2:
            # Keep all scientific fields while omitting local paths and long
            # file-hash inventories from the provider context. The full saved
            # evidence remains bound by evidence_sha256 and bundle verification.
            data['current_evidence'] = copy.deepcopy(self.evidence)
            data['current_evidence'].pop('artifact_sha256', None)
            for key in ('source_sha256', 'frozen_snapshot_sha256', 'public_input_sha256'):
                data['current_evidence']['protocol'].pop(key, None)
            data['evidence_presentation'] = 'Scientific evidence is complete; local path and file hash inventories are omitted. evidence_sha256 identifies the full archived evidence.'
        if role != 'writer':
            data.update(current_draft=self.outputs['writer'], draft_sha256=digest(self.outputs['writer']))
            draft = self.outputs['writer']
            data['draft_word_count'] = sum(len(t.split()) for t in
                [draft['title'], draft['abstract'], *[s['text'] for s in draft['sections']]])
            data['final_word_limit'] = None if self.adapter.is_v2 else 1600
        if role == 'reviser':
            data['internal_review'] = self.outputs['reviewer']
        return (self.adapter.skill / 'roles' / f'{role}.md').read_text() + '\nCURRENT_DATA_JSON\n' + json.dumps(data)

    def accept(self, role, value):
        if role not in self.roles or list(self.outputs) != list(self.roles[:self.roles.index(role)]):
            raise ValueError('paper_role_order')
        if role == 'reviewer':
            if not isinstance(value, dict) or set(value) != {
                    'verdict', 'external_reviewer', 'issues', 'revision_instructions',
                    'draft_sha256', 'evidence_sha256', 'issue_quotes'}:
                raise ValueError('invalid_bound_review')
            if value['draft_sha256'] != digest(self.outputs['writer']) or value['evidence_sha256'] != digest(self.evidence):
                raise ValueError('review_target_mismatch')
            review = {k: value[k] for k in ('verdict', 'external_reviewer', 'issues', 'revision_instructions')}
            review = copy.deepcopy(review)
            for issue in review['issues']:
                # Preserve the original response, but permit a redundant exact
                # section annotation. Never guess or rewrite the target section.
                if 'section_id_note' in issue:
                    if issue['section_id_note'] != issue.get('section_id'):
                        raise ValueError('conflicting_section_annotation')
                    issue.pop('section_id_note')
            validate_review(review, self.outputs['writer'], **({'max_field_chars': None} if self.adapter.is_v2 else {}))
            quotes = value['issue_quotes']
            if not isinstance(quotes, list) or len(quotes) != len(review['issues']):
                raise ValueError('unanchored_review')
            sections = {s['id']: s['text'] for s in self.outputs['writer']['sections']}
            sections['abstract'] = self.outputs['writer']['abstract']
            for issue, quote in zip(review['issues'], quotes):
                if not isinstance(quote, str) or not quote.strip() or quote not in sections[issue['section_id']]:
                    raise ValueError('ungrounded_review')
        else:
            # Model drafts may reach local editorial review; rendering always
            # rechecks the final paper with the original 1600-word default.
            validate_paper(value, self.sources, **(self.adapter.paper_limits if self.adapter.is_v2 else {'max_words': 1800}))
            if role == 'reviser':
                validate_revision_response(value, self.outputs['reviewer'], **({'max_field_chars': None} if self.adapter.is_v2 else {}))
                if (any(i['severity'] in ('blocking', 'major') for i in self.outputs['reviewer']['issues'])
                    and all(value[k] == self.outputs['writer'][k] for k in ('title', 'abstract', 'sections'))):
                    raise ValueError('major_review_without_revision')
        self.outputs[role] = copy.deepcopy(value)
        write_json(self.root / f'{role}.json', value)

    def offline_response(self, role):
        if self.live:
            raise ValueError('scripted_paper_in_live_mode')
        if role == 'writer':
            if self.adapter.is_v2:
                return {'title': 'Static dependency recovery: integration fixture',
                    'abstract': 'This scripted manuscript validates the evidence-to-PDF pipeline and is not a new scientific result.',
                    'sections': [{'id': name, 'text': 'This developer-scripted section tests the manuscript pipeline. '
                        'The saved study concerns self-authored structural held-out workflows with shared static tool contracts. '
                        'The deterministic baseline requires no model plan. Replays and scenarios are repeated measures. '
                        'Developer intervention in protocol revision is recorded; no autonomous discovery or generalization is claimed.',
                        'source_ids': list(self.sources) if name == 'related_work' else []} for name in SECTION_IDS]}
            return {'title': 'Recovery replay: a development study',
                'abstract': 'A scripted integration manuscript using saved measurements. It establishes no new research result.',
                'sections': [{'id': name, 'text': 'This scripted section exercises the manuscript pipeline. '
                    'Strict results and post-hoc diagnostic normalization remain separate. '
                    'Selective replay showed no incremental benefit over model plans. '
                    'The small self-authored sample provides no independent confirmation.',
                    'source_ids': list(self.sources) if name == 'related_work' else []} for name in SECTION_IDS]}
        if role == 'reviewer':
            return {'verdict': 'pass', 'issues': [], 'revision_instructions': [], 'external_reviewer': False,
                'draft_sha256': digest(self.outputs['writer']), 'evidence_sha256': digest(self.evidence), 'issue_quotes': []}
        return {**copy.deepcopy(self.outputs['writer']), 'response_to_review': []}


def compile_pdf(root, tex, *, study_kind='replay_v1'):
    command = ['bash', str(HERE.parent / 'tools/compile-latex.sh'), '--only-cached', '--keep-logs', str(tex)]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=90)
    (root / 'compile.stdout').write_text(result.stdout)
    (root / 'compile.stderr').write_text(result.stderr)
    if result.returncode:
        raise ValueError('paper_compilation_failed')
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(str(root / 'paper.pdf'))
    extracted = []
    for page in document:
        tp = page.get_textpage(); extracted.append(tp.get_text_range()); tp.close(); page.close()
    pages = len(document); document.close()
    body = '\n'.join(extracted)
    (root / 'paper_extracted.txt').write_text(body)
    required = ('results', 'references') if study_kind == 'recovery_v2' else ('results', 'references', 'post-hoc')
    if not all(word in body.lower() for word in required):
        raise ValueError('missing_paper_content')
    if 'published as a conference paper' in body.lower():
        raise ValueError('false_publication_header')
    if re.search(r'Citation .* undefined|There were undefined references', (root / 'paper.log').read_text()):
        raise ValueError('undefined_citation')
    return {'pages': pages, 'bytes': (root / 'paper.pdf').stat().st_size,
            'sha256': hashlib.sha256((root / 'paper.pdf').read_bytes()).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--study-kind', choices=('replay_v1', 'recovery_v2'))
    parser.add_argument('--study-run', type=Path, help='Completed compatible recovery study; saved input is reused on resume')
    parser.add_argument('--resume', type=Path, help='Revalidate saved raw outputs and compile, no API')
    parser.add_argument('--continue-from', type=Path, help='Continue a writer-only run with review/revision')
    parser.add_argument('--editorial-file', type=Path, help='Explicit locally edited final paper; records assistance')
    parser.add_argument('--output-run', type=Path, help='New run directory within replay_paper_runs, for a coordinating workflow')
    parser.add_argument('--no-latest', action='store_true', help='Do not change the shared latest-paper pointer')
    args = parser.parse_args(argv)
    if args.output_run and args.resume:
        raise ValueError('output_run_conflicts_with_resume')
    if args.output_run:
        output_run = args.output_run.resolve()
        if output_run.parent != (HERE / 'replay_paper_runs').resolve():
            raise ValueError('invalid_output_run_location')
    editorial = args.editorial_file.resolve() if args.editorial_file else None
    if args.resume and args.continue_from:
        raise ValueError('conflicting_continuation_modes')
    continuation = args.continue_from.resolve() if args.continue_from else None
    inherited = None
    saved_input = None
    if continuation:
        if not continuation.is_relative_to(HERE / 'replay_paper_runs'):
            raise ValueError('invalid_continuation_location')
        inherited = json.loads((continuation / 'model_summary.json').read_text())
        if (continuation / 'continuation.json').exists():
            ancestor = json.loads((continuation / 'continuation.json').read_text())['source_summary']
            inherited = {**inherited, 'model_calls': inherited['model_calls'] + ancestor['model_calls'],
                         'total_tokens': inherited['total_tokens'] + ancestor['total_tokens']}
        if inherited['model_calls'] not in (1, 2) or (continuation / 'raw_reviser.txt').exists():
            raise ValueError('continuation_requires_unfinished_review_or_revision')
        args.live = inherited['mode'] == 'live'
        saved_input = json.loads((continuation / 'input_provenance.json').read_text())
    if args.resume:
        root = args.resume.resolve()
        if not root.is_relative_to(HERE / 'replay_paper_runs'):
            raise ValueError('invalid_resume_location')
        args.live = json.loads((root / 'model_summary.json').read_text())['mode'] == 'live'
        saved_input = json.loads((root / 'input_provenance.json').read_text())
    else:
        root = output_run if args.output_run else HERE / 'replay_paper_runs' / datetime.now(timezone.utc).strftime(
            ('live' if args.live else 'offline') + '-%Y%m%dT%H%M%S-%f')
        root.mkdir(parents=True, exist_ok=False)
    study_run = select_study_run(args.study_run, saved_input)
    study_kind = args.study_kind or (saved_input or {}).get('study_kind', 'replay_v1')
    adapter = get_adapter(study_kind)
    os.chdir(root)
    try:
        state = ReplayPaperState(root, args.live, run=study_run, expected_provenance=saved_input, study_kind=study_kind)
        if continuation:
            saved_roles = ['writer'] + (['reviewer'] if (continuation / 'raw_reviewer.txt').exists() else [])
            if len(saved_roles) != inherited['model_calls']:
                raise ValueError('continuation_accounting_mismatch')
            raw_hashes = {}
            for role in saved_roles:
                raw = (continuation / f'raw_{role}.txt').read_text()
                state.accept(role, adapter.decode(raw))
                (root / f'raw_{role}.txt').write_text(raw)
                raw_hashes[role] = hashlib.sha256(raw.encode()).hexdigest()
            write_json(root / 'continuation.json', {'source': str(continuation),
                'source_summary': inherited, 'writer_repeated': False,
                'saved_raw_sha256': raw_hashes, 'new_model_calls_planned': 3 - len(saved_roles),
                'draft_review_admission_limit': None if adapter.is_v2 else 1800,
                'final_word_limit': None if adapter.is_v2 else 1600})
        ledger = HERE / ('recovery-v2-paper-requests.jsonl' if adapter.is_v2 else 'replay-paper-v1-requests.jsonl') if args.live else root / 'requests.jsonl'
        with ledger.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.resume:
                for role in state.roles:
                    state.accept(role, adapter.decode((root / f'raw_{role}.txt').read_text()))
                write_json(root / 'recovery.json', {'new_model_calls': 0, 'evidence_verified': True})
            else:
                key = 'offline-placeholder'
                if args.live:
                    keys = re.findall(r'\bsk-[A-Za-z0-9_-]{16,}\b', (HERE.parent / 'apis.txt').read_text())
                    if len(keys) != 1:
                        raise ValueError('expected_one_credential')
                    key = keys[0]
                workflow = adapter.skill / 'scripts' / ('continue.py' if continuation else 'workflow.py')
                if continuation and len(saved_roles) == 2:
                    workflow = root / 'continued_workflow.py'
                    workflow.write_text('from swarmflow import agent, phase\n'
                        'META={"name":"saved-review-revision","description":"Revise saved reviewed draft",'
                        '"phases":["Revise"],"workflow_token_limit":60000}\n'
                        'async def run(args):\n    phase("Revise")\n'
                        '    result = await agent("Revise the saved draft.", label="reviser", '
                        'options={"agent_type":"reviser","timeout":100})\n'
                        '    if not result: raise RuntimeError("missing_revision")\n    return result\n')
                    if adapter.is_v2:
                        workflow.write_text(workflow.read_text().replace(',"workflow_token_limit":60000', ''))
                from run_recovery_v2 import provider_output_capacity
                asyncio.run(native_run(root, workflow, state, live=args.live,
                    key=key, ledger=ledger, max_calls=3, token_stop=None if adapter.is_v2 else 60000, timeout=900 if adapter.is_v2 else 360,
                    max_output_tokens=provider_output_capacity() if adapter.is_v2 else 5000, team_name='recovery_v2_paper' if adapter.is_v2 else 'replay_paper'))
        from replay_paper_render import render_replay_paper
        metering = json.loads((root / 'model_summary.json').read_text())
        if args.resume and (root / 'continuation.json').exists():
            inherited = json.loads((root / 'continuation.json').read_text())['source_summary']
        total_calls = metering['model_calls'] + (inherited['model_calls'] if inherited else 0)
        total_tokens = metering['total_tokens'] + (inherited['total_tokens'] if inherited else 0)
        rendered_evidence = copy.deepcopy(state.evidence)
        rendered_evidence['resource'].update(writing_model_calls=total_calls, writing_total_tokens=total_tokens)
        paper = state.outputs['reviser']
        if editorial:
            paper = adapter.decode(editorial.read_text())
            validate_paper(paper, state.sources, **adapter.paper_limits)
            validate_revision_response(paper, state.outputs['reviewer'], **({'max_field_chars': None} if adapter.is_v2 else {}))
            write_json(root / 'editorial_revision.json', paper)
            write_json(root / 'editorial_assistance.json', {
                'authorship': 'Coding assistant local editorial pass, not a new model response',
                'original_model_revision_sha256': digest(state.outputs['reviser']),
                'final_paper_sha256': digest(paper), 'new_model_calls': 0,
                'reason': 'Explicit local editorial revision' if adapter.is_v2 else 'Model revision remained oversized and its claims of condensation were not supported.',
                'edits': 'See the preserved original revision and editorial_revision.json for the exact changes.' if adapter.is_v2 else 'Condensed abstract, introduction and conclusion; retained methods/results limitations; removed redundant inline source IDs already rendered as citations.'})
        write_json(root / 'paper.json', paper)
        tex = adapter.render(root, paper, state.sources, rendered_evidence, metering['mode'])
        pdf = compile_pdf(root, tex, study_kind=study_kind)
        summary = {'status': 'manuscript_generated', 'mode': metering['mode'], 'pdf': pdf,
            'writing_model_calls': total_calls, 'writing_total_tokens': total_tokens,
            'new_scientific_model_calls': 0, 'external_review_completed': False,
            'editorial_assistance': editorial is not None,
            'semantic_review_certified': False, 'submission_ready': False}
        write_json(root / 'summary.json', summary)
        if adapter.is_v2:
            summary['study_kind'] = study_kind
            write_json(root / 'summary.json', summary)
        if not args.no_latest:
            pointer = 'latest-recovery-v2-paper.json' if adapter.is_v2 else 'latest-replay-paper.json'
            write_json(HERE / pointer, {'run_directory': str(root.relative_to(HERE)), **summary})
        print(json.dumps({'output': str(root), **summary}))
        return 0
    except BaseException as error:
        write_json(root / 'failure.json', {'error_type': type(error).__name__})
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'output': str(root)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
