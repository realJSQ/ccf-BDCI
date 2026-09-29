"""Submission boundaries that must hold without contacting external services."""
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build_publication_submission import safe_copy
from submit_agentic_review import main as review_main


class PublicationSubmissionTests(unittest.TestCase):
    def test_packaging_rejects_credential_like_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'notes.txt'
            source.write_text('sk-' + 'a' * 20, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'credential_like_content'):
                safe_copy(source, root / 'package' / 'notes.txt', root)

    def test_reviewer_contact_cannot_be_read_from_git(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            args = ['--pdf', str(path / 'draft.pdf'), '--output', str(path / 'token.json')]
            with patch.dict(os.environ, {'PAPER_REVIEW_EMAIL': ''}), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as absent:
                    review_main([*args, '--contact-authorized'])
                with self.assertRaises(SystemExit) as removed_option:
                    review_main([*args, '--contact-authorized', '--email-from-git'])
            self.assertEqual(absent.exception.code, 2)
            self.assertEqual(removed_option.exception.code, 2)
            self.assertFalse((path / 'token.json').exists())

    def test_reviewer_upload_requires_explicit_contact_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with patch.dict(os.environ, {'PAPER_REVIEW_EMAIL': 'owner@example.invalid'}), \
                    redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as rejected:
                    review_main(['--pdf', str(path / 'draft.pdf'),
                                 '--output', str(path / 'token.json')])
            self.assertEqual(rejected.exception.code, 2)
            self.assertFalse((path / 'token.json').exists())


if __name__ == '__main__':
    unittest.main()
