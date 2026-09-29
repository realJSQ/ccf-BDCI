import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_replay_pipeline as pipeline


class WritingResourceRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.research = Path(self.temp.name) / 'research'
        self.run = self.research / 'replay_paper_runs/live-test'
        self.run.mkdir(parents=True)
        self.inventory = self.research / 'resource_runs.json'
        self.inventory.write_text(json.dumps({'scope': 'test', 'runs': []}))
        self.patch = patch.object(pipeline, 'HERE', self.research)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def write_run(self, *, status='completed', mode='live', calls=1):
        rows = [{'event': 'usage', 'call': 1, 'run_id': 'live-test',
                 'input_tokens': 4, 'output_tokens': 6, 'total_tokens': 10, 'finish_reason': 'stop'}]
        (self.run / 'model_usage.jsonl').write_text(json.dumps(rows[0]) + '\n')
        (self.run / 'model_summary.json').write_text(json.dumps({'status': status, 'mode': mode,
            'model_calls': calls, 'model_usage': rows, 'total_tokens': 10}))

    def test_completed_and_repeated_registration_count_once(self):
        self.write_run()
        first = pipeline.register_writing_resources(self.run)
        second = pipeline.register_writing_resources(self.run)
        self.assertEqual(first, second)
        self.assertEqual(second['historical_calls'], 1)
        self.assertEqual(second['historical_tokens'], 10)
        self.assertEqual(len(json.loads(self.inventory.read_text())['runs']), 1)

    def test_measured_failed_calls_remain_in_inventory(self):
        self.write_run(status='failed')
        self.assertEqual(pipeline.register_writing_resources(self.run)['tokens'], 10)

    def test_unknown_call_usage_is_not_fabricated(self):
        self.write_run(status='failed', calls=2)
        result = pipeline.register_writing_resources(self.run)
        self.assertEqual(result['status'], 'usage_unresolved')
        self.assertEqual(json.loads(self.inventory.read_text())['runs'], [])

    def test_scripted_usage_never_counted_as_live(self):
        self.write_run(mode='offline_scripted')
        self.assertEqual(pipeline.register_writing_resources(self.run)['status'], 'offline_not_live_usage')
        self.assertEqual(json.loads(self.inventory.read_text())['runs'], [])


if __name__ == '__main__':
    unittest.main()
