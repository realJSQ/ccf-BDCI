from copy import deepcopy
import unittest

from recovery_v2_engine import (POLICIES, Runtime, forward_closure, initial_receipts,
                                public_episode, replay, workflow)
from replay_cases import make_cases, make_scenario
from replay_reference import reference, score


def case_for(family='tabular', topology=(1, 1)):
    case = next(c for c in make_cases() if c['family'] == family)
    case['topology'] = dict(zip(('main_shards', 'aux_shards'), topology))
    return case


def plan(*nodes):
    return {'actions': [{'op': 'rerun', 'node': n} for n in nodes] + [{'op': 'emit'}]}


class RecoveryV2Tests(unittest.TestCase):
    def test_dev_topologies_preserve_domain_semantics(self):
        for family in ('tabular', 'retrieval', 'classification'):
            for topology in ((1, 1), (2, 1), (1, 2)):
                with self.subTest(family=family, topology=topology):
                    base = case_for(family, topology)
                    self.assertEqual(initial_receipts(base)['report']['value'], reference(base))
                    current = make_scenario(base, 'update')
                    public = public_episode(base, current, 'aux_update')
                    for policy in ('E', 'F', 'G'):
                        result = replay(policy, current, public, plan())
                        self.assertEqual(score(result['artifact'], current, result['status']), 'correct_completion')
                        self.assertTrue(result['provenance_current'])

    def test_parent_only_counterexample_is_repaired(self):
        base = case_for()
        current = make_scenario(base, 'update')
        public = public_episode(base, current, 'incomplete_lineage')
        results = {p: replay(p, current, public, plan('read_aux', 'summarize_aux')) for p in POLICIES}
        for p in ('A', 'D'):
            self.assertFalse(results[p]['provenance_current'])
            self.assertEqual(results[p]['tool_calls'], 2)
            self.assertNotEqual(results[p]['artifact'], reference(current))
        for p in ('E', 'G'):
            self.assertTrue(results[p]['provenance_current'])
            self.assertEqual(results[p]['tool_calls'], 4)
            self.assertEqual(results[p]['artifact'], reference(current))
        self.assertEqual(results['F']['tool_calls'], 6)
        self.assertEqual(len({r['public_input_sha256'] for r in results.values()}), 1)

    def test_g_does_not_inherit_model_failure(self):
        base = case_for()
        current = make_scenario(base, 'update')
        public = public_episode(base, current, 'aux_update')
        for bad in (None, {}, {'actions': [{'op': 'rerun', 'node': 'read_aux'}]},
                    {'actions': [{'op': 'refuse'}]}, {'actions': [{'op': 'rerun', 'node': []}, {'op': 'emit'}]}):
            for p in ('A', 'D', 'E', 'F'):
                result = replay(p, current, public, bad)
                self.assertEqual(result['status'], 'refused')
                self.assertEqual(result['tool_calls'], 0)
            deterministic = replay('G', current, public, bad)
            self.assertEqual(deterministic['artifact'], reference(current))
            self.assertIsNone(deterministic['plan_sha256'])

    def test_e_preserves_requested_extra_work_and_cannot_outperform_g_on_calls(self):
        base = case_for(topology=(2, 1))
        current = make_scenario(base, 'update')
        public = public_episode(base, current, 'aux_update')
        requested = plan('read_main', 'read_main')
        protected = replay('E', current, public, requested)
        baseline = replay('G', current, public)
        self.assertEqual(protected['tool_calls'], baseline['tool_calls'] + 1)
        self.assertEqual(protected['artifact'], baseline['artifact'])
        raw = replay('A', current, public, requested)
        self.assertEqual([t['node'] for t in raw['trace']], ['read_main', 'read_main'])

    def test_clean_noop_and_joint_source_closure(self):
        base = case_for(topology=(1, 2))
        public = public_episode(base, base, 'clean')
        for p in POLICIES:
            result = replay(p, base, public, plan())
            self.assertEqual(result['tool_calls'], 0)
            self.assertTrue(result['provenance_current'])
        current = make_scenario(base, 'update')
        current['sources']['main']['revision'] += 1
        current['sources']['main']['rows'][0]['amount'] += 3
        public = public_episode(base, current, 'joint_update')
        for p in ('E', 'F', 'G'):
            result = replay(p, current, public, plan())
            self.assertEqual(result['tool_calls'], len(workflow(base['topology'])))
            self.assertEqual(result['artifact'], reference(current))

    def test_numeric_equality_does_not_imply_fresh_provenance(self):
        base = case_for()
        current = deepcopy(base)
        current['sources']['aux']['revision'] += 1
        public = public_episode(base, current, 'aux_update')
        result = replay('A', current, public, plan())
        self.assertEqual(score(result['artifact'], current), 'correct_completion')
        self.assertFalse(result['provenance_current'])

    def test_all_merge_parent_versions_retained(self):
        base = case_for(topology=(1, 2))
        current = make_scenario(base, 'update')
        runtime = Runtime(current, initial_receipts(base))
        for node in ('read_aux', 'partition_aux_0', 'summarize_aux_0', 'summarize_aux', 'combine', 'report'):
            runtime.execute(node)
        self.assertEqual(runtime.receipts['report']['source_versions']['aux'], [1, 2])

    def test_graph_contract_must_match_actual_tools(self):
        base = case_for()
        public = public_episode(base, base, 'clean')
        public['actual_dependencies']['combine'].remove('summarize_aux')
        with self.assertRaisesRegex(ValueError, 'actual_tool_contract_mismatch'):
            replay('G', base, public)

    def test_descendants_and_disconnected_nodes(self):
        graph = {'a': [], 'b': ['a'], 'c': ['b'], 'other': []}
        self.assertEqual(forward_closure(graph, ['a']), ['a', 'b', 'c'])
        self.assertEqual(forward_closure(graph, []), [])
        with self.assertRaises(ValueError):
            forward_closure(graph, ['missing'])


if __name__ == '__main__':
    unittest.main()
