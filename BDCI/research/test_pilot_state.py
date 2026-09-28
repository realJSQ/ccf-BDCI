"""Offline plan gates and experimental isolation; no framework or API calls."""
import asyncio
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from run_pilot import PilotState, validate_plan, decide, verify_saved_pilot
from native_runner import native_run
from pilot_benchmark import parse_answers, score_paired, public_inputs


class PilotStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = PilotState(Path(self.tmp.name), False)
        self.plan = self.state.offline_response('designer')

    def ready(self):
        self.state.accept('designer', self.plan)
        self.state.accept('critic', self.state.offline_response('critic'))
        return parse_answers(self.state.dataset['oracle'], self.state.dataset)

    def test_valid_plan_and_decline(self):
        self.assertTrue(validate_plan(self.plan, self.state.sources))
        self.assertFalse(validate_plan({'status': 'decline', 'reason': 'Inadequate evidence'}, self.state.sources))
        with self.assertRaises(ValueError):
            validate_plan({'status': 'decline', 'reason': ''}, self.state.sources)

    def test_invalid_plan_references(self):
        for refs in ([], ['unknown', next(iter(self.state.sources))], [1, 2]):
            plan = copy.deepcopy(self.plan)
            plan['source_ids'] = refs
            with self.subTest(refs=refs), self.assertRaises(ValueError):
                validate_plan(plan, self.state.sources)

    def test_synthetic_or_missing_abstract_sources_cannot_pass(self):
        for patch in ({'evidence_kind': 'synthetic'}, {'abstract': None}):
            sources = copy.deepcopy(self.state.sources)
            sources[next(iter(sources))].update(patch)
            with self.assertRaises(ValueError):
                validate_plan(self.plan, sources)

    def test_unsupported_experiment(self):
        for patch in ({'family': 'unbounded_generated_code'}, {'n': 25},
                      {'max_api_calls': 4}, {'needs_gpu': True}):
            plan = copy.deepcopy(self.plan)
            plan['experiment'].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate_plan(plan, self.state.sources)

    def test_experiment_requires_exact_types(self):
        for patch in ({'n': 24.0}, {'max_api_calls': 3.0}, {'needs_gpu': 0},
                      {'needs_gpu': None}, {'max_api_calls': True}):
            plan = copy.deepcopy(self.plan)
            plan['experiment'].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate_plan(plan, self.state.sources)

    def test_nonboolean_state_mode_rejected(self):
        for live in ('false', 0, 1, None):
            with self.subTest(live=live), self.assertRaisesRegex(ValueError, 'invalid_pilot_mode'):
                PilotState(self.state.root, live)

    def test_mode_mismatch_rejected_before_framework_or_model(self):
        for live in (True, 0, 'false'):
            with self.subTest(live=live), self.assertRaisesRegex(ValueError, 'research_mode_mismatch'):
                asyncio.run(native_run(self.state.root, self.state.root / 'unused.py', self.state,
                    live=live, key='unused-placeholder', ledger=self.state.root / 'unused.jsonl'))
        self.assertFalse((self.state.root / 'unused.jsonl').exists())

    def test_live_state_forbids_offline_oracle_fixture(self):
        live_state = PilotState(self.state.root, True)
        for role in ('designer', 'peer', 'baseline', 'intervention'):
            with self.subTest(role=role), self.assertRaises(ValueError):
                live_state.offline_response(role)

    def test_same_policies_rejected(self):
        self.plan['intervention_policy'] = ' ' + self.plan['baseline_policy'] + ' '
        with self.assertRaisesRegex(ValueError, 'invalid_policy_comparison'):
            validate_plan(self.plan, self.state.sources)

    def test_boolean_nonfinite_or_invalid_threshold_rejected(self):
        for value in (True, False, float('nan'), float('inf'), -0.1, 0, 0.51):
            self.plan['min_improvement'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_plan(self.plan, self.state.sources)

    def test_no_experiment_before_review_or_after_rejection(self):
        self.state.accept('designer', self.plan)
        with self.assertRaisesRegex(ValueError, 'experiment_not_preregistered'):
            self.state.prompt('peer')
        review = self.state.offline_response('critic')
        review['verdict'] = 'reject'
        self.state.accept('critic', review)
        self.assertIsNone(self.state.dataset)
        decision = self.state.finish()
        self.assertEqual(decision['status'], 'needs_revision')
        self.assertFalse(decision['pilot_executed'])

    def test_preregistration_precedes_results_and_records_hashes(self):
        self.ready()
        prereg = json.loads((self.state.root / 'pre_registration.json').read_text())
        self.assertEqual(self.state.answers, {})
        self.assertIsNone(self.state.metrics)
        self.assertEqual(prereg['experimental_calls'], 3)
        self.assertEqual(prereg['min_peer_errors'], 5)
        self.assertTrue(prereg['plan_sha256'])
        self.assertTrue(prereg['inputs_sha256'])
        self.assertTrue(prereg['oracle_sha256'])

    def test_saved_scoring_replay_and_tamper_rejection(self):
        self.ready()
        for role in ('peer','baseline','intervention','analyst'):
            self.state.accept(role,self.state.offline_response(role))
        self.assertEqual(verify_saved_pilot(self.state.root)['status'],'passed')
        for filename in ('oracle_private.json','metrics.json','designer.json'):
            path = self.state.root / filename
            original = path.read_text()
            data = json.loads(original)
            if filename == 'oracle_private.json':
                data[0]['answer'] += 1
            elif filename == 'metrics.json':
                data['accuracy']['baseline'] = 0.999
            else:
                data['min_improvement'] = 0.4
            path.write_text(json.dumps(data))
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                verify_saved_pilot(self.state.root)
            path.write_text(original)

    def test_solver_prompts_exclude_oracle_and_share_tasks_and_peer(self):
        self.ready()
        sentinel = -99999999999999999999999999999999
        self.state.dataset['oracle'][0]['answer'] = sentinel
        self.state.answers['peer'] = {row['id']: index for index, row in enumerate(public_inputs(self.state.dataset))}
        prompts = {role: self.state.prompt(role) for role in ('peer', 'baseline', 'intervention')}
        for prompt in prompts.values():
            self.assertNotIn(str(sentinel), prompt)
            self.assertNotIn('oracle', prompt.lower())
        tasks = [prompt.split('\nTASK_INPUTS_JSON\n')[1] for prompt in prompts.values()]
        self.assertEqual(tasks[0], tasks[1])
        self.assertEqual(tasks[1], tasks[2])
        baseline_peer = prompts['baseline'].split('\nPEER_ANSWERS_JSON\n')[1].split('\nTASK_INPUTS_JSON\n')[0]
        intervention_peer = prompts['intervention'].split('\nPEER_ANSWERS_JSON\n')[1].split('\nTASK_INPUTS_JSON\n')[0]
        self.assertEqual(baseline_peer, intervention_peer)
        self.assertNotIn('PEER_ANSWERS_JSON', prompts['peer'])

    def test_insufficient_peer_errors_cannot_be_positive(self):
        truth = self.ready()
        baseline = {key: value + 1 for key, value in truth.items()}
        metrics = score_paired(self.state.dataset, truth, baseline, truth)
        decision = decide(metrics, self.plan, True)
        self.assertEqual(decision['status'], 'inconclusive_insufficient_peer_errors')
        self.assertIsNone(decision['observed_effect'])

    def test_negative_accuracy_not_supported(self):
        truth = self.ready()
        wrong = {key: value + 1 for key, value in truth.items()}
        metrics = score_paired(self.state.dataset, wrong, truth, wrong)
        decision = decide(metrics, self.plan, True)
        self.assertLess(decision['observed_effect'], 0)
        self.assertEqual(decision['status'], 'hypothesis_not_supported_in_pilot')

    def test_less_wrong_peer_agreement_cannot_trade_away_accuracy(self):
        truth = self.ready()
        keys = list(truth)
        peer, intervention = truth.copy(), truth.copy()
        for key in keys[:5]:
            peer[key] += 1
        for key in keys[5:11]:
            intervention[key] += 2
        metrics = score_paired(self.state.dataset, peer, peer, intervention)
        self.plan['primary_metric'] = 'wrong_peer_copy_reduction'
        decision = decide(metrics, self.plan, True)
        self.assertEqual(decision['observed_effect'], 1)
        self.assertLess(metrics['paired']['accuracy_delta'], 0)
        self.assertEqual(decision['status'], 'hypothesis_not_supported_in_pilot')

    def test_offline_positive_fixture_remains_nonreal(self):
        self.ready()
        for role in ('peer', 'baseline', 'intervention'):
            self.state.accept(role, self.state.offline_response(role))
        result = self.state.finish()
        self.assertEqual(result['status'], 'offline_only')
        self.assertEqual(result['scripted_status'], 'preliminary_positive_observation')
        self.assertFalse(result['real_observation'])
        self.assertFalse(result['pilot_executed'])
        self.assertFalse(result['final_topic_selected'])
        self.assertFalse(result['novelty_proven'])


if __name__ == '__main__':
    unittest.main()
