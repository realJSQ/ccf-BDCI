"""Adversarial cache freshness examples: no models, tools or external data."""
import copy
import unittest

from protocol_graph import analyze_graph_example


def example():
    nodes = ['main', 'aux', 'summary_main', 'summary_aux', 'combine', 'report']
    dependencies = {'main': [], 'aux': [], 'summary_main': ['main'],
                    'summary_aux': ['aux'], 'combine': ['summary_main', 'summary_aux'],
                    'report': ['combine']}
    closure = ['aux', 'summary_aux', 'combine', 'report']
    return {'nodes': nodes, 'actual_dependencies': dependencies,
            'declared_dependencies': copy.deepcopy(dependencies),
            'changed_sources': ['aux'], 'cached_source_versions': {'main': 0, 'aux': 0},
            'current_source_versions': {'main': 0, 'aux': 1},
            'actions': [{'op': 'rerun', 'node': n} for n in closure] + [{'op': 'emit', 'node': 'report'}],
            'claimed_closure': closure, 'tool_budget': 4}


class GraphExampleTests(unittest.TestCase):
    def test_complete_closure_recovers_report(self):
        result = analyze_graph_example(example())
        self.assertTrue(result['completed'])
        self.assertTrue(result['provenance_current'])
        self.assertTrue(result['closure_claim_valid'])
        self.assertEqual(result['tool_attempts'], 4)
        self.assertEqual(result['output_source_versions'], {'aux': [1], 'main': [0]})

    def test_missing_report_claim_is_diagnosed_even_when_execution_fresh(self):
        spec = example()
        spec['claimed_closure'].remove('report')
        result = analyze_graph_example(spec)
        self.assertFalse(result['closure_claim_valid'])
        self.assertEqual(result['diagnostics'][0]['missing_nodes'], ['report'])
        self.assertTrue(result['provenance_current'])

    def test_emit_does_not_recompute_report_after_combine(self):
        spec = example()
        spec['actions'].pop(-2)
        result = analyze_graph_example(spec)
        self.assertTrue(result['completed'])
        self.assertFalse(result['provenance_current'])
        self.assertEqual(result['stale_sources'], ['aux'])
        self.assertEqual(result['tool_attempts'], 3)

    def test_missing_declared_edge_does_not_remove_actual_read(self):
        spec = example()
        spec['declared_dependencies']['combine'] = ['summary_main']
        spec['claimed_closure'] = ['aux', 'summary_aux']
        spec['actions'] = [{'op': 'rerun', 'node': n} for n in spec['claimed_closure']] + [{'op': 'emit', 'node': 'report'}]
        result = analyze_graph_example(spec)
        self.assertTrue(result['closure_claim_valid'])
        self.assertFalse(result['provenance_current'])
        self.assertEqual(result['stale_sources'], ['aux'])

    def test_rerunning_wrong_source_leaves_changed_input_stale(self):
        spec = example()
        spec['actions'][0]['node'] = 'main'
        self.assertFalse(analyze_graph_example(spec)['provenance_current'])
        spec['changed_sources'] = ['main']
        with self.assertRaisesRegex(ValueError, 'version differences'):
            analyze_graph_example(spec)

    def test_diamond_keeps_mixed_old_and_new_versions(self):
        spec = example()
        spec['actual_dependencies']['summary_main'] = ['aux']
        spec['declared_dependencies'] = copy.deepcopy(spec['actual_dependencies'])
        spec['claimed_closure'].insert(1, 'summary_main')
        result = analyze_graph_example(spec)
        self.assertEqual(result['output_source_versions'], {'aux': [0, 1]})
        self.assertFalse(result['provenance_current'])

    def test_budget_and_repeated_reruns(self):
        spec = example()
        spec['actions'].insert(0, {'op': 'rerun', 'node': 'aux'})
        result = analyze_graph_example(spec)
        self.assertEqual(result['tool_attempts'], 4)
        self.assertEqual(result['termination'], 'tool_budget_exhausted')
        self.assertFalse(result['completed'])
        self.assertIsNone(result['emitted_node'])
        spec['tool_budget'] = 5
        self.assertTrue(analyze_graph_example(spec)['provenance_current'])

    def test_refusal_is_not_completion(self):
        spec = example()
        spec['actions'] = [{'op': 'refuse'}]
        result = analyze_graph_example(spec)
        self.assertFalse(result['completed'])
        self.assertFalse(result['provenance_current'])
        self.assertEqual(result['termination'], 'refused')
        self.assertEqual(result['tool_attempts'], 0)

    def test_clean_cache_can_emit_without_budget(self):
        spec = example()
        spec['current_source_versions'] = dict(spec['cached_source_versions'])
        spec['changed_sources'] = []
        spec['claimed_closure'] = []
        spec['actions'] = [{'op': 'emit', 'node': 'report'}]
        spec['tool_budget'] = 0
        self.assertTrue(analyze_graph_example(spec)['provenance_current'])

    def test_invalid_schema_graph_and_actions_are_rejected(self):
        mutations = [
            lambda s: s.update(extra='forbidden'),
            lambda s: s['actual_dependencies']['main'].append('report'),
            lambda s: s['declared_dependencies']['main'].append('unknown'),
            lambda s: s['actual_dependencies']['report'].append('combine'),
            lambda s: s['nodes'].append('report'),
            lambda s: s['cached_source_versions'].update(aux=True),
            lambda s: s.update(tool_budget=True),
            lambda s: s['actions'].append({'op': 'rerun', 'node': 'main'}),
            lambda s: s.update(actions=[{'op': 'execute', 'code': 'evil'}]),
            lambda s: s.update(actions=[{'op': 'emit', 'node': 'report', 'value': 1}]),
            lambda s: s.update(actions=[{'op': 'rerun', 'node': 'main'}] * 128 + [{'op': 'refuse'}]),
            lambda s: s['changed_sources'].append('aux'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                spec = example()
                mutate(spec)
                with self.assertRaises(ValueError):
                    analyze_graph_example(spec)

    def test_input_is_not_mutated(self):
        spec = example()
        before = copy.deepcopy(spec)
        analyze_graph_example(spec)
        self.assertEqual(spec, before)


if __name__ == '__main__':
    unittest.main()
