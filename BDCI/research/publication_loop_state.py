"""Evidence-bound state for a bounded native manuscript review loop."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re

from paper_contracts import normalize_bound_issues, validate_review, validate_revision_response
from publication_quality import NARRATIVE, audit_publication
from publication_render import validate_publication
from replay_paper_evidence import digest
from run_publication_revision import HERE, PublicationState, SOURCE_GUIDANCE, profile_digest, validate_inline_citations
from run_topics import write_json


SKILL = HERE / 'skills/publication-loop'
ALL_ROLES = ('writer', 'reviser_0', 'reviewer_1', 'reviser_1', 'reviewer_2', 'reviser_2', 'reviewer_3')


def loop_profile_digest():
    paths = [Path(__file__), HERE / 'run_publication_loop.py', HERE.parent / 'activate.sh',
             HERE.parent / 'jiuwenswarm/jiuwenswarm/agents/harness/common/rails/research_budget_rail.py',
             *sorted(SKILL.rglob('*.md')), *sorted(SKILL.rglob('*.py'))]
    return digest({'base_publication_profile': profile_digest(),
                   'loop_files': {os.path.relpath(path, HERE): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in paths}})


def verified_inherited_literature(source_run: Path) -> dict:
    """Use saved primary texts only when the source run bound them."""
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
        inherited_review_path = source_run / 'external_review.json'
        if inherited_review_path.exists():
            inherited_review = json.loads(inherited_review_path.read_text())
            inherited_provenance = json.loads((source_run / 'input_provenance.json').read_text())
            if (inherited_provenance.get('external_review_sha256') != digest(inherited_review)
                    or inherited_review.get('schema') != 'bound_external_review/1'):
                raise ValueError('inherited_external_review_changed')
            self.external_review = inherited_review
        self.review_controls = {}
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
        if self.external_review is not None:
            self.provenance['external_review_sha256'] = digest(self.external_review)

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
                            'control': getattr(self, 'review_controls', {}).get(f'reviewer_{round_number}'),
                            'revision_response': revision.get('response_to_review') if revision else None})
        return history

    def prompt(self, role):
        if role != self.expected_next() or loop_profile_digest() != self.profile_hash:
            raise ValueError('publication_loop_role_or_profile_changed')
        data = {'scientific_context': self.science, 'sources': self.sources,
                'source_claim_guidance': SOURCE_GUIDANCE,
                'evidence_sha256': digest(self.evidence),
                'prior_quality_audit': self.prior_quality,
                'review_history': self.review_history(),
                'editorial_target': 'A complete, concise short paper; expand only where the evidence and argument need it. No page, word, or token target.'}
        if self.external_review is not None:
            data['external_review_of_earlier_pdf'] = self.external_review
        if role == 'writer':
            data.update(previous_model_draft=self.previous)
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
                            internal_review_control=getattr(self, 'review_controls', {}).get(
                                f"reviewer_{int(role.rsplit('_', 1)[1])}"),
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

    def _effective_review(self, model_review, paper):
        """Add grounded mechanical issues while preserving the model's review."""
        effective = copy.deepcopy(model_review)
        machine_issues = []
        existing_quotes = set(effective['issue_quotes'])
        sections = {section['id']: section['text'] for section in paper['sections']}
        for finding in self._text_findings(paper):
            section_id, identifier, verb = (finding[k] for k in ('section_id', 'source_id', 'verb'))
            matches = [match.group(0) for match in NARRATIVE.finditer(sections[section_id])
                       if match.group(1) == identifier and match.group(2) == verb]
            if not matches:
                raise ValueError('mechanical_finding_not_anchored')
            quote = next((candidate for candidate in matches if candidate not in existing_quotes), None)
            if quote is None:
                continue
            author_count = len(self.sources[identifier]['authors'])
            number = 'singular' if author_count == 1 else 'plural'
            issue = {'severity': 'minor', 'section_id': section_id,
                     'message': f'The cited source has {author_count} author(s); change the verb '
                                f'after this narrative citation to the {number} form.'}
            effective['issues'].append(issue)
            effective['issue_quotes'].append(quote)
            effective['revision_instructions'].append(
                f'Correct subject-verb agreement in {quote!r} and check adjacent narrative citations.')
            existing_quotes.add(quote)
            machine_issues.append({'finding': finding, 'quote': quote,
                                   'effective_issue_index': len(effective['issues']) - 1})
        if effective['issues']:
            effective['verdict'] = 'revise'
        validate_review({key: effective[key] for key in
                         ('verdict', 'external_reviewer', 'issues', 'revision_instructions')},
                        paper, max_field_chars=None)
        return effective, machine_issues

    def workflow_response(self, role, model_value):
        """Route by the effective review, without altering the archived raw reply."""
        return self.outputs[role] if role.startswith('reviewer_') else model_value

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
            bound_review = {**review, 'draft_sha256': value['draft_sha256'],
                            'evidence_sha256': value['evidence_sha256'],
                            'issue_quotes': copy.deepcopy(value['issue_quotes'])}
            effective, machine_issues = self._effective_review(bound_review, current)
            write_json(self.root / f'{role}_model.json', value)
            control = {
                'schema': 'review_control/1', 'model_verdict': value['verdict'],
                'model_issue_count': len(value['issues']), 'mechanical_issues': machine_issues,
                'effective_verdict': effective['verdict'], 'draft_sha256': value['draft_sha256']}
            self.review_controls = getattr(self, 'review_controls', {})
            self.review_controls[role] = control
            write_json(self.root / f'{role}_control.json', control)
            value = effective
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
        initial_role = self.expected_next()
        initial_prompt = self.prompt(initial_role)
        (self.root / f'prompt_{initial_role}.txt').write_text(initial_prompt)
        for template in ('reviewer', 'reviser'):
            (self.root / f'prompt_{template}_template.txt').write_text(
                (SKILL / 'roles' / f'{template}.md').read_text())
        write_json(self.root / 'egress_manifest.json', {
            'schema': 'publication_loop_egress/1',
            'provider': 'https://api.deepseek.com', 'model': 'deepseek-flash',
            'initial_role': initial_role,
            'initial_prompt_sha256': hashlib.sha256(initial_prompt.encode()).hexdigest(),
            'initial_prompt_chars': len(initial_prompt),
            'source_ids': sorted(self.sources),
            'data_categories': [
                'frozen synthetic experiment evidence and summary tables',
                f'{len(self.sources)} public version-verified arXiv paper excerpts and OpenAlex metadata',
                'previous model-generated manuscript and local mechanical quality findings',
            ],
            'later_role_payloads': 'The same experiment and source context, plus model-generated current drafts, bound internal reviews, and their revision history.',
            'credential_in_prompt': False,
            'planned_calls_maximum': 6,
        })
        write_json(self.root / 'prepared.json', {
            'input_sha256': digest(self.provenance), 'status': 'prepared',
            'initial_role': initial_role,
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


class FollowupState(LoopState):
    """Start with a model revision responding to the prior campaign's final review."""

    def __init__(self, root: Path, source_run: Path, *, live: bool,
                 failed_attempt: Path | None = None):
        super().__init__(root, source_run, live=live)
        source_run = Path(source_run).resolve()
        summary = json.loads((source_run / 'summary.json').read_text())
        if (summary.get('status') != 'needs_more_revision'
                or summary.get('final_internal_review') != 'revise'
                or summary.get('role_sequence', [])[-1:] != ['reviewer_3']):
            raise ValueError('source_has_no_final_review_to_continue')
        review = json.loads((source_run / 'reviewer_3.json').read_text())
        control = json.loads((source_run / 'reviewer_3_control.json').read_text())
        if (set(review) != {'verdict', 'external_reviewer', 'issues', 'revision_instructions',
                            'draft_sha256', 'evidence_sha256', 'issue_quotes'}
                or review['draft_sha256'] != digest(self.previous)
                or review['evidence_sha256'] != digest(self.evidence)
                or review['verdict'] != 'revise'
                or not review['issues']
                or control.get('draft_sha256') != review['draft_sha256']):
            raise ValueError('source_final_review_not_bound')
        validate_review({key: review[key] for key in
                         ('verdict', 'external_reviewer', 'issues', 'revision_instructions')},
                        self.previous, max_field_chars=None)
        sections = {section['id']: section['text'] for section in self.previous['sections']}
        sections['abstract'] = self.previous['abstract']
        if (len(review['issues']) != len(review['issue_quotes'])
                or any(quote not in sections[issue['section_id']]
                       for issue, quote in zip(review['issues'], review['issue_quotes']))):
            raise ValueError('source_final_review_not_grounded')
        self.seed_review = review
        self.review_controls['reviewer_0'] = control
        self.provenance.update(initial_role='reviser_0',
                               source_final_review_sha256=digest(review),
                               source_final_control_sha256=digest(control))
        self.failed_attempt_data = None
        if failed_attempt is not None:
            failed_attempt = Path(failed_attempt).resolve()
            if (failed_attempt.parent != (HERE / 'replay_paper_runs').resolve()
                    or failed_attempt in (source_run, self.root.resolve())):
                raise ValueError('invalid_failed_attempt_location')
            failed_provenance = json.loads((failed_attempt / 'input_provenance.json').read_text())
            failure = json.loads((failed_attempt / 'failure.json').read_text())
            metering = json.loads((failed_attempt / 'model_summary.json').read_text())
            raw = (failed_attempt / 'raw_reviser_0.txt').read_text()
            if (failed_provenance.get('source_run_relative') != str(source_run.relative_to(HERE))
                    or failed_provenance.get('source_final_review_sha256') != digest(review)
                    or failure.get('automatic_retry') is not False
                    or metering.get('status') != 'failed' or metering.get('model_calls') != 1
                    or len(metering.get('model_usage', [])) != 1
                    or (failed_attempt / 'role_sequence.json').exists()):
                raise ValueError('failed_attempt_not_bound_to_source_review')
            draft = self.decode_response(raw)
            validate_revision_response(draft, review, max_field_chars=None)
            if (not isinstance(draft.get('sections'), list)
                    or not any(re.search(r'\[\[citet?:\d{4}\.\d{4,5}v\d+\]\]',
                                         section.get('text', '')) for section in draft['sections'])):
                raise ValueError('failed_attempt_has_no_known_citation_defect')
            self.failed_attempt_data = {
                'paper': draft, 'validation_findings': [
                    'Citation markers in the prior model attempt omitted the literal arxiv: prefix.',
                    'It was rejected before PDF rendering; it is not an accepted manuscript.',
                ]}
            self.provenance.update(failed_attempt_relative=str(failed_attempt.relative_to(HERE)),
                                   failed_raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                                   failed_model_usage_sha256=hashlib.sha256(
                                       (failed_attempt / 'model_usage.jsonl').read_bytes()).hexdigest())

    def current_paper(self):
        return super().current_paper() if self.outputs else self.previous

    def latest_review(self):
        return super().latest_review() if any(role.startswith('reviewer_') for role in self.outputs) else self.seed_review

    def expected_next(self):
        return super().expected_next() if self.outputs else 'reviser_0'

    def review_history(self):
        return ([{'round': 0, 'review': self.seed_review,
                  'control': self.review_controls['reviewer_0'],
                  'revision_response': self.outputs.get('reviser_0', {}).get('response_to_review')}]
                + super().review_history())

    def archive_inputs(self):
        super().archive_inputs()
        write_json(self.root / 'source_final_review.json', self.seed_review)
        write_json(self.root / 'source_final_review_control.json', self.review_controls['reviewer_0'])
        if self.failed_attempt_data is not None:
            write_json(self.root / 'failed_attempt_for_model.json', self.failed_attempt_data)
            manifest_path = self.root / 'egress_manifest.json'
            manifest = json.loads(manifest_path.read_text())
            manifest['data_categories'].append('previous DeepSeek revision attempt rejected by citation validation')
            manifest['failed_attempt_raw_sha256'] = self.provenance['failed_raw_sha256']
            write_json(manifest_path, manifest)

    def prompt(self, role):
        prompt = super().prompt(role)
        if role == 'reviser_0' and self.failed_attempt_data is not None:
            prompt += '\nFAILED_MODEL_ATTEMPT_JSON\n' + json.dumps(self.failed_attempt_data, ensure_ascii=False)
        if re.search(r'\bsk-[A-Za-z0-9_-]{16,}\b', prompt):
            raise ValueError('credential_pattern_in_publication_prompt')
        return prompt
