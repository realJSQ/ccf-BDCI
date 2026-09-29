"""Regression boundaries for follow-up design, no model or network calls."""
from pathlib import Path
import tempfile
import json
import hashlib
import shutil
import unittest

from run_followup_design import FollowupState, validate_design, complete_top_level_fields, recover_rejected


def proposal(state):
    value = state.offline_response('designer')
    value.update(status='propose', selected_alternative='change',
        alternatives=[dict(id=i, method='M', benefit='B', risk='R', comparison='C') for i in ('change', 'control')],
        resources=dict(base_instances=6, scenarios=3, prompt_conditions=2,
            planned_api_calls=36, cpu_only=True, arithmetic_calibration=False,
            tool_budget_semantics='Count every attempt.'),
        scenario_ids=['clean', 'update', 'lineage'], prompt_condition_ids=['original', 'new'],
        falsification_conditions=['No benefit over model-only.'], limitations=['Development only.'],
        policies=[dict(id=i, algorithm='Frozen plan.', visible_inputs='Shared observation.',
            failure_semantics='Retain failures.', tool_budget='12 attempts.')
            for i in ('model_only', 'full_replay', 'intervention')])
    for field in ('title', 'research_question', 'hypothesis', 'selection_reason',
                  'primary_endpoint', 'novelty_boundary', 'split_before_data',
                  'holdout', 'control', 'evaluation', 'unit_of_analysis', 'freeze_rule', 'worked_example'):
        value[field] = 'Fixture text; not a scientific proposal.'
    value['graph_example'] = json.loads((Path(__file__).parent / 'protocol_examples/graph-cache.json').read_text())
    return value


class FollowupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.state = FollowupState(Path(temp.name), False)

    def recovery_fixture(self):
        source = self.state.root / 'source'
        source.mkdir()
        for name in ('context.json', 'input_provenance.json'):
            shutil.copyfile(self.state.root / name, source / name)
        value = proposal(self.state)
        raw = (json.dumps(value)[:-1] + ', "unfinished": ["partial').encode()
        (source / 'truncated_designer.txt').write_bytes(raw)
        (source / 'truncation_recovery.json').write_text(json.dumps(dict(
            finish_reason='length', accepted_as_designer=False, new_model_calls=0,
            sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))))
        (source / 'model_summary.json').write_text(json.dumps(dict(mode='offline_scripted',
            status='failed', model_calls=1, total_tokens=10,
            model_usage=[dict(finish_reason='length', total_tokens=10)])))
        (source / 'model_usage.jsonl').write_text(json.dumps(dict(finish_reason='length', total_tokens=10)) + '\n')
        return source, value

    def test_extract_complete_fields_without_inventing_tail(self):
        self.assertEqual(complete_top_level_fields('```json\n{"a":"x\\ny", "b":[1,2], "c":[3,'),
                         {'a': 'x\ny', 'b': [1, 2]})
        self.assertEqual(complete_top_level_fields('{"a":1,"b":2e'), {'a': 1})

    def test_rejected_recovery_cannot_implement(self):
        source, value = self.recovery_fixture()
        record = recover_rejected(self.state, source)
        self.assertEqual(self.state.outputs['designer'], value)
        self.assertFalse(record['proposal_input_accepted'])
        review = self.state.offline_response('auditor')
        review.update(verdict='implement', resource_arithmetic_checked=True)
        with self.assertRaisesRegex(ValueError, 'rejected_input_cannot_promote'):
            self.state.accept('auditor', review)
        review['verdict'] = 'reject'
        self.state.accept('auditor', review)
        self.assertFalse(self.state.handoff()['proposal_input_accepted'])

    def test_recovery_refuses_changed_raw_and_context(self):
        source, _ = self.recovery_fixture()
        raw_path = source / 'truncated_designer.txt'
        original = raw_path.read_bytes()
        raw_path.write_bytes(original + b' ')
        with self.assertRaisesRegex(ValueError, 'truncation_provenance'):
            recover_rejected(self.state, source)
        raw_path.write_bytes(original)
        context_path = source / 'context.json'
        context = json.loads(context_path.read_text())
        context['changed'] = True
        context_path.write_text(json.dumps(context))
        with self.assertRaisesRegex(ValueError, 'context_mismatch'):
            recover_rejected(self.state, source)

    def test_decline_review_and_handoff_disable_execution(self):
        self.state.accept('designer', self.state.offline_response('designer'))
        self.state.accept('auditor', self.state.offline_response('auditor'))
        self.assertFalse(self.state.handoff()['execution_enabled'])
        self.assertFalse(self.state.handoff()['implementation_recommended'])

    def test_cannot_promote_decline(self):
        self.state.accept('designer', self.state.offline_response('designer'))
        review = self.state.offline_response('auditor')
        review.update(verdict='implement', resource_arithmetic_checked=True)
        with self.assertRaisesRegex(ValueError, 'decline_cannot_promote'):
            self.state.accept('auditor', review)

    def test_graph_claims_checked_even_when_the_prose_is_plausible(self):
        value = proposal(self.state)
        validate_design(value, self.state.source_ids)
        value['graph_example']['expected']['provenance_current'] = True
        with self.assertRaisesRegex(ValueError, 'graph_example_prediction_mismatch'):
            validate_design(value, self.state.source_ids)
        value['graph_example']['expected']['provenance_current'] = False
        value['graph_example']['input']['claimed_closure'].remove('report')
        with self.assertRaisesRegex(ValueError, 'graph_example_prediction_mismatch'):
            validate_design(value, self.state.source_ids)
        del value['graph_example']
        with self.assertRaisesRegex(ValueError, 'missing_executable_graph_example'):
            validate_design(value, self.state.source_ids)

    def test_call_product_cap_and_real_int(self):
        for changes in ({'planned_api_calls': 35}, {'base_instances': 7, 'planned_api_calls': 42},
                        {'base_instances': True}):
            value = proposal(self.state)
            value['resources'].update(changes)
            with self.assertRaisesRegex(ValueError, 'call_arithmetic'):
                validate_design(value, self.state.source_ids)

    def test_strong_controls_and_dimensions_required(self):
        value = proposal(self.state)
        value['policies'][0]['id'] = 'weak_control'
        with self.assertRaisesRegex(ValueError, 'strong_controls'):
            validate_design(value, self.state.source_ids)
        value = proposal(self.state)
        value['prompt_condition_ids'] = ['one']
        with self.assertRaisesRegex(ValueError, 'dimension_count'):
            validate_design(value, self.state.source_ids)

    def test_bindings_and_literal_blockers(self):
        self.state.accept('designer', proposal(self.state))
        for key in ('evidence_sha256', 'review_target_sha256'):
            review = self.state.offline_response('auditor')
            review[key] = '0' * 64
            with self.assertRaises(ValueError):
                self.state.accept('auditor', review)
        review = self.state.offline_response('auditor')
        review['blocking_issues'] = [dict(field='policies.0.algorithm', quote='invented', explanation='Bad')]
        with self.assertRaisesRegex(ValueError, 'ungrounded'):
            self.state.accept('auditor', review)
        review['blocking_issues'][0]['quote'] = 'Frozen plan.'
        review.update(verdict='implement', resource_arithmetic_checked=True)
        with self.assertRaisesRegex(ValueError, 'blocked_design'):
            self.state.accept('auditor', review)
        review['verdict'] = 'revise'
        self.state.accept('auditor', review)

    def test_implementation_advice_is_not_execution(self):
        self.state.accept('designer', proposal(self.state))
        review = self.state.offline_response('auditor')
        review.update(verdict='implement', resource_arithmetic_checked=True)
        self.state.accept('auditor', review)
        self.assertTrue(self.state.handoff()['implementation_recommended'])
        self.assertFalse(self.state.handoff()['execution_enabled'])
        self.assertFalse(self.state.handoff()['scientific_certification'])

    def test_role_order_and_no_live_fixture(self):
        with self.assertRaisesRegex(ValueError, 'role_order'):
            self.state.accept('auditor', {})
        self.state.live = True
        with self.assertRaisesRegex(ValueError, 'scripted_response'):
            self.state.offline_response('designer')


if __name__ == '__main__':
    unittest.main()
