"""Design and audit a follow-up to frozen negative evidence; never execute it."""
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
from protocol_graph import analyze_graph_example
from replay_paper_evidence import build_evidence, sources, digest
from run_method_revision import text, strings, references
from run_topics import write_json

HERE = Path(__file__).resolve().parent
SKILL = HERE / 'skills/followup-design'
FOLLOWUP = HERE / 'prior_work/revision_followup.json'
SOURCE_CHECK = HERE / 'prior_work/followup_design_source_check.json'
PREVIOUS_ASSESSMENT = HERE / 'followup_design_runs/live-20260929T003516-680636/followup_assessment.json'


def revision_context(state):
    """Attach the rejected attempt and executable diagnostics to a new design.

    This is a separately metered design revision, never a budget reset or an
    implementation approval. Developer examples are explicitly not observations.
    """
    from check_recovery_example import check_example
    assessment = json.loads(PREVIOUS_ASSESSMENT.read_text())
    if (assessment['status'] != 'not_implementation_ready'
            or assessment['proposal_input_accepted'] is not False
            or assessment['model_audit_accepted'] is not False):
        raise ValueError('unexpected_previous_design_state')
    examples = {name: json.loads((HERE / f'protocol_examples/{name}.json').read_text())
                for name in ('inconsistent', 'consistent')}
    state.context['revision'] = {
        'previous_assessment': assessment,
        'previous_assessment_sha256': hashlib.sha256(PREVIOUS_ASSESSMENT.read_bytes()).hexdigest(),
        'developer_examples_not_scientific_observations': {
            name: {'input': value, 'computed': check_example(value)} for name, value in examples.items()},
        'instruction': 'Propose a complete corrected design or decline. Do not fill in the truncated old response. '
            'Choose the research question yourself within the existing scope. New task structures and splits '
            'must be specified concretely before results; the six old instances cannot become held-out evidence. '
            'Use brief prose, preferably under 35 words per text field, and a small complete graph_example. '
            'A measured boundary or negative outcome is valid; no positive result is required. '
            'Describe exact intervention and strong baseline algorithms, visible information, actual outputs '
            'and a separate scoring oracle. Runtime tool actions need not use additional model calls. '
            'Do not assume diagnostic access unavailable to the baseline. '
            'For the auditor, quote string-field text exactly; never use a numeric field as a quotation anchor.'}
    state.evidence_sha256 = digest(state.context)
    write_json(state.root / 'context.json', state.context)
    provenance = json.loads((state.root / 'input_provenance.json').read_text())
    provenance.update(context_sha256=state.evidence_sha256,
                      previous_assessment_sha256=state.context['revision']['previous_assessment_sha256'])
    write_json(state.root / 'input_provenance.json', provenance)


def complete_top_level_fields(raw):
    """Decode complete values only, without closing or repairing truncated values."""
    start = raw.find('{')
    if start < 0:
        raise ValueError('missing_truncated_object')
    decoder, result, offset = json.JSONDecoder(), {}, start + 1
    while True:
        while offset < len(raw) and raw[offset].isspace():
            offset += 1
        if offset >= len(raw) or raw[offset] == '}':
            return result
        try:
            key, offset = decoder.raw_decode(raw, offset)
        except json.JSONDecodeError:
            return result
        if not isinstance(key, str) or key in result:
            raise ValueError('invalid_or_duplicate_truncated_key')
        while offset < len(raw) and raw[offset].isspace():
            offset += 1
        if offset >= len(raw):
            return result
        if raw[offset] != ':':
            raise ValueError('invalid_truncated_separator')
        offset += 1
        while offset < len(raw) and raw[offset].isspace():
            offset += 1
        try:
            value, end = decoder.raw_decode(raw, offset)
        except json.JSONDecodeError:
            return result
        while end < len(raw) and raw[end].isspace():
            end += 1
        if end >= len(raw) or raw[end] not in ',}':
            return result
        result[key] = value
        if raw[end] == '}':
            return result
        offset = end + 1


