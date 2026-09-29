"""Evidence-bound state for a bounded native manuscript review loop."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re

from paper_contracts import normalize_bound_issues, validate_review, validate_revision_response
from publication_quality import audit_publication
from publication_render import validate_publication
from replay_paper_evidence import digest
from run_publication_revision import HERE, PublicationState, SOURCE_GUIDANCE, profile_digest, validate_inline_citations
from run_topics import write_json


SKILL = HERE / 'skills/publication-loop'
ALL_ROLES = ('writer', 'reviewer_1', 'reviser_1', 'reviewer_2', 'reviser_2', 'reviewer_3')


def loop_profile_digest():
    paths = [Path(__file__), HERE / 'run_publication_loop.py', HERE.parent / 'activate.sh',
             HERE.parent / 'jiuwenswarm/jiuwenswarm/agents/harness/common/rails/research_budget_rail.py',
             *sorted(SKILL.rglob('*.md')), *sorted(SKILL.rglob('*.py'))]
    return digest({'base_publication_profile': profile_digest(),
                   'loop_files': {os.path.relpath(path, HERE): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in paths}})


def verified_inherited_literature(source_run: Path) -> dict:
    """Use the six saved primary texts only when the source run bound them."""
    source_run = Path(source_run).resolve()
    provenance = json.loads((source_run / 'input_provenance.json').read_text())
    manifest = json.loads((source_run / 'literature_manifest.json').read_text())
    sources = json.loads((source_run / 'sources.json').read_text())
    if (provenance.get('literature_manifest_sha256') != digest(manifest)
            or provenance.get('sources_sha256') != digest(sources)
            or sources != manifest.get('sources')
            or len(sources) < 6):
        raise ValueError('inherited_primary_literature_changed')
    for identifier, source in sources.items():
        if (source.get('id') != identifier or source.get('verification_status') != 'primary_fulltext'
                or not isinstance(source.get('primary_text_excerpt'), str)
                or len(source['primary_text_excerpt']) < 4000):
            raise ValueError('inherited_primary_literature_unverified')
    return manifest


class LoopState(PublicationState):
    roles = ALL_ROLES

    def __init__(self, root: Path, source_run: Path, *, live: bool):
        if type(live) is not bool:
            raise ValueError('invalid_publication_loop_mode')
        source_run = Path(source_run).resolve()
        literature = verified_inherited_literature(source_run)
        super().__init__(root, source_run, live=live, literature_manifest=literature)
        self.source_run = source_run
        self.prior_quality = audit_publication(self.previous, self.sources, source_run / 'paper.pdf')
        saved_quality = source_run / 'quality_audit.json'
        if saved_quality.exists() and json.loads(saved_quality.read_text()) != self.prior_quality:
            raise ValueError('source_quality_audit_changed')
        self.profile_hash = loop_profile_digest()
        self.provenance.update(schema='publication_review_loop/1', profile_sha256=self.profile_hash,
                               prior_quality_sha256=digest(self.prior_quality),
                               minimum_reviews=2, maximum_reviews=3, maximum_revisions=2,
                               planned_calls_maximum=6, target_pages=None,
                               length_policy='Expand only where needed for a complete argument; no page target')

    def current_paper(self):
        for role in reversed(self.outputs):
            if role == 'writer' or role.startswith('reviser_'):
                return self.outputs[role]
        raise ValueError('manuscript_not_written')

    def latest_review(self):
        for role in reversed(self.outputs):
            if role.startswith('reviewer_'):
                return self.outputs[role]
        raise ValueError('manuscript_not_reviewed')

    def expected_next(self):
        if not self.outputs:
            return 'writer'
        last = next(reversed(self.outputs))
        if last == 'writer':
            return 'reviewer_1'
        if last.startswith('reviser_'):
            return 'reviewer_' + str(int(last.rsplit('_', 1)[1]) + 1)
        round_number = int(last.rsplit('_', 1)[1])
        review = self.outputs[last]
        needs_revision = review['verdict'] == 'revise' or bool(review['issues'])
        if round_number == 3 or (round_number >= 2 and not needs_revision):
            return None
        if needs_revision:
            return 'reviser_' + str(round_number)
        return 'reviewer_2'

    def review_history(self):
        history = []
        for round_number in (1, 2, 3):
            review = self.outputs.get(f'reviewer_{round_number}')
            if review is None:
                continue
            revision = self.outputs.get(f'reviser_{round_number}')
            history.append({'round': round_number, 'review': review,
                            'revision_response': revision.get('response_to_review') if revision else None})
        return history

    def prompt(self, role):
        if role != self.expected_next() or loop_profile_digest() != self.profile_hash:
            raise ValueError('publication_loop_role_or_profile_changed')
        data = {'scientific_context': self.science, 'sources': self.sources,
                'source_claim_guidance': SOURCE_GUIDANCE,
                'evidence_sha256': digest(self.evidence),
                'review_history': self.review_history(),
                'editorial_target': 'A complete, concise short paper; expand only where the evidence and argument need it. No page, word, or token target.'}
        if role == 'writer':
            data.update(previous_model_draft=self.previous, prior_quality_audit=self.prior_quality)
            template = 'writer.md'
        else:
            current = self.current_paper()
            data.update(current_draft=current, draft_sha256=digest(current),
                        draft_text_findings=self._text_findings(current))
            if role.startswith('reviewer_'):
                data['review_round'] = int(role.rsplit('_', 1)[1])
                template = 'reviewer.md'
            else:
                data.update(internal_review=self.latest_review(),
                            revision_round=int(role.rsplit('_', 1)[1]))
                template = 'reviser.md'
        prompt = (SKILL / 'roles' / template).read_text() + '\nCURRENT_DATA_JSON\n' + json.dumps(data, ensure_ascii=False)
        if re.search(r'\bsk-[A-Za-z0-9_-]{16,}\b', prompt):
            raise ValueError('credential_pattern_in_publication_prompt')
        return prompt

    def _text_findings(self, paper):
        # The full layout audit waits for PDF compilation; this catches the
        # previous single-author citation grammar defect before the next review.
        from publication_quality import narrative_citation_findings
        return narrative_citation_findings(paper, self.sources)

    def accept(self, role, value):
        if role != self.expected_next():
            raise ValueError('publication_loop_role_order')
        if role == 'writer' or role.startswith('reviser_'):
            validate_publication(value, self.sources, self.evidence)
            validate_inline_citations(value, self.sources)
            if role == 'writer':
                if set(value) != {'title', 'abstract', 'sections'}:
                    raise ValueError('writer_must_return_manuscript_only')
            else:
                validate_revision_response(value, self.latest_review(), max_field_chars=None)
                if (any(issue['severity'] in ('blocking', 'major') for issue in self.latest_review()['issues'])
                        and all(value[k] == self.current_paper()[k] for k in ('title', 'abstract', 'sections'))):
                    raise ValueError('major_review_without_revision')
        else:
            if not isinstance(value, dict) or set(value) != {
                    'verdict', 'external_reviewer', 'issues', 'revision_instructions',
                    'draft_sha256', 'evidence_sha256', 'issue_quotes'}:
                raise ValueError('invalid_bound_review')
            current = self.current_paper()
            if value['draft_sha256'] != digest(current) or value['evidence_sha256'] != digest(self.evidence):
                raise ValueError('review_target_mismatch')
            review = normalize_bound_issues(
                {key: copy.deepcopy(value[key]) for key in
                 ('verdict', 'external_reviewer', 'issues', 'revision_instructions')},
                value['issue_quotes'])
            validate_review(review, current, max_field_chars=None)
            quotes = value['issue_quotes']
            sections = {section['id']: section['text'] for section in current['sections']}
            sections['abstract'] = current['abstract']
            if any(not isinstance(quote, str) or not quote.strip()
                   or quote not in sections[issue['section_id']]
                   for issue, quote in zip(review['issues'], quotes)):
                raise ValueError('ungrounded_review')
            if len(quotes) != len(review['issues']):
                raise ValueError('unanchored_review')
        self.outputs[role] = copy.deepcopy(value)
        write_json(self.root / f'{role}.json', value)
        write_json(self.root / 'role_sequence.json', list(self.outputs))

    def archive_inputs(self):
        for name, value in [('evidence', self.evidence), ('sources', self.sources),
                            ('scientific_context', self.science), ('source_paper', self.previous),
                            ('input_provenance', self.provenance),
                            ('posthoc_plan_analysis', self.posthoc_plan_analysis),
                            ('literature_manifest', self.literature_manifest),
                            ('prior_quality_audit', self.prior_quality)]:
            write_json(self.root / f'{name}.json', value)
        writer_prompt = self.prompt('writer')
        (self.root / 'prompt_writer.txt').write_text(writer_prompt)
        for template in ('reviewer', 'reviser'):
            (self.root / f'prompt_{template}_template.txt').write_text(
                (SKILL / 'roles' / f'{template}.md').read_text())
        write_json(self.root / 'egress_manifest.json', {
            'schema': 'publication_loop_egress/1',
            'provider': 'https://api.deepseek.com', 'model': 'deepseek-flash',
            'writer_prompt_sha256': hashlib.sha256(writer_prompt.encode()).hexdigest(),
            'writer_prompt_chars': len(writer_prompt),
            'source_ids': sorted(self.sources),
            'data_categories': [
                'frozen synthetic experiment evidence and summary tables',
                'six public version-verified arXiv paper excerpts and OpenAlex metadata',
                'previous model-generated manuscript and local mechanical quality findings',
            ],
            'later_role_payloads': 'The same experiment and source context, plus model-generated current drafts, bound internal reviews, and their revision history.',
            'credential_in_prompt': False,
            'planned_calls_maximum': 6,
        })
        write_json(self.root / 'prepared.json', {
            'input_sha256': digest(self.provenance), 'status': 'prepared',
            'minimum_reviews': 2, 'maximum_reviews': 3, 'maximum_revisions': 2,
            'planned_calls_maximum': 6, 'token_stop': None,
            'dependent_prompts': 'Each review binds the current model paper and evidence hash; each revision binds its preceding review.'})

    def offline_response(self, role):
        if self.live:
            raise ValueError('scripted_response_in_live_mode')
        if role == 'writer':
            return {key: copy.deepcopy(self.previous[key]) for key in ('title', 'abstract', 'sections')}
        if role.startswith('reviewer_'):
            return {'verdict': 'pass', 'external_reviewer': False, 'issues': [],
                    'revision_instructions': [], 'draft_sha256': digest(self.current_paper()),
                    'evidence_sha256': digest(self.evidence), 'issue_quotes': []}
        raise ValueError('offline_revision_requires_explicit_test_fixture')
