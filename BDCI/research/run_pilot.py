"""Critique-driven proposal revision and bounded real paired pilot; offline default."""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re

from native_runner import native_run
from pilot_benchmark import make_dataset, public_inputs, parse_answers, score_paired
from run_topics import write_json

HERE = Path(__file__).resolve().parent
BDCI = HERE.parent
SKILL = HERE / 'skills/pilot-study'
PREVIOUS = HERE / 'runs/live-20260928T081927-158480'
PRIOR_CHECK = HERE / 'prior_work/fulltext_check.json'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate_plan(plan, sources):
    if plan.get('status') == 'decline':
        if not isinstance(plan.get('reason'), str) or not plan['reason'].strip():
            raise ValueError('missing_decline_reason')
        return False
    if plan.get('status') != 'propose':
        raise ValueError('invalid_plan_status')
    for key in ['title','research_question','hypothesis','changes_from_previous',
                'baseline_policy','intervention_policy']:
        if not isinstance(plan.get(key), str) or not plan[key].strip():
            raise ValueError('missing_plan_text')
    for key in ['addresses_critique','limitations']:
        if (not isinstance(plan.get(key), list) or not plan[key]
                or any(not isinstance(x,str) or not x.strip() for x in plan[key])):
            raise ValueError('missing_plan_list')
    refs = plan.get('source_ids')
    if (not isinstance(refs,list) or any(not isinstance(x,str) for x in refs)
            or len(set(refs)) < 2 or any(ref not in sources for ref in refs)):
        raise ValueError('invalid_plan_references')
    for ref in refs:
        if sources[ref].get('evidence_kind') != 'retrieved' or not sources[ref].get('abstract'):
            raise ValueError('insufficient_plan_evidence')
    if (any(len(plan[k]) > 800 for k in ['baseline_policy','intervention_policy'])
            or plan['baseline_policy'].strip() == plan['intervention_policy'].strip()):
        raise ValueError('invalid_policy_comparison')
    if plan.get('primary_metric') not in ('accuracy_delta','wrong_peer_copy_reduction'):
        raise ValueError('unsupported_primary_metric')
    threshold = plan.get('min_improvement')
    if type(threshold) not in (int,float) or not math.isfinite(threshold) or not 0 < threshold <= 0.5:
        raise ValueError('invalid_effect_threshold')
    experiment = plan.get('experiment')
    if (not isinstance(experiment, dict) or type(experiment.get('n')) is not int
            or type(experiment.get('max_api_calls')) is not int
            or experiment.get('needs_gpu') is not False
            or experiment != {'family':'integer_arithmetic_v1','n':24,
                                   'max_api_calls':3,'needs_gpu':False}):
        raise ValueError('unsupported_experiment_contract')
    return True


def decide(metrics, plan, live):
    if metrics['status'] == 'insufficient_peer_errors':
        status = 'inconclusive_insufficient_peer_errors'
        observed = None
    else:
        if plan['primary_metric'] == 'accuracy_delta':
            observed = metrics['paired']['accuracy_delta']
        else:
            subset = metrics['wrong_peer_subset']
            observed = subset['baseline_propagated_error_rate'] - subset['intervention_propagated_error_rate']
        status = ('preliminary_positive_observation' if observed >= plan['min_improvement']
                  and metrics['paired']['accuracy_delta'] >= 0 else 'hypothesis_not_supported_in_pilot')
    return {'status':status if live else 'offline_only', 'scripted_status':None if live else status,
            'primary_metric':plan['primary_metric'], 'observed_effect':observed,
            'preregistered_threshold':plan['min_improvement'], 'pilot_executed':live,
            'real_observation':live, 'final_topic_selected':False, 'novelty_proven':False,
            'requires':['Full-text prior-work checking', 'Independent runs and task families',
                        'Power and uncertainty analysis before a scientific claim'],
            'interpretation':'One bounded exploratory pilot; no causal copying, significance or generalization claim.'}


