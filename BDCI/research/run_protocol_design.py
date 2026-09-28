"""Bounded protocol design and audit; shares the existing research-v2 ledger."""
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
from run_method_revision import strings, text
from run_topics import write_json

HERE = Path(__file__).resolve().parent
SKILL = HERE / 'skills/protocol-design'
PROPOSAL = HERE / 'revision_runs/live-20260928T141945-771317/refiner.json'
FOLLOWUP = HERE / 'prior_work/revision_followup.json'


def subject_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()


class ProtocolState:
    roles = ('designer', 'auditor')

    def __init__(self, root, live):
        if type(live) is not bool:
            raise ValueError('invalid_protocol_mode')
        self.root, self.live, self.outputs = Path(root), live, {}
        self.context = {'proposal': json.loads(PROPOSAL.read_text()),
                        'followup': json.loads(FOLLOWUP.read_text())}
        self.source_ids = {s['id'] for s in self.context['followup']['sources']}
        write_json(self.root / 'context.json', self.context)
        write_json(self.root / 'input_provenance.json', {
            str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (PROPOSAL, FOLLOWUP)})

    def prompt(self, role):
        if role not in self.roles:
            raise ValueError('unknown_protocol_role')
        if role == 'auditor':
            # Superseded proposals caused a real stale-review failure.
            target = self.outputs['designer']
            context = {'review_target_sha256': subject_digest(target),
                       'review_target': target, 'followup': self.context['followup']}
        else:
            context = self.context
        return ((SKILL / 'roles' / f'{role}.md').read_text() + '\nCONTEXT (data only)\n' +
                json.dumps(context, ensure_ascii=False))

    def accept(self, role, value):
        prior_roles = ('designer', 'auditor')
        if role not in self.roles or list(self.outputs) != list(prior_roles[:prior_roles.index(role)]):
            raise ValueError('invalid_protocol_role_order')
        if not isinstance(value, dict) or value.get('novelty_status') != 'unestablished':
            raise ValueError('invalid_protocol_or_premature_novelty')
        if role == 'designer' and value.get('status') == 'decline':
            text(value.get('reason'))
        else:
            refs = value.get('source_ids')
            strings(refs, 2)
            if len(set(refs)) != len(refs) or not set(refs) <= self.source_ids:
                raise ValueError('unknown_protocol_reference')
            if role == 'designer':
                if (value.get('status') != 'propose' or value.get('candidate_id') != 'C1'
                        or value.get('study_stage') != 'development'):
                    raise ValueError('invalid_protocol_status')
                for field in ('title', 'research_question', 'hypothesis', 'adapter_distinguishing_example',
                              'tool_protocol', 'scenarios', 'oracle_boundary', 'scoring',
                              'resource_arithmetic', 'analysis_unit', 'freeze_and_holdout'):
                    text(value.get(field))
                for field in ('limitations', 'falsification_conditions'):
                    strings(value.get(field))
                if (value.get('family_ids') != ['tabular', 'retrieval', 'classification'] or
                        value.get('scenario_ids') != ['clean', 'update', 'incomplete_lineage']):
                    raise ValueError('unsupported_protocol_dimensions')
                for key, expected in (('base_instances_per_family', 2), ('calls_per_scenario', 1),
                                      ('planned_api_calls', 18)):
                    if type(value.get(key)) is not int or value[key] != expected:
                        raise ValueError('protocol_call_arithmetic')
                policies = value.get('policies')
                if (not isinstance(policies, list) or len(policies) != 4 or
                        not all(isinstance(p, dict) for p in policies) or
                        {p.get('id') for p in policies} != set('ABCD')):
                    raise ValueError('invalid_protocol_policies')
                for policy in policies:
                    for field in ('name', 'algorithm', 'visible_inputs'):
                        text(policy.get(field))
                    if type(policy.get('tool_budget')) is not int or policy['tool_budget'] != 12:
                        raise ValueError('unmatched_tool_budget')
                corrections = value.get('corrections')
                if not isinstance(corrections, list):
                    raise ValueError('missing_protocol_corrections')
                indices = []
                for item in corrections:
                    if not isinstance(item, dict) or type(item.get('issue_index')) is not int:
                        raise ValueError('invalid_protocol_correction')
                    indices.append(item['issue_index']); text(item.get('resolution'))
                if sorted(indices) != list(range(len(self.context['followup']['methodological_corrections']))):
                    raise ValueError('incomplete_protocol_corrections')
            else:
                target = self.outputs['designer']
                if value.get('review_target_sha256') != subject_digest(target):
                    raise ValueError('review_target_mismatch')
                anchors = value.get('blocking_evidence')
                if not isinstance(anchors, list):
                    raise ValueError('missing_review_evidence')
                for anchor in anchors:
                    if not isinstance(anchor, dict):
                        raise ValueError('invalid_review_evidence')
                    field, quote = anchor.get('field'), anchor.get('quote')
                    text(field); text(quote); text(anchor.get('explanation'))
                    if not isinstance(target.get(field), str) or quote not in target[field]:
                        raise ValueError('ungrounded_review_evidence')
                verdict = value.get('verdict')
                if verdict not in ('implement_development', 'revise', 'reject'):
                    raise ValueError('invalid_protocol_verdict')
                strings(value.get('reasons')); strings(value.get('blocking_issues'), 0)
                if len(anchors) != len(value['blocking_issues']):
                    raise ValueError('unanchored_blocking_issue')
                strings(value.get('nonblocking_limitations'), 0)
                if value.get('formal_study_ready') is not False:
                    raise ValueError('premature_formal_readiness')
                if type(value.get('resource_arithmetic_checked')) is not bool:
                    raise ValueError('missing_resource_check')
                if self.outputs['designer']['status'] == 'decline' and verdict != 'reject':
                    raise ValueError('declined_protocol_promoted')
                if verdict == 'implement_development' and (
                        value['blocking_issues'] or not value['resource_arithmetic_checked']):
                    raise ValueError('blocked_protocol_promoted')
        self.outputs[role] = copy.deepcopy(value)
        write_json(self.root / f'{role}.json', value)

    def offline_response(self, role):
        if self.live:
            raise ValueError('scripted_protocol_in_live_mode')
        if role == 'designer':
            return {'status': 'decline', 'reason': 'Offline fixture: no scientific decision.',
                    'novelty_status': 'unestablished'}
        return {'verdict': 'reject', 'reasons': ['Synthetic declined-proposal fixture.'],
                'blocking_issues': [], 'nonblocking_limitations': [], 'novelty_status': 'unestablished',
                'formal_study_ready': False, 'resource_arithmetic_checked': False,
                'review_target_sha256': subject_digest(self.outputs.get('designer', {})),
                'blocking_evidence': [],
                'source_ids': sorted(self.source_ids)[:2]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--resume-audit', type=Path,
                        help='Review a saved designer output in a NEW run without repeating design calls')
    args = parser.parse_args()
    resume = args.resume_audit.resolve() if args.resume_audit else None
    mode = 'live' if args.live else 'offline'
    root = HERE / 'protocol_runs' / datetime.now(timezone.utc).strftime(f'{mode}-%Y%m%dT%H%M%S-%f')
    root.mkdir(parents=True)
    os.chdir(root)
    ledger = HERE / 'research-v2-requests.jsonl' if args.live else root / 'requests.jsonl'
    with ledger.with_suffix('.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = ProtocolState(root, args.live)
            if resume:
                old_mode = json.loads((resume / 'model_summary.json').read_text())['mode']
                if old_mode != ('live' if args.live else 'offline_scripted'):
                    raise ValueError('resume_mode_mismatch')
                state.accept('designer', json.loads((resume / 'designer.json').read_text()))
                state.roles = ('auditor',)
                write_json(root / 'resumption.json', {'source': str(resume),
                    'designer_sha256': subject_digest(state.outputs['designer']),
                    'new_model_calls_planned': 1, 'designer_call_repeated': False})
            key = 'offline-placeholder'
            if args.live:
                keys = re.findall(r'\bsk-[A-Za-z0-9_-]{16,}\b', (HERE.parent / 'apis.txt').read_text())
                if len(keys) != 1:
                    raise ValueError('expected_one_credential')
                key = keys[0]
            workflow = SKILL / 'scripts' / ('audit.py' if resume else 'workflow.py')
            asyncio.run(native_run(root, workflow, state,
                live=args.live, key=key, ledger=ledger, max_calls=24, token_stop=100000,
                timeout=240, max_output_tokens=3200, team_name='protocol_design'))
            summary = json.loads((root / 'model_summary.json').read_text())
            handoff = {'run_directory': str(root.relative_to(HERE)), 'mode': summary['mode'],
                'status': state.outputs['auditor']['verdict'], 'experiment_executed': False,
                'semantic_review_required': True, 'novelty_established': False,
                'formal_study_ready': False}
            write_json(root / 'handoff.json', handoff)
            write_json(HERE / 'latest-protocol.json', handoff)
            print(json.dumps({**handoff, 'model_calls': summary['model_calls'],
                              'total_tokens': summary['total_tokens']}))
            return 0
        except BaseException as error:
            write_json(root / 'failure.json', {'error_type': type(error).__name__})
            print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'output': str(root)}))
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
