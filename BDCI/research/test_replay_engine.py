import copy
import unittest
from unittest.mock import patch

from replay_cases import make_cases, make_scenario
from replay_engine import (NODES, ToolRuntime, TransientToolError, closure, declared_dependencies,
                           initial_receipts, public_episode, replay)
from replay_reference import reference, score


class ReplayEngineTests(unittest.TestCase):
    def episode(self, base, scenario):
        current = make_scenario(base, scenario)
        public = public_episode(base, current, scenario, initial_receipts(base))
        return current, public

    def test_tools_match_independent_reference_for_every_family_and_update(self):
        for base in make_cases():
            for scenario in ('clean', 'update', 'incomplete_lineage'):
                current, public = self.episode(base, scenario)
                plan = {'actions': [{'op': 'rerun', 'node': n} for n in NODES] + [{'op': 'emit'}]}
                for policy in 'ABCD':
                    result = replay(policy, current, public, plan)
                    self.assertEqual(result['artifact'], reference(current))
                    self.assertEqual(score(result['artifact'], current, result['status']), 'correct_completion')

    def test_missing_edge_has_actual_effect_but_model_can_repair_it(self):
        base = make_cases()[0]
        current, public = self.episode(base, 'incomplete_lineage')
        plan = {'actions': [{'op': 'emit'}]}
        full = replay('C', current, public, plan)
        selective = replay('D', current, public, plan)
        self.assertEqual(full['tool_calls'], 6)
        self.assertEqual(selective['tool_calls'], 2)
        self.assertEqual(score(full['artifact'], current), 'correct_completion')
        self.assertEqual(score(selective['artifact'], current), 'wrong_completion')
        plan['actions'] = [{'op': 'rerun', 'node': n} for n in ('combine', 'report')] + [{'op': 'emit'}]
        recovered = replay('D', current, public, plan)
        self.assertEqual(score(recovered['artifact'], current), 'correct_completion')
        self.assertEqual(recovered['tool_calls'], 4)

    def test_legitimate_update_and_clean_control(self):
        for base in make_cases():
            for scenario, work in (('clean', 0), ('update', 4)):
                current, public = self.episode(base, scenario)
                result = replay('D', current, public, {'actions': [{'op': 'emit'}]})
                self.assertEqual(score(result['artifact'], current), 'correct_completion')
                self.assertEqual(result['tool_calls'], work)

    def test_declared_graph_does_not_implicitly_use_actual_graph(self):
        self.assertEqual(closure(declared_dependencies('incomplete_lineage'), ['read_aux']),
                         ['read_aux', 'summarize_aux'])
        self.assertEqual(closure(declared_dependencies('update'), ['read_aux']),
                         ['read_aux', 'summarize_aux', 'combine', 'report'])

    def test_refusal_budget_and_invalid_plan_cannot_count_as_completion(self):
        current, public = self.episode(make_cases()[0], 'update')
        for policy in 'ABCD':
            refused = replay(policy, current, public, {'actions': [{'op': 'refuse'}]})
            self.assertEqual(score(refused['artifact'], current, refused['status']), 'refusal')
            invalid = replay(policy, current, public, {'actions': [{'op': 'shell', 'node': 'rm'}]})
            self.assertEqual(invalid['status'], 'refused')
            exhausted = replay(policy, current, public,
                               {'actions': [{'op': 'rerun', 'node': 'read_aux'}, {'op': 'emit'}]}, tool_budget=0)
            self.assertEqual(exhausted['reason'], 'tool_budget_exhausted')

    def test_private_label_perturbation_cannot_change_policy_behavior(self):
        current, public = self.episode(make_cases()[0], 'update')
        changed = copy.deepcopy(current)
        changed['unused_private_oracle_label'] = 'wrong'
        for policy in 'ABCD':
            a = replay(policy, current, public, {'actions': [{'op': 'emit'}]})
            b = replay(policy, changed, public, {'actions': [{'op': 'emit'}]})
            for value in (a, b):
                value.pop('duration_seconds')
            self.assertEqual(a, b)
        self.assertNotIn('unused_private_oracle_label', public)
        self.assertNotIn('scenario', public)

    def test_transient_retry_has_matched_allowance(self):
        current, public = self.episode(make_cases()[0], 'clean')
        actual = ToolRuntime.execute
        for policy, expected in (('A', 'refused'), ('B', 'completed'), ('C', 'completed'), ('D', 'completed')):
            calls = []
            def fail_once(runtime, node):
                calls.append(node)
                if len(calls) == 1:
                    raise TransientToolError('test-only')
                return actual(runtime, node)
            with patch.object(ToolRuntime, 'execute', fail_once):
                result = replay(policy, current, public,
                    {'actions': [{'op': 'rerun', 'node': 'read_aux'}, {'op': 'emit'}]})
            self.assertEqual(result['status'], expected)
            self.assertEqual(result['tool_calls'], 1 if policy == 'A' else 2)


if __name__ == '__main__':
    unittest.main()