def verify_saved_pilot(root):
    """Recompute measurements from saved responses, without any model calls."""
    prereg = json.loads((root/'pre_registration.json').read_text())
    plan = json.loads((root/'designer.json').read_text())
    if prereg['plan_sha256'] != digest(plan):
        raise ValueError('saved_plan_hash_mismatch')
    if prereg['generator_sha256'] != hashlib.sha256((HERE/'pilot_benchmark.py').read_bytes()).hexdigest():
        raise ValueError('saved_generator_hash_mismatch')
    dataset = make_dataset(seed=prereg['seed'], n=plan['experiment']['n'])
    inputs = json.loads((root/'dataset_inputs.json').read_text())
    oracle = json.loads((root/'oracle_private.json').read_text())
    if (inputs != public_inputs(dataset) or oracle != dataset['oracle']
            or digest(inputs) != prereg['inputs_sha256'] or digest(oracle) != prereg['oracle_sha256']):
        raise ValueError('saved_dataset_hash_mismatch')
    responses = [json.loads((root/f'{role}.json').read_text())['answers']
                 for role in ('peer','baseline','intervention')]
    expected = score_paired(dataset,*responses)
    expected['mode'] = prereg['mode']
    measured = json.loads((root/'metrics.json').read_text())
    if expected != measured:
        raise ValueError('saved_metrics_mismatch')
    return {'status':'passed','replayed_items':len(inputs),'model_calls':0,
            'metrics_sha256':hashlib.sha256((root/'metrics.json').read_bytes()).hexdigest(),
            'scope':'Recomputed scoring from archived responses, not an independent rerun of the model.'}


