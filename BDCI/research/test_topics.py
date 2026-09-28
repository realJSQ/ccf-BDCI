"""Contract and state tests; no model or internet access."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from run_topics import DiscoveryState, parse_object, queries, scripted_responses, revision_queue


class TopicStateTests(unittest.TestCase):
    def test_json_duplicate_or_nonfinite_rejected(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}', '[]', 'plain prose'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_object(text)
        self.assertEqual(parse_object('```json\n{"a":1}\n```'), {"a": 1})

    def test_search_query_bounds(self):
        for value in ([], ['a'] * 2, ['a', 'b', 'c'], ['a\nb'], ['x' * 181]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                queries(value)

    def test_offline_flow_cannot_enable_live_pilot(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = DiscoveryState(Path(tmp), False)
            for role, response in zip(('planner', 'proposer', 'critic'), scripted_responses()):
                asyncio.run(state.accept(role, response))
            result = state.decide()
            self.assertEqual(result['status'], 'eligible_for_pilot')
            self.assertFalse(result['live_pilot_allowed'])
            self.assertFalse(result['novelty_proven'])
            self.assertEqual(len(state.sources), 2)

    def test_no_candidates_returns_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = DiscoveryState(Path(tmp), False)
            asyncio.run(state.accept('proposer', {'candidates': [], 'novelty_queries': []}))
            self.assertEqual(state.decide()['status'], 'needs_revision')

    def test_nonobject_candidates_and_critiques_stop_before_rendering(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = DiscoveryState(Path(tmp), False)
            for role, data in [('proposer', {'candidates': [None]}),
                               ('critic', {'critiques': ['bad']})]:
                with self.subTest(role=role), self.assertRaises(ValueError):
                    asyncio.run(state.accept(role, data))

    def test_revision_queue_preserves_criticism_without_retry(self):
        result = revision_queue([{'id':'C1','title':'test'}],
                                [{'candidate_id':'C1','verdict':'reject','reason':'overlap'}],
                                {'decisions':[{'candidate_id':'C1','status':'needs_revision',
                                               'reasons':['critic_did_not_advance']}]})
        self.assertEqual(result['items'][0]['action'], 'replace')
        self.assertEqual(result['items'][0]['critic']['reason'], 'overlap')
        self.assertFalse(result['automatic_retry'])
        self.assertEqual(result['next_model_calls'], 0)

    def test_source_context_truncation_is_disclosed(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = DiscoveryState(Path(tmp), False)
            state.sources['a'] = {'id':'a', 'title':'title', 'year':2026,
                                  'abstract':'x'*2000, 'evidence_kind':'retrieved'}
            row = state.source_context()[0]
            self.assertEqual(len(row['abstract']), 1400)
            self.assertTrue(row['abstract_truncated'])
            self.assertTrue(row['untrusted_data'])
            self.assertEqual(len(state.sources['a']['abstract']), 2000)


if __name__ == '__main__':
    unittest.main()
