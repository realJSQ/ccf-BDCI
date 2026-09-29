import copy
import json
from pathlib import Path
import tempfile
import unittest

from resource_accounting import audit_resources, source_path


class ResourceAccountingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rows = [{'call': 1, 'run_id': 'one', 'event': 'usage',
                      'input_tokens': 10, 'output_tokens': 2, 'total_tokens': 12}]
        self.summary = {'mode': 'live', 'model_calls': 1, 'model_usage': self.rows,
                        'total_tokens': 12, 'status': 'failed', 'duration_seconds': 3}
        self.inventory = {'scope': 'test', 'runs': [{'usage': 'run/usage.jsonl',
                                                   'summary': 'run/summary.json'}]}
        self.save()

    def save(self):
        (self.root / 'run').mkdir(exist_ok=True)
        (self.root / 'run/usage.jsonl').write_text('\n'.join(map(json.dumps, self.rows)))
        (self.root / 'run/summary.json').write_text(json.dumps(self.summary))

    def test_failed_usage_included_without_summing_duration(self):
        result = audit_resources(self.root, self.inventory)
        self.assertEqual(result['total_calls'], 1)
        self.assertEqual(result['total_tokens'], 12)
        self.assertIsNone(result['wall_clock_end_to_end_seconds'])

    def test_stale_summary_and_offline_rejected(self):
        self.summary['total_tokens'] = 13
        self.save()
        with self.assertRaisesRegex(ValueError, 'summary_mismatch'):
            audit_resources(self.root, self.inventory)
        self.summary['mode'] = 'offline'
        self.save()
        with self.assertRaisesRegex(ValueError, 'not_live'):
            audit_resources(self.root, self.inventory)

    def test_duplicate_run_and_copied_usage_rejected(self):
        self.inventory['runs'].append(copy.deepcopy(self.inventory['runs'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            audit_resources(self.root, self.inventory)
        (self.root / 'copy').mkdir()
        for name in ('usage.jsonl', 'summary.json'):
            (self.root / 'copy' / name).write_bytes((self.root / 'run' / name).read_bytes())
        self.inventory['runs'][1] = {'usage': 'copy/usage.jsonl', 'summary': 'copy/summary.json'}
        with self.assertRaisesRegex(ValueError, 'duplicate_resource_call'):
            audit_resources(self.root, self.inventory)

    def test_inconsistent_token_arithmetic_rejected(self):
        self.rows[0]['total_tokens'] = 15
        self.save()
        with self.assertRaisesRegex(ValueError, 'invalid_resource_usage'):
            audit_resources(self.root, self.inventory)

    def test_parent_escape_and_symlink_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unsafe_resource_path'):
            source_path(self.root, '../elsewhere')
        (self.root / 'link').symlink_to(self.root / 'run', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'unsafe_resource_path'):
            source_path(self.root, 'link/usage.jsonl')


if __name__ == '__main__':
    unittest.main()
