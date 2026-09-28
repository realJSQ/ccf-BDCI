"""Construct paper inputs by replaying both strict and post-hoc saved evidence."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from analyze_replay import verify_saved, normalize_report_terminal, deterministic, read

HERE = Path(__file__).resolve().parent
DEFAULT_RUN = HERE / 'replay_runs/live-20260928T144804-532140'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def build_evidence(root=DEFAULT_RUN):
    root = Path(root)
    engine, scorer, episodes, strict = verify_saved(root)
    resource = read(root / 'model_summary.json')
    if resource['mode'] != 'live' or resource['status'] != 'completed':
        raise ValueError('real_completed_replay_required')
    posthoc, changed = [], 0
    for role, episode in episodes.items():
        original = read(root / f'{role}.json')
        normalized = normalize_report_terminal(original)
        changed += normalized != original
        for policy in engine.POLICIES:
            row = engine.replay(policy, episode['current'], episode['public'], normalized)
            row.update(episode_id=role, case_id=episode['case_id'], family=episode['family'], scenario=episode['scenario'])
            row['outcome'] = scorer.score(row['artifact'], episode['current'], row['status'])
            posthoc.append(row)
    saved = read(root / 'posthoc_report_terminal/results.json')
    if [deterministic(r) for r in posthoc] != [deterministic(r) for r in saved]:
        raise ValueError('posthoc_replay_mismatch')
    evidence = {'resource': {k: resource[k] for k in ('model_calls', 'total_tokens', 'duration_seconds')},
                'study_stage': 'development_only', 'writing_does_not_run_experiments': True}
    for label, rows in (('strict', strict), ('posthoc', posthoc)):
        summary = []
        for scenario in ('clean', 'update', 'incomplete_lineage'):
            for policy in engine.POLICIES:
                selected = [r for r in rows if (r['scenario'], r['policy']) == (scenario, policy)]
                counts = Counter(r['outcome'] for r in selected)
                summary.append({'scenario': scenario, 'policy': policy, 'episodes': len(selected),
                    **{k: counts[k] for k in ('correct_completion', 'wrong_completion', 'refusal')},
                    'tool_calls': sum(r['tool_calls'] for r in selected)})
        evidence[label] = {'summary_by_scenario_policy': summary, 'base_instance_count': 6,
            'completed_model_plans': 18, 'completed_policy_replays': 72}
    evidence['posthoc'].update(changed_plan_count=changed, model_calls=0)
    evidence['strict']['noncompletion_reasons'] = dict(Counter(r.get('reason') for r in strict
        if r['policy'] == 'A' and r['status'] != 'completed'))
    evidence['protocol'] = read(root / 'frozen_source/research/replay_protocol.json')
    evidence['limitations'] = [
        'Six self-authored base instances; scenarios and policies are repeated measures, not independent samples.',
        'One cached model recovery plan per episode, not four independent interactive agents.',
        'Missing terminal emit is malformed output, not voluntary model refusal or a wrong numerical answer.',
        'Post-hoc normalization adds only emit after an existing final rerun(report); no recovery nodes are invented.',
        'Post-hoc equality is not a preregistered success, held-out confirmation or statistical equivalence.',
        'Selective replay did not outperform the model plan alone; do not cherry-pick full replay as the sole baseline.',
        'No transient errors were injected, so retry B is expected to match A.',
        'Existing selective invalidation and version lineage are prior art; novelty is unestablished.']
    evidence['artifact_sha256'] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ('pre_registration.json', 'results.json', 'model_summary.json',
                     'posthoc_report_terminal/results.json', 'posthoc_report_terminal/summary.json')}
    return evidence


def sources():
    followup = read(HERE / 'prior_work/revision_followup.json')
    metadata = {
        'arxiv:2607.11098v1': ('AgentCheck: A Reproduce-Intervene-Mitigate Workbench for LLM Agents over MCP',
                             ['Aritra Mazumder', 'Nusrat jahan Lia'], 'v3 exists; this record cites the read v1'),
        'arxiv:2608.12761v1': ('Correct Is Not Governed: Provenance Integrity in Agentic Workflows',
                             ['Jesus Salas'], 'v1'),
        'arxiv:2604.16706v1': ('Evaluating Tool-Using Language Agents: Judge Reliability, Propagation Cascades, and Runtime Mitigation in AgentProp-Bench',
                             ['Bhaskar Gurram'], 'v2 has a different title; this record cites the read v1')}
    result = {}
    for row in followup['sources']:
        title, authors, version = metadata[row['id']]
        value = {'id': row['id'], 'title': title, 'authors': authors, 'year': 2026,
            'url': 'https://arxiv.org/abs/' + row['id'].split(':')[1], 'evidence_kind': 'retrieved',
            'metadata_checked_on': '2026-09-28', 'publication_status': 'arXiv preprint; no acceptance inferred',
            'version_note': version, 'reading_note': row['finding'], 'reading_scope': row['sections_read']}
        value['content_sha256'] = digest(value)
        result[row['id']] = value
    return result