class PilotState:
    roles = ('designer','critic','peer','baseline','intervention','analyst')

    def __init__(self, root, live):
        if type(live) is not bool:
            raise ValueError('invalid_pilot_mode')
        self.root, self.live = root, live
        self.plan, self.review, self.metrics, self.interpretation = None,None,None,None
        self.dataset, self.answers, self.active_role = None,{},None
        self.previous = json.loads((PREVIOUS/'revision_queue.json').read_text())
        all_sources = json.loads((PREVIOUS/'sources.json').read_text())
        original = json.loads((PREVIOUS/'proposer.json').read_text())['candidates'][0]
        self.original = original
        self.sources = {ref:all_sources[ref] for ref in original['source_ids']}
        for source in self.sources.values():
            expected = source['content_sha256']
            if digest({k:v for k,v in source.items() if k != 'content_sha256'}) != expected:
                raise ValueError('source_snapshot_hash_mismatch')
        self.prior = json.loads(PRIOR_CHECK.read_text())
        write_json(root/'context_sources.json',self.sources)
        write_json(root/'previous_criticism.json',self.previous)
        write_json(root/'prior_work_check.json',self.prior)

    def prompt(self, role):
        file = 'solver' if role in ('peer','baseline','intervention') else role
        text = (SKILL/'roles'/f'{file}.md').read_text()
        if role in ('designer','critic'):
            text += '\nSOURCE_DATA_JSON\n'+json.dumps(self.sources,ensure_ascii=False)
            text += '\nPRIOR_WORK_ACCESS_DATA_JSON\n'+json.dumps(self.prior,ensure_ascii=False)
            if role == 'designer':
                text += '\nPREVIOUS_CRITICISM_JSON\n'+json.dumps(self.previous['items'][0],ensure_ascii=False)
                text += '\nPREVIOUS_PROPOSAL_JSON\n'+json.dumps(self.original,ensure_ascii=False)
            else:
                text += '\nREVISED_PLAN_JSON\n'+json.dumps(self.plan,ensure_ascii=False)
        elif role in ('peer','baseline','intervention'):
            if self.dataset is None:
                raise ValueError('experiment_not_preregistered')
            if role == 'peer':
                text += '\nSolve independently; no peer advice is provided.\n'
            else:
                text += '\nEXPERIMENT_POLICY\n'+self.plan[role+'_policy']
                text += '\nPEER_ANSWERS_JSON\n'+json.dumps(self.answers['peer'])
            text += '\nTASK_INPUTS_JSON\n'+json.dumps(public_inputs(self.dataset))
            text += ('\nFINAL RESPONSE CONTRACT: Return only a JSON object with key answers, '
                     'an array of {id, answer} objects. This format overrides any policy wording. '
                     'Every answer must be an integer; include each supplied ID exactly once.')
        else:
            text += '\nPLAN_JSON\n'+json.dumps(self.plan)
            compact = {k:v for k,v in self.metrics.items() if k != 'paired'}
            compact['paired'] = {k:v for k,v in self.metrics['paired'].items() if k != 'items'}
            text += '\nMEASURED_METRICS_JSON\n'+json.dumps(compact)
            text += '\nPROGRAM_DECISION_JSON\n'+json.dumps(decide(self.metrics,self.plan,self.live))
        return text

    def accept(self, role, data):
        write_json(self.root/f'{role}.json',data)
        if role == 'designer':
            validate_plan(data,self.sources)
            self.plan = data
        elif role == 'critic':
            if data.get('verdict') not in ('advance','revise','reject') or any(
                    not isinstance(data.get(k),str) or not data[k].strip()
                    for k in ['reason','control_check','scope_check','novelty_caution']):
                raise ValueError('invalid_pilot_review')
            self.review = data
            if data['verdict'] == 'advance':
                self.preregister()
        elif role in ('peer','baseline','intervention'):
            if set(data) != {'answers'}:
                raise ValueError('unexpected_answer_fields')
            self.answers[role] = parse_answers(data['answers'],self.dataset)
            if role == 'intervention':
                self.metrics = score_paired(self.dataset,self.answers['peer'],
                    self.answers['baseline'],self.answers['intervention'])
                self.metrics['mode'] = 'live' if self.live else 'offline_scripted'
                write_json(self.root/'metrics.json',self.metrics)
        else:
            if (not isinstance(data.get('summary'),str) or not isinstance(data.get('next_step'),str)
                    or not isinstance(data.get('limitations'),list)
                    or any(not isinstance(x,str) for x in data['limitations'])):
                raise ValueError('invalid_pilot_interpretation')
            self.interpretation = data

    def preregister(self):
        # Before any experimental response is requested or observed.
        self.dataset = make_dataset()
        write_json(self.root/'dataset_inputs.json',public_inputs(self.dataset))
        write_json(self.root/'oracle_private.json',self.dataset['oracle'])
        prereg = {'timestamp':datetime.now(timezone.utc).isoformat(), 'plan':self.plan,
                  'plan_sha256':digest(self.plan),'inputs_sha256':digest(public_inputs(self.dataset)),
                  'oracle_sha256':digest(self.dataset['oracle']),'seed':self.dataset['seed'],
                  'generator_sha256':hashlib.sha256((HERE/'pilot_benchmark.py').read_bytes()).hexdigest(),
                  'model':'deepseek-flash','temperature':0,'max_output_tokens':2200,
                  'experimental_calls':3,'min_peer_errors':5,
                  'comparison':'Same tasks and same natural peer answers, separate worker calls',
                  'decision_rule':'Enough peer errors, effect >= threshold AND accuracy_delta >= 0; still provisional',
                  'mode':'live' if self.live else 'offline_scripted'}
        write_json(self.root/'pre_registration.json',prereg)

    def finish(self):
        if self.metrics:
            decision = decide(self.metrics,self.plan,self.live)
            prereg = json.loads((self.root/'pre_registration.json').read_text())
            if (prereg['plan_sha256'] != digest(self.plan)
                    or prereg['inputs_sha256'] != digest(public_inputs(self.dataset))
                    or prereg['oracle_sha256'] != digest(self.dataset['oracle'])):
                raise ValueError('preregistration_mismatch')
            write_json(self.root/'scoring_replay.json',verify_saved_pilot(self.root))
        else:
            decision = {'status':'needs_revision','pilot_executed':False,'real_observation':False,
                        'final_topic_selected':False,'novelty_proven':False,
                        'reason':self.review or self.plan}
        write_json(self.root/'decision.json',decision)
        write_json(self.root/'next_iteration.json', {
            'status':'pending_design_revision' if self.metrics else 'pending_plan_revision',
            'automatic_retry':False, 'final_topic_selected':False,
            'observed_decision':decision['status'], 'agent_recommendation':self.interpretation,
            'requires':'New bounded campaign; retain this preregistration and its negative/inconclusive result.'})
        artifacts = [p for p in self.root.iterdir() if p.suffix in ('.json','.txt') and p.name != 'artifact_hashes.json']
        write_json(self.root/'artifact_hashes.json', {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts})
        lines = ['# Revised research pilot','', 'LIVE API' if self.live else 'OFFLINE SCRIPTED TEST','',
                 f"Program decision: **{decision['status']}**. Final topic selected: no. Novelty proven: no.", '',
                 '## Agent-proposed plan','', '```json',json.dumps(self.plan,indent=2,ensure_ascii=False),'```','',
                 '## Independent review','', '```json',json.dumps(self.review,indent=2,ensure_ascii=False),'```','']
        if self.metrics:
            lines += ['## Measured results','',f"Natural peer errors: {self.metrics['natural_peer_error_count']} / {self.metrics['n']}",
                      '', '| Condition | Exact accuracy |','| --- | --- |']
            lines += [f'| {name} | {value:.4f} |' for name,value in self.metrics['accuracy'].items()]
            lines += ['', 'Paired accuracy difference: '+str(self.metrics['paired']['accuracy_delta']), '',
                      'Observed agreement with a wrong peer is not proof of causal copying. One shared batch does not establish significance.',
                      '', '## Agent interpretation (subject to verification)','',
                      json.dumps(self.interpretation,ensure_ascii=False,indent=2)]
        lines += ['', 'Full-text access to the closest ACM work remains incomplete; novelty is unresolved.',
                  'This is a feasibility pilot on one arithmetic family with one model, not a competition paper.']
        (self.root/'report.md').write_text('\n'.join(lines)+'\n')
        return decision

    def offline_response(self, role):
        if self.live:
            raise ValueError('synthetic_response_forbidden_in_live_mode')
        if role == 'designer':
            return {'status':'propose','title':'SCRIPTED pipeline fixture','research_question':'Synthetic paired comparison?',
                    'hypothesis':'Synthetic fixture only','source_ids':list(self.sources),'changes_from_previous':'Schema test only',
                    'addresses_critique':['No real research claim'],'baseline_policy':'Solve normally and consider peer advice.',
                    'intervention_policy':'Compute independently before checking peer advice.','primary_metric':'accuracy_delta',
                    'min_improvement':0.05,'limitations':['Synthetic fixture, not a research proposal'],
                    'experiment':{'family':'integer_arithmetic_v1','n':24,'max_api_calls':3,'needs_gpu':False}}
        if role == 'critic':
            return {'verdict':'advance','reason':'Offline structure check only','control_check':'Synthetic',
                    'scope_check':'No real inference','novelty_caution':'No novelty claim'}
        if role in ('peer','baseline','intervention'):
            values = [dict(row) for row in self.dataset['oracle']]
            # Only offline fixtures manufacture errors, never the live executor.
            if role != 'intervention':
                for row in values[:8]:row['answer'] += 1
            return {'answers':values}
        return {'summary':'Synthetic model responses, not research evidence.',
                'limitations':['Offline only'],'next_step':'Run a separately budgeted real pilot.'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true',help='Spend fixed pilot-v1 budget (<=6 requests)')
    args=parser.parse_args()
    mode='live' if args.live else 'offline'
    root=HERE/'pilot_runs'/datetime.now(timezone.utc).strftime(f'{mode}-%Y%m%dT%H%M%S-%f')
    root.mkdir(parents=True);os.chdir(root)
    os.environ.setdefault('JIUWENSWARM_HOME',str(root/'runtime'))
    os.environ.setdefault('JIUWENSWARM_DATA_DIR',str(root/'runtime/.jiuwenswarm'))
    ledger=HERE/'pilot-v1-requests.jsonl' if args.live else root/'requests.jsonl'
    lock=ledger.with_suffix('.lock').open('a')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        key='offline-placeholder'
        if args.live:
            keys=re.findall(r'\bsk-[A-Za-z0-9_-]{16,}\b',(BDCI/'apis.txt').read_text())
            if len(keys)!=1:raise ValueError('expected_one_credential')
            key=keys[0]
        state=PilotState(root,args.live)
        asyncio.run(native_run(root,SKILL/'scripts/workflow.py',state,live=args.live,key=key,ledger=ledger))
        decision=state.finish()
        summary=json.loads((root/'model_summary.json').read_text())
        summary.update(pilot_status=decision['status'],pilot_executed=decision['pilot_executed'],final_topic_selected=False)
        write_json(root/'summary.json',summary)
        print(json.dumps({'status':'completed','pilot_status':decision['status'],'output':str(root)}))
        return 0
    except BaseException as error:
        write_json(root/'failure.json',{'status':'failed','error_type':type(error).__name__})
        print(json.dumps({'status':'failed','error_type':type(error).__name__,'output':str(root)}))
        return 1
    finally:
        lock.close()


if __name__=='__main__':
    raise SystemExit(main())