def recover_rejected(state, source):
    source = Path(source).resolve()
    recovery = json.loads((source / 'truncation_recovery.json').read_text())
    raw = (source / 'truncated_designer.txt').read_bytes()
    if (recovery.get('finish_reason') != 'length' or recovery.get('accepted_as_designer') is not False
            or recovery.get('sha256') != hashlib.sha256(raw).hexdigest()
            or recovery.get('bytes') != len(raw) or recovery.get('new_model_calls') != 0):
        raise ValueError('invalid_truncation_provenance')
    context = json.loads((source / 'context.json').read_text())
    provenance = json.loads((source / 'input_provenance.json').read_text())
    current = json.loads((state.root / 'input_provenance.json').read_text())
    if digest(context) != state.evidence_sha256 or provenance != current:
        raise ValueError('recovery_context_mismatch')
    summary = json.loads((source / 'model_summary.json').read_text())
    usage = summary.get('model_usage', [])
    original_usage = [json.loads(line) for line in (source / 'model_usage.jsonl').read_text().splitlines() if line.strip()]
    if original_usage != usage or sum(row['total_tokens'] for row in original_usage) != summary.get('total_tokens'):
        raise ValueError('recovery_original_usage_mismatch')
    if (summary.get('mode') != ('live' if state.live else 'offline_scripted')
            or summary.get('status') != 'failed' or summary.get('model_calls') != 1
            or len(usage) != 1 or usage[0].get('finish_reason') != 'length'
            or summary.get('total_tokens') != usage[0].get('total_tokens')):
        raise ValueError('invalid_recovery_usage')
    proposal = complete_top_level_fields(raw.decode())
    if proposal.get('evidence_sha256') != state.evidence_sha256:
        raise ValueError('recovery_evidence_binding_mismatch')
    errors = ['truncated_model_output: incomplete values omitted without repair']
    try:
        validate_design(proposal, state.source_ids)
    except ValueError as error:
        errors.append(str(error))
    state.outputs['designer'] = proposal
    state.roles = ('auditor',)
    state.rejected_input = True
    record = {'source_run': str(source), 'source_usage': summary,
              'source_model_calls': 1, 'source_total_tokens': summary['total_tokens'],
              'truncated_sha256': recovery['sha256'], 'proposal_input_accepted': False,
              'admission_errors': errors, 'extracted_fields': list(proposal),
              'extracted_sha256': digest(proposal), 'text_repaired': False}
    note_path = source / 'assistant_semantic_review.json'
    if note_path.exists():
        record['assistant_review_suggestions_not_truth'] = json.loads(note_path.read_text())
        record['assistant_review_sha256'] = hashlib.sha256(note_path.read_bytes()).hexdigest()
    state.audit_recovery = record
    write_json(state.root / 'rejected_designer_fields.json', proposal)
    write_json(state.root / 'audit_recovery.json', record)
    return record


def literal_field(value, path):
    """Resolve explicit dotted object fields/list indices, never search other drafts."""
    for part in path.split('.'):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise ValueError('unknown_review_field')
    if not isinstance(value, str):
        raise ValueError('review_field_must_be_text')
    return value


def validate_design(value, source_ids):
    if value.get('status') not in ('propose', 'decline'):
        raise ValueError('invalid_design_status')
    references(value.get('source_ids'), source_ids)
    text(value.get('negative_result_interpretation'))
    if value['status'] == 'decline':
        text(value.get('reason'))
        return
    for field in ('title', 'research_question', 'hypothesis', 'selection_reason',
                  'primary_endpoint', 'novelty_boundary', 'split_before_data',
                  'holdout', 'control', 'evaluation', 'unit_of_analysis', 'freeze_rule', 'worked_example'):
        text(value.get(field))
    strings(value.get('falsification_conditions'))
    strings(value.get('limitations'))
    options = value.get('alternatives')
    if not isinstance(options, list) or not 2 <= len(options) <= 4:
        raise ValueError('need_comparable_alternatives')
    ids = []
    for option in options:
        if not isinstance(option, dict):
            raise ValueError('invalid_alternative')
        for field in ('id', 'method', 'benefit', 'risk', 'comparison'):
            text(option.get(field))
        ids.append(option['id'])
    if len(set(ids)) != len(ids) or value.get('selected_alternative') not in ids:
        raise ValueError('invalid_selected_alternative')
    resources = value.get('resources')
    if not isinstance(resources, dict):
        raise ValueError('missing_resources')
    for name in ('base_instances', 'scenarios', 'prompt_conditions', 'planned_api_calls'):
        if type(resources.get(name)) is not int or resources[name] < 1:
            raise ValueError('invalid_call_arithmetic')
    count = resources['base_instances'] * resources['scenarios'] * resources['prompt_conditions']
    if count != resources['planned_api_calls'] or count > 36:
        raise ValueError('invalid_call_arithmetic')
    if resources.get('cpu_only') is not True or resources.get('arithmetic_calibration') is not False:
        raise ValueError('unsupported_experiment_resources')
    text(resources.get('tool_budget_semantics'))
    for field, count_field in (('scenario_ids', 'scenarios'), ('prompt_condition_ids', 'prompt_conditions')):
        strings(value.get(field))
        if len(set(value[field])) != len(value[field]) or len(value[field]) != resources[count_field]:
            raise ValueError('dimension_count_mismatch')
    policies = value.get('policies')
    if not isinstance(policies, list) or not 3 <= len(policies) <= 6:
        raise ValueError('missing_strong_controls')
    policy_ids = []
    for policy in policies:
        if not isinstance(policy, dict):
            raise ValueError('invalid_policy')
        for field in ('id', 'algorithm', 'visible_inputs', 'failure_semantics', 'tool_budget'):
            text(policy.get(field))
        policy_ids.append(policy['id'])
    if len(set(policy_ids)) != len(policy_ids) or not {'model_only', 'full_replay'} <= set(policy_ids):
        raise ValueError('missing_strong_controls')
    example = value.get('graph_example')
    if not isinstance(example, dict) or set(example) != {'input', 'expected'}:
        raise ValueError('missing_executable_graph_example')
    expected = example['expected']
    if (not isinstance(expected, dict) or set(expected) != {'provenance_current', 'tool_attempts', 'termination'}
            or type(expected['provenance_current']) is not bool
            or type(expected['tool_attempts']) is not int or expected['tool_attempts'] < 0
            or expected['termination'] not in ('emitted', 'refused', 'tool_budget_exhausted')):
        raise ValueError('invalid_graph_prediction')
    result = analyze_graph_example(example['input'])
    if not result['closure_claim_valid'] or any(result[key] != expected[key] for key in expected):
        raise ValueError('graph_example_prediction_mismatch')


