import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import publication_loop_state as loop
from paper_contracts import SECTION_IDS
from replay_paper_evidence import digest
from run_publication_loop import paper_summary


def manuscript():
    return {'title': 'A paper', 'abstract': 'A bounded abstract',
            'sections': [{'id': sid, 'text': 'An anchored claim.', 'source_ids': []}
                         for sid in SECTION_IDS]}


def review(paper, evidence, *, verdict, issues=None):
    issues = issues or []
    return {'verdict': verdict, 'external_reviewer': False, 'issues': issues,
            'revision_instructions': ['Correct the anchored issue'] if issues else [],
            'draft_sha256': digest(paper), 'evidence_sha256': digest(evidence),
            'issue_quotes': ['An anchored claim.'] * len(issues)}


class PublicationLoopTests(unittest.TestCase):
    def test_two_reviews_may_pass_without_spending_revision_call(self):
        with tempfile.TemporaryDirectory() as name:
            state = loop.LoopState.__new__(loop.LoopState)
            state.root = Path(name); state.outputs = {}; state.evidence = {'fixed': True}; state.sources = {}
            paper = manuscript()
            state.previous = paper
            with patch.object(loop, 'validate_publication'):
                self.assertEqual(state.expected_next(), 'writer')
                state.accept('writer', paper)
                state.accept('reviewer_1', review(paper, state.evidence, verdict='pass'))
                self.assertEqual(state.expected_next(), 'reviewer_2')
                state.accept('reviewer_2', review(paper, state.evidence, verdict='pass'))
            self.assertIsNone(state.expected_next())
            self.assertEqual(list(state.outputs), ['writer', 'reviewer_1', 'reviewer_2'])

    def test_two_revisions_and_final_review_are_bound_to_current_draft(self):
        with tempfile.TemporaryDirectory() as name:
            state = loop.LoopState.__new__(loop.LoopState)
            state.root = Path(name); state.outputs = {}; state.evidence = {'fixed': True}; state.sources = {}
            paper = manuscript()
            state.previous = paper
            issue = {'severity': 'minor', 'section_id': 'introduction',
                     'message': 'Improve this anchored sentence.'}
            with patch.object(loop, 'validate_publication'):
                state.accept('writer', paper)
                bad = review(paper, state.evidence, verdict='revise', issues=[issue])
                bad['draft_sha256'] = 'wrong'
                with self.assertRaisesRegex(ValueError, 'review_target_mismatch'):
                    state.accept('reviewer_1', bad)
                state.accept('reviewer_1', review(paper, state.evidence, verdict='revise', issues=[issue]))
                first = {**copy.deepcopy(paper), 'response_to_review':
                         [{'issue_index': 0, 'change': 'Reworded the sentence.'}]}
                state.accept('reviser_1', first)
                state.accept('reviewer_2', review(first, state.evidence, verdict='revise', issues=[issue]))
                second = {**copy.deepcopy(first), 'response_to_review':
                          [{'issue_index': 0, 'change': 'Clarified the same point.'}]}
                state.accept('reviser_2', second)
                state.accept('reviewer_3', review(second, state.evidence, verdict='pass'))
            self.assertIsNone(state.expected_next())
            self.assertEqual(state.current_paper(), second)
            self.assertEqual(len(state.review_history()), 3)
            summary = paper_summary(state, {'mode': 'live', 'model_calls': 6, 'total_tokens': 123},
                                    {'pages': 8}, {'findings': []}, resumed=False)
            self.assertTrue(summary['ready_for_external_review'])
            self.assertFalse(summary['submission_ready'])
            self.assertEqual(summary['review_rounds'], 3)

    def test_inherited_literature_requires_saved_hash_and_primary_text(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = {'id': 'arxiv:2604.16706v1', 'verification_status': 'primary_fulltext',
                      'primary_text_excerpt': 'x' * 4000}
            sources = {f'arxiv:2604.{n:05d}v1': {**source, 'id': f'arxiv:2604.{n:05d}v1'}
                       for n in range(6)}
            manifest = {'sources': sources}
            (root / 'sources.json').write_text(json.dumps(sources))
            (root / 'literature_manifest.json').write_text(json.dumps(manifest))
            (root / 'input_provenance.json').write_text(json.dumps(
                {'sources_sha256': digest(sources), 'literature_manifest_sha256': digest(manifest)}))
            self.assertEqual(loop.verified_inherited_literature(root), manifest)
            sources.pop(next(iter(sources)))
            (root / 'sources.json').write_text(json.dumps(sources))
            with self.assertRaisesRegex(ValueError, 'changed'):
                loop.verified_inherited_literature(root)

    def test_review_cap_does_not_mark_unresolved_paper_ready(self):
        with tempfile.TemporaryDirectory() as name:
            state = loop.LoopState.__new__(loop.LoopState)
            state.root = Path(name); state.outputs = {}; state.evidence = {'fixed': True}; state.sources = {}
            paper = manuscript(); state.previous = paper
            with patch.object(loop, 'validate_publication'):
                state.accept('writer', paper)
                state.accept('reviewer_1', review(paper, state.evidence, verdict='pass'))
                state.accept('reviewer_2', review(paper, state.evidence, verdict='revise'))
                revised = {**copy.deepcopy(paper), 'response_to_review': []}
                state.accept('reviser_2', revised)
                state.accept('reviewer_3', review(revised, state.evidence, verdict='revise'))
            self.assertIsNone(state.expected_next())
            summary = paper_summary(state, {'mode': 'live', 'model_calls': 5, 'total_tokens': 123},
                                    {'pages': 6}, {'findings': []}, resumed=False)
            self.assertEqual(summary['status'], 'needs_more_revision')
            self.assertFalse(summary['ready_for_external_review'])

    def test_mechanical_citation_defect_forces_model_revision_without_editing_paper(self):
        with tempfile.TemporaryDirectory() as name:
            state = loop.LoopState.__new__(loop.LoopState)
            state.root = Path(name); state.outputs = {}; state.evidence = {'fixed': True}
            identifier = 'arxiv:2607.11098v1'
            state.sources = {identifier: {'authors': ['First Author', 'Second Author']}}
            paper = manuscript()
            paper['sections'][1]['text'] = f'[[citet:{identifier}]] presents a method.'
            paper['sections'][1]['source_ids'] = [identifier]
            state.previous = paper
            with patch.object(loop, 'validate_publication'):
                state.accept('writer', paper)
                model_review = review(paper, state.evidence, verdict='pass')
                state.accept('reviewer_1', model_review)
                self.assertEqual(state.expected_next(), 'reviser_1')
                self.assertEqual(state.workflow_response('reviewer_1', model_review)['verdict'], 'revise')
                self.assertEqual(state.current_paper(), paper)
                self.assertEqual(json.loads((state.root / 'reviewer_1_model.json').read_text()), model_review)
                self.assertEqual(len(state.outputs['reviewer_1']['issues']), 1)
                self.assertEqual(state.review_controls['reviewer_1']['model_verdict'], 'pass')
                self.assertEqual(len(state.review_controls['reviewer_1']['mechanical_issues']), 1)
                self.assertEqual(state.outputs['reviewer_1']['issue_quotes'],
                                 [f'[[citet:{identifier}]] presents'])
                revised = copy.deepcopy(paper)
                revised['sections'][1]['text'] = f'[[citet:{identifier}]] present a method.'
                revised['response_to_review'] = [{'issue_index': 0, 'change': 'Changed to plural verb.'}]
                state.accept('reviser_1', revised)
                self.assertEqual(state.expected_next(), 'reviewer_2')
                state.accept('reviewer_2', review(revised, state.evidence, verdict='pass'))
            self.assertIsNone(state.expected_next())
            self.assertFalse(state._text_findings(state.current_paper()))

    def test_followup_starts_from_bound_final_review(self):
        with tempfile.TemporaryDirectory() as name:
            source, output = Path(name) / 'source', Path(name) / 'output'
            source.mkdir(); output.mkdir()
            paper = manuscript()
            issue = {'severity': 'minor', 'section_id': 'introduction',
                     'message': 'Clarify the anchored claim.'}
            bound = review(paper, {'fixed': True}, verdict='revise', issues=[issue])
            (source / 'summary.json').write_text(json.dumps({
                'status': 'needs_more_revision', 'final_internal_review': 'revise',
                'role_sequence': ['writer', 'reviewer_3']}))
            (source / 'reviewer_3.json').write_text(json.dumps(bound))
            (source / 'reviewer_3_control.json').write_text(json.dumps({
                'draft_sha256': digest(paper), 'mechanical_issues': [], 'model_verdict': 'revise'}))
            def seed(state, root, source_run, *, live):
                state.root = root; state.outputs = {}; state.previous = paper
                state.evidence = {'fixed': True}; state.sources = {}; state.science = {}
                state.prior_quality = {'findings': []}; state.review_controls = {}
                state.provenance = {}; state.profile_hash = loop.loop_profile_digest()
            with patch.object(loop.LoopState, '__init__', seed):
                state = loop.FollowupState(output, source, live=False)
            self.assertEqual(state.expected_next(), 'reviser_0')
            self.assertEqual(state.current_paper(), paper)
            self.assertEqual(state.latest_review(), bound)
            self.assertEqual(state.review_history()[0]['round'], 0)
            revised = copy.deepcopy(paper)
            revised['sections'][0]['text'] = 'A clarified claim.'
            revised['response_to_review'] = [{'issue_index': 0, 'change': 'Clarified the claim.'}]
            with patch.object(loop, 'validate_publication'):
                state.accept('reviser_0', revised)
            self.assertEqual(state.expected_next(), 'reviewer_1')
            self.assertEqual(state.current_paper(), revised)

    def test_native_workflow_uses_bounded_review_branches(self):
        path = loop.SKILL / 'scripts/workflow.py'
        spec = importlib.util.spec_from_file_location('publication_loop_workflow_test', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'swarmflow': SimpleNamespace(agent=lambda *args, **kwargs: None,
                                                               phase=lambda *args: None)}):
            spec.loader.exec_module(module)
        for verdicts, expected in [(['pass', 'pass'], ['writer', 'reviewer_1', 'reviewer_2']),
                                   (['revise', 'revise', 'pass'],
                                    ['writer', 'reviewer_1', 'reviser_1', 'reviewer_2', 'reviser_2', 'reviewer_3'])]:
            calls = []
            async def agent(_prompt, *, label, options):
                calls.append(label)
                if label.startswith('reviewer_'):
                    return json.dumps({'verdict': verdicts[int(label[-1]) - 1], 'issues': []})
                return '{}'
            with self.subTest(verdicts=verdicts), patch.object(module, 'agent', agent), patch.object(module, 'phase'):
                asyncio.run(module.run({}))
                self.assertEqual(calls, expected)
        calls = []
        async def followup_agent(_prompt, *, label, options):
            calls.append(options['agent_type'])
            return json.dumps({'verdict': 'pass', 'issues': []}) if label.startswith('reviewer_') else '{}'
        with patch.object(module, 'agent', followup_agent), patch.object(module, 'phase'):
            asyncio.run(module.run({'initial_role': 'reviser_0'}))
        self.assertEqual(calls, ['reviser_0', 'reviewer_1', 'reviewer_2'])


if __name__ == '__main__':
    unittest.main()
