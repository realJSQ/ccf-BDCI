"""Check an illustrative plan against existing CPU tools; not a scientific study."""
import argparse
import json
from pathlib import Path

from replay_cases import make_cases, make_scenario
from replay_engine import NODES, POLICIES, closure, initial_receipts, public_episode, replay
from replay_reference import score

MAX_EXPERIMENT_CALLS = 36


def check_example(spec):
    required = {'case_id', 'scenario', 'plan', 'claimed_changed_sources',
                'claimed_closure', 'predictions', 'resources'}
    if not isinstance(spec, dict) or set(spec) != required:
        raise ValueError('invalid_example_fields')
    cases = {case['case_id']: case for case in make_cases()}
    if spec['case_id'] not in cases:
        raise ValueError('unsupported_case_use_new_adapter_for_new_task_structures')
    base = cases[spec['case_id']]
    current = make_scenario(base, spec['scenario'])
    public = public_episode(base, current, spec['scenario'], initial_receipts(base))
    for key in ('claimed_changed_sources', 'claimed_closure'):
        value = spec[key]
        if (not isinstance(value, list) or not all(isinstance(n, str) for n in value)
                or len(value) != len(set(value)) or not set(value) <= set(NODES)):
            raise ValueError('invalid_node_claim')
    resources = spec['resources']
    fields = ('base_instances', 'scenarios', 'prompt_conditions', 'planned_api_calls')
    if (not isinstance(resources, dict) or set(resources) != set(fields)
            or any(type(resources[k]) is not int or not 1 <= resources[k] <= 1000 for k in fields)):
        raise ValueError('invalid_resource_plan')
    product = resources['base_instances'] * resources['scenarios'] * resources['prompt_conditions']
    predictions = spec['predictions']
    if not isinstance(predictions, dict) or set(predictions) != set(POLICIES):
        raise ValueError('incomplete_policy_predictions')
    issues = []
    if product != resources['planned_api_calls'] or product > MAX_EXPERIMENT_CALLS:
        issues.append({'code': 'experiment_request_budget', 'computed_calls': product,
                       'claimed_calls': resources['planned_api_calls'], 'maximum': MAX_EXPERIMENT_CALLS})
    changed = public['changed_source_nodes']
    expected_closure = closure(public['declared_dependencies'], changed)
    for key, expected in (('claimed_changed_sources', changed), ('claimed_closure', expected_closure)):
        if set(spec[key]) != set(expected):
            issues.append({'code': key + '_mismatch', 'expected': expected, 'claimed': spec[key]})
    results = {}
    for policy in POLICIES:
        prediction = predictions[policy]
        if (not isinstance(prediction, dict) or set(prediction) != {'outcome', 'tool_calls'}
                or prediction['outcome'] not in ('correct_completion', 'wrong_completion', 'refusal')
                or type(prediction['tool_calls']) is not int or prediction['tool_calls'] < 0):
            raise ValueError('invalid_prediction')
        result = replay(policy, current, public, spec['plan'])
        measured = {'outcome': score(result['artifact'], current, result['status']),
                    'tool_calls': result['tool_calls']}
        results[policy] = {**measured, 'status': result['status'], 'reason': result.get('reason'),
                           'executed_nodes': [row['node'] for row in result['trace']]}
        if measured != prediction:
            issues.append({'code': 'policy_prediction_mismatch', 'policy': policy,
                           'expected': measured, 'claimed': prediction})
    return {'claims_consistent': not issues, 'issues': issues, 'policy_checks': results,
            'declared_closure': expected_closure, 'changed_sources': changed,
            'new_model_calls': 0, 'scientific_certification': False,
            'experiment_execution_enabled': False,
            'scope': 'Illustrative check on the existing six-node CPU adapter; no new model observation or independent validation.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('example', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = check_example(json.loads(args.example.read_text()))
    encoded = json.dumps(report, indent=2) + '\n'
    if args.output:
        with args.output.open('x') as output:
            output.write(encoded)
    print(encoded)
    raise SystemExit(0 if report['claims_consistent'] else 1)
