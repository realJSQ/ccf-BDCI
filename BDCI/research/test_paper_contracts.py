"""No-model tests for paper structure, citation provenance and review coverage."""
import copy
import unittest

try:
    from .paper_contracts import SECTION_IDS, validate_paper, validate_review, validate_revision_response
except ImportError:
    from paper_contracts import SECTION_IDS, validate_paper, validate_review, validate_revision_response


class PaperContractTests(unittest.TestCase):
    def setUp(self):
        self.sources = {key: {'id': key, 'evidence_kind': 'retrieved'} for key in ('a', 'b')}
        self.paper = {'title': 'A descriptive feasibility pilot', 'abstract': 'A bounded exploratory observation.',
                      'sections': [{'id': key, 'text': 'A concise scientific discussion.', 'source_ids': []}
                                   for key in SECTION_IDS]}
        self.paper['sections'][1]['source_ids'] = ['a', 'b']
        self.review = {'verdict': 'revise', 'external_reviewer': False,
                       'issues': [{'severity': 'major', 'section_id': 'abstract', 'message': 'Clarify the pilot scope.'},
                                  {'severity': 'minor', 'section_id': 'methods', 'message': 'Clarify the comparison.'}],
                       'revision_instructions': ['State the limited scope.']}

    def test_valid_data_returns_none_and_is_unchanged(self):
        original = copy.deepcopy(self.paper)
        self.assertIsNone(validate_paper(self.paper, self.sources))
        self.assertEqual(self.paper, original)
        self.assertIsNone(validate_review(self.review, self.paper))

    def test_fabricated_source_id_rejected(self):
        self.paper['sections'][1]['source_ids'].append('invented')
        with self.assertRaisesRegex(ValueError, 'unverified_reference'):
            validate_paper(self.paper, self.sources)

    def test_source_identity_and_retrieval_provenance_required(self):
        for patch in ({'id': 'wrong'}, {'evidence_kind': 'synthetic'}, {'evidence_kind': None}):
            sources = copy.deepcopy(self.sources)
            sources['a'].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate_paper(self.paper, sources)

    def test_duplicate_references_within_section_rejected_but_cross_section_allowed(self):
        self.paper['sections'][2]['source_ids'] = ['a']
        validate_paper(self.paper, self.sources)
        self.paper['sections'][1]['source_ids'].append('a')
        with self.assertRaises(ValueError):
            validate_paper(self.paper, self.sources)

    def test_minimum_and_related_work_references(self):
        self.paper['sections'][1]['source_ids'] = ['a']
        with self.assertRaisesRegex(ValueError, 'at_least_two'):
            validate_paper(self.paper, self.sources)
        self.paper['sections'][2]['source_ids'] = ['a', 'b']
        self.paper['sections'][1]['source_ids'] = []
        with self.assertRaisesRegex(ValueError, 'related_work_requires'):
            validate_paper(self.paper, self.sources)

    def test_extra_results_and_missing_sections_rejected(self):
        for key in ('results', 'appendix'):
            paper = copy.deepcopy(self.paper)
            paper['sections'].append({'id': key, 'text': 'Invented results', 'source_ids': []})
            with self.assertRaises(ValueError):
                validate_paper(paper, self.sources)
        del self.paper['sections'][2]
        with self.assertRaises(ValueError):
            validate_paper(self.paper, self.sources)

    def test_duplicate_or_replaced_section_id_rejected(self):
        for identifier in ('introduction', 'results', None):
            paper = copy.deepcopy(self.paper)
            paper['sections'][2]['id'] = identifier
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                validate_paper(paper, self.sources)

    def test_extra_fields_empty_or_oversized_text_rejected(self):
        for value in ('', '  ', None, 'x' * 10001):
            self.paper['title'] = value
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError):
                validate_paper(self.paper, self.sources)
        self.paper['title'] = 'A title'
        self.paper['scores'] = {'competition': 100}
        with self.assertRaises(ValueError):
            validate_paper(self.paper, self.sources)

    def test_english_word_limit(self):
        self.paper['abstract'] = 'word ' * 1600
        with self.assertRaisesRegex(ValueError, 'paper_word_limit'):
            validate_paper(self.paper, self.sources)

    def test_fake_external_review_rejected(self):
        for value in (True, 0, 'false', None):
            self.review['external_reviewer'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'external_reviewer'):
                validate_review(self.review, self.paper)

    def test_pass_with_major_or_blocking_issue_rejected(self):
        self.review['verdict'] = 'pass'
        for severity in ('major', 'blocking'):
            self.review['issues'][0]['severity'] = severity
            with self.assertRaisesRegex(ValueError, 'contradictory_pass'):
                validate_review(self.review, self.paper)
        self.review['issues'][0]['severity'] = 'minor'
        validate_review(self.review, self.paper)

    def test_unknown_review_section(self):
        self.review['issues'][0]['section_id'] = 'results'
        with self.assertRaisesRegex(ValueError, 'unknown_review_section'):
            validate_review(self.review, self.paper)

    def test_revision_responds_to_every_issue_once_without_mutation(self):
        self.paper['response_to_review'] = [{'issue_index': 1, 'change': 'Expanded comparison.'},
                                            {'issue_index': 0, 'change': 'Narrowed claims.'}]
        original = copy.deepcopy(self.paper)
        self.assertIsNone(validate_revision_response(self.paper, self.review))
        validate_paper(self.paper, self.sources)
        self.assertEqual(self.paper, original)

    def test_missing_duplicate_boolean_and_unknown_response_indices(self):
        for responses in ([], [{'issue_index': 0, 'change': 'One fix'}],
                          [{'issue_index': 0, 'change': 'Fix'}] * 2,
                          [{'issue_index': False, 'change': 'Fix'}, {'issue_index': 1, 'change': 'Fix'}],
                          [{'issue_index': 2, 'change': 'Fix'}]):
            self.paper['response_to_review'] = responses
            with self.subTest(responses=responses), self.assertRaises(ValueError):
                validate_revision_response(self.paper, self.review)

    def test_no_issues_requires_empty_response_list(self):
        self.review['issues'] = []
        self.paper['response_to_review'] = []
        validate_revision_response(self.paper, self.review)


if __name__ == '__main__':
    unittest.main()
