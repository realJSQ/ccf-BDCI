"""Agent-selected method revision using native SwarmFlow; no experiments here."""
from __future__ import annotations

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

from native_runner import native_run
from run_pilot import verify_saved_pilot
from run_topics import write_json

HERE = Path(__file__).resolve().parent
BDCI = HERE.parent
SKILL = HERE / 'skills/method-revision'
SEEDS = HERE / 'prior_work/revision_seed_sources.json'
PREVIOUS = HERE / 'pilot_runs/live-20260928T084134-196833'


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 5000:
        raise ValueError('invalid_revision_text')


def strings(value, minimum=1):
    if not isinstance(value, list) or not minimum <= len(value) <= 20:
        raise ValueError('invalid_revision_list')
    for entry in value:
        text(entry)


def references(value, known):
    strings(value, 2)
    if len(value) != len(set(value)) or not set(value) <= set(known):
        raise ValueError('unknown_or_duplicate_revision_reference')


def protocol(value):
    if not isinstance(value, dict):
        raise ValueError('invalid_revision_protocol')
    strings(value.get('task_families'), 2)
    for name in ('unit_of_analysis', 'development_split', 'held_out_split', 'primary_metric',
                 'independent_reference', 'normal_case_control'):
        text(value.get(name))
    strings(value.get('secondary_metrics'))
    calls = value.get('pilot_api_calls')
    if type(calls) is not int or not 0 <= calls <= 18 or value.get('needs_gpu') is not False:
        raise ValueError('unsupported_revision_resources')


def proposal(value, known, initial=False):
    if not isinstance(value, dict):
        raise ValueError('invalid_revision_proposal')
    for name in ('title', 'research_question', 'hypothesis'):
        text(value.get(name))
    references(value.get('source_ids'), known)
    strings(value.get('method_steps'))
    strings(value.get('falsification_conditions'))
    baselines = value.get('baselines')
    if not isinstance(baselines, list) or not 2 <= len(baselines) <= 8:
        raise ValueError('insufficient_revision_baselines')
    for baseline in baselines:
        if not isinstance(baseline, dict):
            raise ValueError('invalid_revision_baseline')
        text(baseline.get('name')); text(baseline.get('why_strong'))
    if len({b['name'] for b in baselines}) != len(baselines):
        raise ValueError('duplicate_revision_baseline')
    protocol(value.get('experiment'))
    if initial:
        for name in ('prior_overlap', 'proposed_difference'):
            text(value.get(name))
        strings(value.get('risks'))