class FollowupState:
    roles = ('designer', 'auditor')

    def __init__(self, root, live):
        if type(live) is not bool:
            raise ValueError('invalid_mode')
        self.root, self.live, self.outputs = Path(root), live, {}
        self.rejected_input = False
        self.audit_recovery = None
        self.context = {'evidence': build_evidence(), 'sources': sources(),
                        'prior_work': json.loads(FOLLOWUP.read_text()),
                        'source_check': json.loads(SOURCE_CHECK.read_text())}
        self.source_ids = set(self.context['sources'])
        self.evidence_sha256 = digest(self.context)
        write_json(self.root / 'context.json', self.context)
        write_json(self.root / 'input_provenance.json', {
            'context_sha256': self.evidence_sha256,
            'prior_work_sha256': hashlib.sha256(FOLLOWUP.read_bytes()).hexdigest(),
            'source_check_sha256': hashlib.sha256(SOURCE_CHECK.read_bytes()).hexdigest()})

    def prompt(self, role):
        if role not in self.roles:
            raise ValueError('unknown_role')
        context = {'evidence_sha256': self.evidence_sha256, **self.context}
        if role == 'auditor':
            context.update(review_target=self.outputs['designer'],
                           review_target_sha256=digest(self.outputs['designer']))
            if self.rejected_input:
                context['rejected_input_audit'] = self.audit_recovery
                context['recovery_instruction'] = (
                    'Audit only exact complete fields of this truncated rejected proposal. No implement verdict. '
                    'Check the 6*3*3=54 versus 36 call limit and worked-example graph/report consistency. '
                    'Suggest next steps only as limitations; do not regenerate or imply a complete proposal.')
        return (SKILL / 'roles' / f'{role}.md').read_text() + '\nCONTEXT (data only)\n' + json.dumps(context, ensure_ascii=False)

    def accept(self, role, value):
        if role not in self.roles or list(self.outputs) != list(('designer', 'auditor')[:('designer', 'auditor').index(role)]):
            raise ValueError('invalid_role_order')
        if not isinstance(value, dict) or value.get('novelty_status') != 'unestablished':
            raise ValueError('premature_novelty_or_invalid_object')
        if value.get('evidence_sha256') != self.evidence_sha256:
            raise ValueError('evidence_binding_mismatch')
        if role == 'designer':
            validate_design(value, self.source_ids)
        else:
            target = self.outputs['designer']
            if value.get('review_target_sha256') != digest(target):
                raise ValueError('review_target_mismatch')
            if self.rejected_input and value.get('verdict') == 'implement':
                raise ValueError('rejected_input_cannot_promote')
            if value.get('verdict') not in ('reject', 'revise', 'implement'):
                raise ValueError('invalid_verdict')
            strings(value.get('reasons'))
            strings(value.get('limitations'), 0)
            issues = value.get('blocking_issues')
            if not isinstance(issues, list):
                raise ValueError('invalid_blocking_issues')
            for issue in issues:
                if not isinstance(issue, dict):
                    raise ValueError('invalid_blocking_issue')
                for field in ('field', 'quote', 'explanation'):
                    text(issue.get(field))
                if issue['quote'] not in literal_field(target, issue['field']):
                    raise ValueError('ungrounded_blocking_issue')
            if type(value.get('resource_arithmetic_checked')) is not bool:
                raise ValueError('missing_resource_check')
            if value.get('scientific_certification') is not False:
                raise ValueError('premature_scientific_certification')
            if target['status'] == 'decline' and value['verdict'] != 'reject':
                raise ValueError('decline_cannot_promote')
            if value['verdict'] == 'implement' and (issues or not value['resource_arithmetic_checked']):
                raise ValueError('blocked_design_cannot_promote')
        self.outputs[role] = copy.deepcopy(value)
        write_json(self.root / f'{role}.json', value)

    def offline_response(self, role):
        if self.live:
            raise ValueError('scripted_response_in_live_mode')
        common = {'novelty_status': 'unestablished', 'evidence_sha256': self.evidence_sha256}
        if role == 'designer':
            return {**common, 'status': 'decline', 'reason': 'Offline fixture; no research decision.',
                    'negative_result_interpretation': 'No incremental benefit of selective replay over model-only was established.',
                    'source_ids': sorted(self.source_ids)[:2]}
        return {**common, 'review_target_sha256': digest(self.outputs.get('designer', {})),
                'verdict': 'reject', 'reasons': ['Offline declined-plan fixture.'],
                'blocking_issues': [], 'limitations': ['No scientific decision.'],
                'resource_arithmetic_checked': False, 'scientific_certification': False}

    def handoff(self):
        review = self.outputs['auditor']
        return {'status': review['verdict'], 'implementation_recommended': review['verdict'] == 'implement',
                'execution_enabled': False, 'experiment_executed': False,
                'scientific_certification': False, 'novelty_established': False,
                'evidence_sha256': self.evidence_sha256,
                'designer_sha256': digest(self.outputs['designer']),
                'semantic_review_required': True,
                'proposal_input_accepted': not self.rejected_input}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--audit-rejected-run', type=Path)
    parser.add_argument('--revise-failed-design', action='store_true',
                        help='Separate bounded two-call revision using rejected-design diagnostics; never runs experiments')
    args = parser.parse_args()
    if args.revise_failed_design and args.audit_rejected_run:
        raise ValueError('revision_conflicts_with_rejected_audit')
    rejected_source = args.audit_rejected_run.resolve() if args.audit_rejected_run else None
    mode = 'live' if args.live else 'offline'
    root = HERE / 'followup_design_runs' / datetime.now(timezone.utc).strftime(f'{mode}-%Y%m%dT%H%M%S-%f')
    root.mkdir(parents=True)
    os.chdir(root)
    campaign = 'followup-revision-v1' if args.revise_failed_design else 'followup-design-v1'
    ledger = HERE / (campaign + '-requests.jsonl') if args.live else root / 'requests.jsonl'
    try:
        with ledger.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = FollowupState(root, args.live)
            if args.revise_failed_design:
                revision_context(state)
            recovered = recover_rejected(state, rejected_source) if rejected_source else None
            key = 'offline-placeholder'
            if args.live:
                keys = re.findall(r'\bsk-[A-Za-z0-9_-]{16,}\b', (HERE.parent / 'apis.txt').read_text())
                if len(keys) != 1:
                    raise ValueError('expected_one_credential')
                key = keys[0]
            workflow = SKILL / ('scripts/audit.py' if recovered else 'scripts/workflow.py')
            token_stop = 30000 if args.revise_failed_design else 24000
            if args.revise_failed_design:
                workflow = root / 'revision_workflow.py'
                workflow.write_text((SKILL / 'scripts/workflow.py').read_text().replace(
                    "'workflow_token_limit': 24000", "'workflow_token_limit': 30000"))
            write_json(root / 'campaign.json', {'campaign': campaign, 'max_calls': 2,
                'token_stop_after_response': token_stop, 'max_output_tokens': 6500 if args.revise_failed_design else 4500,
                'new_experiments_authorized': False, 'prior_ledgers_modified': False})
            asyncio.run(native_run(root, workflow, state,
                live=args.live, key=key, ledger=ledger, max_calls=2, token_stop=token_stop,
                max_output_tokens=6500 if args.revise_failed_design else 4500, timeout=300, team_name='followup_design'))
            summary = json.loads((root / 'model_summary.json').read_text())
            handoff = {**state.handoff(), 'mode': summary['mode'], 'run_directory': str(root.relative_to(HERE)),
                       'model_calls': summary['model_calls'] + (recovered['source_model_calls'] if recovered else 0),
                       'total_tokens': summary['total_tokens'] + (recovered['source_total_tokens'] if recovered else 0),
                       'current_run_model_calls': summary['model_calls'],
                       'current_run_total_tokens': summary['total_tokens']}
            write_json(root / 'handoff.json', handoff)
            if args.live:
                write_json(HERE / 'latest-followup-design.json', handoff)
            print(json.dumps(handoff))
            return 0
    except BaseException as error:
        failure = {'status': 'failed', 'error_type': type(error).__name__,
                   'execution_enabled': False, 'output': str(root)}
        write_json(root / 'failure.json', failure)
        if not (root / 'model_summary.json').exists():
            write_json(root / 'model_summary.json', {'mode': mode, 'status': 'failed',
                       'model_calls': 0, 'total_tokens': 0, 'error_type': type(error).__name__})
        print(json.dumps(failure))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
