"""Structural paper/review gates, not verification of scientific correctness.

Passing these checks establishes only bounded structure, known citation IDs and
review-response coverage. It cannot establish that claims follow from sources,
that a review is insightful, or that a revision actually resolves its issues.
"""
from collections.abc import Mapping
import copy

SECTION_IDS = ('introduction', 'related_work', 'methods', 'discussion', 'conclusion')
# This bounds artifact size, not scientific quality or competition eligibility.
# The competition has no 1200-word requirement; retain complete bounded revisions.
MAX_WORDS = 1600
MAX_FIELD_CHARS = 10000


def normalize_bound_issues(review, quotes):
    """Remove only exact duplicate annotations; preserve all substantive text."""
    normalized = copy.deepcopy(review)
    issues = normalized.get('issues')
    if not isinstance(issues, list) or not isinstance(quotes, list) or len(issues) != len(quotes):
        raise ValueError('unanchored_review')
    for issue, quote in zip(issues, quotes):
        if not isinstance(issue, dict):
            raise ValueError('invalid_review_issue')
        if 'section_id_note' in issue and issue.pop('section_id_note') != issue.get('section_id'):
            raise ValueError('conflicting_section_annotation')
        if 'quote' in issue and issue.pop('quote') != quote:
            raise ValueError('conflicting_quote_annotation')
    return normalized


def _text(value, field, max_field_chars=MAX_FIELD_CHARS):
    if (max_field_chars is not None and (type(max_field_chars) is not int or max_field_chars <= 0)):
        raise ValueError('invalid_field_character_limit')
    if not isinstance(value, str) or not value.strip() or (max_field_chars is not None and len(value) > max_field_chars):
        raise ValueError(f'invalid_text:{field}')


def _keys(value, expected, field):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f'invalid_fields:{field}')


def validate_paper(paper, sources, *, max_words=MAX_WORDS, max_field_chars=MAX_FIELD_CHARS):
    """Validate a paper without changing it; returns None or raises ValueError.

    Sections are a list of ID-bearing objects. Results and numeric truth tables are owned
    by the deterministic renderer, never by generated paper structure. An
    optional response_to_review is checked separately for a revised paper.
    """
    if (not isinstance(paper, dict) or not {'title', 'abstract', 'sections'} <= set(paper)
            or not set(paper) <= {'title', 'abstract', 'sections', 'response_to_review'}):
        raise ValueError('invalid_fields:paper')
    if not isinstance(sources, Mapping):
        raise ValueError('invalid_source_mapping')
    _text(paper['title'], 'title', max_field_chars)
    _text(paper['abstract'], 'abstract', max_field_chars)
    sections = paper['sections']
    if not isinstance(sections, list) or len(sections) != len(SECTION_IDS):
        raise ValueError('invalid_fields:sections')
    section_map = {}
    for section in sections:
        _keys(section, ('id', 'text', 'source_ids'), 'section')
        section_id = section['id']
        if not isinstance(section_id, str) or section_id not in SECTION_IDS or section_id in section_map:
            raise ValueError('invalid_section_id')
        section_map[section_id] = section
    texts = [paper['title'], paper['abstract']]
    cited = set()
    for section_id in SECTION_IDS:
        section = section_map[section_id]
        _text(section['text'], section_id, max_field_chars)
        texts.append(section['text'])
        refs = section['source_ids']
        if (not isinstance(refs, list) or any(not isinstance(ref, str) or not ref.strip()
                                            or len(ref) > MAX_FIELD_CHARS for ref in refs)
                or len(set(refs)) != len(refs)):
            raise ValueError(f'invalid_source_ids:{section_id}')
        if section_id == 'related_work' and not refs:
            raise ValueError('related_work_requires_reference')
        for ref in refs:
            source = sources.get(ref)
            if (not isinstance(source, Mapping) or source.get('id') != ref
                    or source.get('evidence_kind') != 'retrieved'):
                raise ValueError(f'unverified_reference:{ref}')
            cited.add(ref)
    if len(cited) < 2:
        raise ValueError('at_least_two_references_required')
    if max_words is not None and (type(max_words) is not int or max_words <= 0):
        raise ValueError('invalid_paper_word_limit')
    if max_words is not None and sum(len(text.split()) for text in texts) > max_words:
        raise ValueError('paper_word_limit')


def validate_review(review, paper, *, max_field_chars=MAX_FIELD_CHARS):
    """Validate internal-review structure, never imply an external review."""
    _keys(review, ('verdict', 'issues', 'revision_instructions', 'external_reviewer'), 'review')
    if review['verdict'] not in ('pass', 'revise'):
        raise ValueError('invalid_review_verdict')
    if review['external_reviewer'] is not False:
        raise ValueError('external_reviewer_must_be_false')
    if not isinstance(paper, dict) or not isinstance(paper.get('sections'), list):
        raise ValueError('invalid_reviewed_paper')
    paper_section_ids = [section.get('id') for section in paper['sections'] if isinstance(section, dict)]
    issues = review['issues']
    if not isinstance(issues, list):
        raise ValueError('invalid_review_issues')
    for issue in issues:
        _keys(issue, ('severity', 'section_id', 'message'), 'review_issue')
        if issue['severity'] not in ('blocking', 'major', 'minor'):
            raise ValueError('invalid_issue_severity')
        section_id = issue['section_id']
        if (not isinstance(section_id, str) or section_id not in ('abstract',) + SECTION_IDS
                or (section_id != 'abstract' and section_id not in paper_section_ids)):
            raise ValueError('unknown_review_section')
        _text(issue['message'], 'issue.message', max_field_chars)
        if review['verdict'] == 'pass' and issue['severity'] in ('blocking', 'major'):
            raise ValueError('contradictory_pass_review')
    instructions = review['revision_instructions']
    if not isinstance(instructions, list):
        raise ValueError('invalid_revision_instructions')
    for instruction in instructions:
        _text(instruction, 'revision_instruction', max_field_chars)


def validate_revision_response(revised, review, *, max_field_chars=MAX_FIELD_CHARS):
    """Require one response per issue, without claiming semantic resolution."""
    if not isinstance(revised, dict) or not isinstance(review, dict):
        raise ValueError('invalid_revision_or_review')
    issues = review.get('issues')
    responses = revised.get('response_to_review')
    if not isinstance(issues, list) or not isinstance(responses, list):
        raise ValueError('invalid_revision_response')
    seen = set()
    for response in responses:
        _keys(response, ('issue_index', 'change'), 'issue_response')
        index = response['issue_index']
        if type(index) is not int or index < 0 or index >= len(issues) or index in seen:
            raise ValueError('invalid_or_duplicate_issue_index')
        _text(response['change'], 'response.change', max_field_chars)
        seen.add(index)
    if seen != set(range(len(issues))):
        raise ValueError('missing_issue_response')