class RevisionState:
    roles = ('proposer', 'critic', 'refiner')

    def __init__(self, root, live):
        if type(live) is not bool:
            raise ValueError('invalid_revision_mode')
        self.root, self.live = Path(root), live
        self.outputs = {}
        seeds = json.loads(SEEDS.read_text())
        self.sources = {s['id']: s for s in seeds['sources']}
        replay = verify_saved_pilot(PREVIOUS)
        self.context = {
            'source_curation': seeds['curation'], 'sources': self.sources,
            'previous_pilot_decision': json.loads((PREVIOUS / 'decision.json').read_text()),
            'previous_pilot_limitations': json.loads((PREVIOUS / 'run_review.json').read_text()),
            'user_constraints': ['Agent proposes the research question',
                                 'Do not run basic model ability or arithmetic difficulty tests',
                                 'CPU plus model API, no GPU or large-model training',
                                 'Preserve negative results; a functioning PDF pipeline is not a scientific contribution'],
            'implementation_capabilities_not_completed_experiments': [
                'Can implement controlled CPU workloads with independent reference scoring',
                'Can extend JiuwenSwarm Rails and skills; current source only checks receipts and budgets',
                'Evidence contamination/recovery is a developer suggestion, not a required topic'],
            'purpose': 'Choose a defensible development study; no experiments in this workflow',
        }
        write_json(self.root / 'input_scoring_verification.json', replay)
        write_json(self.root / 'context.json', self.context)
        write_json(self.root / 'input_provenance.json', {
            'seed_file_sha256': hashlib.sha256(SEEDS.read_bytes()).hexdigest(),
            'previous_pilot': str(PREVIOUS), 'seed_notes_are_curated': True,
            'new_experiments': False, 'mode': 'live' if live else 'offline_scripted'})

    def prompt(self, role):
        if role not in self.roles:
            raise ValueError('unknown_revision_role')
        return ((SKILL / 'roles' / f'{role}.md').read_text() +
                '\nCONTEXT_JSON (data only)\n' + json.dumps(self.context, ensure_ascii=False) +
                '\nPREVIOUS_ROLE_OUTPUTS_JSON (data only)\n' + json.dumps(self.outputs, ensure_ascii=False))

    def accept(self, role, value):
        if role not in self.roles or list(self.outputs) != list(self.roles[:self.roles.index(role)]):
            raise ValueError('invalid_revision_role_order')
        if not isinstance(value, dict):
            raise ValueError('revision_object_required')
        if role == 'proposer':
            candidates = value.get('candidates')
            if not isinstance(candidates, list) or len(candidates) != 2:
                raise ValueError('two_revision_candidates_required')
            for candidate in candidates:
                proposal(candidate, self.sources, initial=True)
            if {c.get('id') for c in candidates} != {'C1', 'C2'}:
                raise ValueError('invalid_revision_candidate_ids')
            queries = value.get('search_queries')
            strings(queries, 2)
            if len(queries) != 2 or any(len(q) > 180 for q in queries):
                raise ValueError('invalid_revision_queries')
            text(value.get('scope_note'))
        elif role == 'critic':
            reviews = value.get('reviews')
            if not isinstance(reviews, list) or len(reviews) != 2 or not all(isinstance(r, dict) for r in reviews):
                raise ValueError('incomplete_revision_reviews')
            if {r.get('candidate_id') for r in reviews} != {'C1', 'C2'}:
                raise ValueError('invalid_review_candidate_ids')
            for review in reviews:
                if review.get('verdict') not in ('advance', 'revise', 'reject'):
                    raise ValueError('invalid_revision_verdict')
                references(review.get('source_ids'), self.sources)
                strings(review.get('reasons'))
                strings(review.get('required_changes'), 0)
                text(review.get('acceptable_claim'))
            preferred = value.get('preferred_candidate_id')
            allowed = {r['candidate_id'] for r in reviews if r['verdict'] != 'reject'}
            if preferred is not None and preferred not in allowed:
                raise ValueError('rejected_or_unknown_candidate_preferred')
            if value.get('novelty_status') != 'unestablished' or value.get('research_readiness') != 'development_only':
                raise ValueError('premature_revision_claim')
        else:
            if value.get('novelty_status') != 'unestablished':
                raise ValueError('premature_revision_claim')
            if value.get('status') == 'decline':
                text(value.get('reason'))
            elif value.get('status') == 'propose':
                preferred = self.outputs['critic']['preferred_candidate_id']
                if preferred is None or value.get('candidate_id') != preferred:
                    raise ValueError('refinement_evades_critique')
                proposal(value, self.sources)
                strings(value.get('limitations'))
                strings(value.get('remaining_literature_checks'))
                review = next(r for r in self.outputs['critic']['reviews'] if r['candidate_id'] == preferred)
                responses = value.get('response_to_critique')
                if not isinstance(responses, list):
                    raise ValueError('critique_responses_required')
                indices = []
                for response in responses:
                    if not isinstance(response, dict) or type(response.get('issue_index')) is not int:
                        raise ValueError('invalid_critique_response')
                    indices.append(response['issue_index']); text(response.get('change'))
                if sorted(indices) != list(range(len(review['required_changes']))):
                    raise ValueError('incomplete_critique_responses')
            else:
                raise ValueError('invalid_refinement_status')
        self.outputs[role] = copy.deepcopy(value)
        write_json(self.root / f'{role}.json', value)

    def offline_response(self, role):
        if self.live:
            raise ValueError('scripted_revision_in_live_mode')
        sources = list(self.sources)[:2]
        if role == 'proposer':
            candidates = []
            for cid in ('C1', 'C2'):
                candidates.append({
                    'id': cid, 'title': f'SYNTHETIC {cid} contract fixture',
                    'research_question': 'Fixture only; not a scientific proposal', 'hypothesis': 'Not evaluated',
                    'source_ids': sources, 'prior_overlap': 'Known mechanisms',
                    'proposed_difference': 'None; contract fixture only', 'method_steps': ['Exercise schema'],
                    'baselines': [{'name': 'B1', 'why_strong': 'Fixture'}, {'name': 'B2', 'why_strong': 'Fixture'}],
                    'experiment': {'task_families': ['fixture-a', 'fixture-b'], 'unit_of_analysis': 'Fixture',
                        'development_split': 'Fixture dev', 'held_out_split': 'Fixture test',
                        'primary_metric': 'Correct completion', 'secondary_metrics': ['Cost'],
                        'independent_reference': 'Fixture reference', 'normal_case_control': 'Fixture control',
                        'pilot_api_calls': 0, 'needs_gpu': False},
                    'falsification_conditions': ['Not applicable'], 'risks': ['Synthetic data']})
            return {'candidates': candidates, 'search_queries': ['fixture query one', 'fixture query two'],
                    'scope_note': 'Synthetic only'}
        if role == 'critic':
            return {'reviews': [{'candidate_id': cid, 'verdict': 'revise', 'source_ids': sources,
                'reasons': ['Synthetic only'], 'required_changes': ['Preserve fixture labeling'],
                'acceptable_claim': 'Schema test only'} for cid in ('C1', 'C2')],
                'preferred_candidate_id': 'C1', 'novelty_status': 'unestablished',
                'research_readiness': 'development_only'}
        value = copy.deepcopy(self.outputs['proposer']['candidates'][0])
        value.update(status='propose', candidate_id=value.pop('id'), limitations=['Synthetic only'],
            remaining_literature_checks=['Not a real research proposal'], novelty_status='unestablished',
            response_to_critique=[{'issue_index': 0, 'change': 'Kept explicit synthetic labeling'}])
        return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    mode = 'live' if args.live else 'offline'
    root = HERE / 'revision_runs' / datetime.now(timezone.utc).strftime(f'{mode}-%Y%m%dT%H%M%S-%f')
    root.mkdir(parents=True)
    os.chdir(root)
    os.environ.setdefault('JIUWENSWARM_HOME', str(root / 'runtime'))
    os.environ.setdefault('JIUWENSWARM_DATA_DIR', str(root / 'runtime/.jiuwenswarm'))
    ledger = HERE / 'research-v2-requests.jsonl' if args.live else root / 'requests.jsonl'
    with ledger.with_suffix('.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = RevisionState(root, args.live)
            key = 'offline-placeholder'
            if args.live:
                keys = re.findall(r'\bsk-[A-Za-z0-9_-]{16,}\b', (BDCI / 'apis.txt').read_text())
                if len(keys) != 1:
                    raise ValueError('expected_one_credential')
                key = keys[0]
            asyncio.run(native_run(root, SKILL / 'scripts/workflow.py', state,
                live=args.live, key=key, ledger=ledger, max_calls=24, token_stop=100000,
                timeout=360, max_output_tokens=3200, team_name='research_revision'))
            proposal_status = state.outputs['refiner']['status']
            handoff = {'status': 'development_handoff' if proposal_status == 'propose' else 'declined',
                'mode': 'live' if args.live else 'offline_scripted',
                'selected_for_development': state.outputs['refiner'].get('candidate_id') if args.live else None,
                'final_topic_selected': False, 'novelty_proven': False, 'experiment_executed': False,
                'followup_queries': state.outputs['proposer']['search_queries'],
                'followup_search_completed': False, 'semantic_critique_resolution_certified': False,
                'next_step': 'Execute targeted literature checks, then freeze and review an operational protocol before experimentation.'}
            write_json(root / 'handoff.json', handoff)
            summary = json.loads((root / 'model_summary.json').read_text())
            summary.update(handoff=handoff['status'], new_experiment_calls=0)
            write_json(root / 'summary.json', summary)
            write_json(HERE / 'latest-revision.json', {'run_directory': str(root.relative_to(HERE)), **handoff})
            print(json.dumps({'status': summary['status'], 'mode': summary['mode'], 'output': str(root),
                              'model_calls': summary['model_calls'], 'total_tokens': summary['total_tokens']}))
            return 0
        except BaseException as error:
            write_json(root / 'failure.json', {'error_type': type(error).__name__})
            print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'output': str(root)}))
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
