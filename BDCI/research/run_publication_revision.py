"""Publication-oriented revision; immutable old manuscripts, explicit paid execution."""
import argparse
import asyncio
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from native_runner import native_run
from paper_contracts import SECTION_IDS
from replay_paper_evidence import digest
from run_replay_paper import ReplayPaperState, compile_pdf, select_study_run
from run_topics import write_json
from study_adapter import get_adapter

HERE = Path(__file__).resolve().parent
SKILL = HERE / 'skills/publication-paper'
PLAN_AUDIT = HERE.parent / 'docs/submission/publication-plan-audit'
MARKER = re.compile(r'\[\[(cite|citet):(arxiv:[0-9.]+v[0-9]+)\]\]')
LITERATURE_SEARCHES = (
    {'id': 'arxiv:2607.11098v1',
     'title': 'AgentCheck: A Reproduce-Intervene-Mitigate Workbench for LLM Agents over MCP',
     'query': 'AgentCheck Reproduce Intervene Mitigate Workbench LLM Agents MCP', 'selected': True},
    {'id': 'arxiv:2608.12761v1',
     'title': 'Correct Is Not Governed: Provenance Integrity in Agentic Workflows',
     'query': 'Correct Is Not Governed Provenance Integrity Agentic Workflows', 'selected': True},
    {'id': 'arxiv:2604.16706v1',
     'title': 'Evaluating Tool-Using Language Agents: Judge Reliability, Propagation Cascades, and Runtime Mitigation in AgentProp-Bench',
     'query': 'AgentProp-Bench Judge Reliability Propagation Cascades Runtime Mitigation', 'selected': True},
    {'id': 'arxiv:2608.10502v1',
     'title': 'From Faulty Memories to Corrected Actions: Dependency-Guided Rollback Repair for Memory-Augmented Agents',
     'query': 'dependency guided rollback repair memory augmented agents', 'selected': True},
    {'id': 'arxiv:2609.00243v1',
     'title': 'Invalidation Contracts for Cross-Episode Agent Memory',
     'query': 'invalidation contracts cross episode agent memory', 'selected': True},
    {'id': 'arxiv:2311.02384v1',
     'title': 'The Case of Transparent Cache Invalidation in Web Applications',
     'query': 'transparent cache invalidation web applications', 'selected': True},
)


def profile_digest():
    paths = [PLAN_AUDIT / 'audit_plans.py', Path(__file__), HERE / 'publication_render.py', HERE / 'publication_quality.py', HERE / 'native_runner.py',
             HERE / 'paper_contracts.py', HERE / 'run_replay_paper.py', HERE / 'study_adapter.py',
             *sorted(SKILL.rglob('*.md')), *sorted(SKILL.rglob('*.py'))]
    openalex = HERE / 'openalex_literature.py'
    if openalex.exists():
        paths.append(openalex)
    return digest({os.path.relpath(p, HERE): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def publication_request_ledger(root):
    return Path(root) / 'publication-paper-requests.jsonl'


def validate_inline_citations(paper, sources):
    for field in ('title', 'abstract'):
        if '[[' in paper[field] or ']]' in paper[field]:
            raise ValueError('citation_not_allowed_in_title_or_abstract')
    for section in paper['sections']:
        text = section['text']
        ids = {match[1] for match in MARKER.findall(text)}
        remaining = MARKER.sub('', text)
        if '[[' in remaining or ']]' in remaining:
            raise ValueError('malformed_inline_citation')
        if ids != set(section['source_ids']) or not ids <= sources.keys():
            raise ValueError('inline_citation_source_mismatch')


def scientific_context(evidence):
    """Allowlist scientific content; provenance remains separately archived."""
    keys = ('base_instance_count', 'completed_model_plans', 'completed_policy_replays',
            'paired_model_policy_replays', 'deterministic_g_replays', 'policies', 'scenarios',
            'summary_by_scenario_policy', 'summary_by_policy', 'freshness_by_policy',
            'task_generation_notes', 'source_intervention_notes', 'tool_contracts_by_topology',
            'information_condition')
    data = {key: copy.deepcopy(evidence[key]) for key in keys}
    data['paired_instances'] = [{k: copy.deepcopy(v) for k, v in row.items() if k != 'case_id'}
                                for row in evidence['paired_base_instances']]
    data['protocol'] = {k: copy.deepcopy(evidence['protocol'][k]) for k in
                       ('model', 'temperature', 'reasoning', 'independent_unit', 'primary_comparison', 'strong_baseline')}
    data['study_resources'] = copy.deepcopy(evidence['resource'])
    data['interpretation'] = {
        'split': 'Nine development instances and nine structural held-out instances; three families crossed with three layouts per split. Only held-out results are reported.',
        'comparison': 'E minus A isolates the added closure guard on the SAME model plan. A versus G or E versus G compares model-based policies with a no-model baseline.',
        'invariants': 'D and E union the model-requested nodes with their respective forward closures. E uses actual graph; D uses declared graph. Actual contracts are supplied to the planner. A/D/E/F honor model refusal or malformed plans; G does not require a model plan. E tool count >= G only applies to valid completed emit plans, not refused/invalid plans.',
        'conclusions': 'All five policies achieve 36/36 correctness. A/D/E/G use 294 calls each; F uses 414. No observed incremental guard or model benefit; no equivalence or broad generalization claim. Full replay savings are not specific to E.',
        'limitations': 'Self-authored small structural holdout with deterministic source generation; local freeze, not public preregistration. Separate numerical reference implementation by the same authors, not external validation. Freshness is evaluated separately from numerical correctness. Repeated scenarios/policies are not independent samples.',
        'implementation': 'JiuwenSwarm orchestrates model roles; local Python executes CPU replay. Developer assistance designed and revised the protocol. No new closure algorithm is proposed.'}
    return data


def verified_plan_analysis(study_run):
    """Recompute archived post-hoc analysis in an isolated interpreter, no API."""
    with tempfile.TemporaryDirectory(prefix='publication-plan-audit-') as folder:
        output = Path(folder) / 'analysis.json'
        result = subprocess.run([sys.executable, str(PLAN_AUDIT / 'audit_plans.py'),
                                 '--run', str(study_run), '--output', str(output)],
                                capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise ValueError('posthoc_plan_analysis_recomputation_failed')
        analysis = json.loads(output.read_text())
    archived = json.loads((PLAN_AUDIT / 'analysis.json').read_text())
    if analysis != archived:
        raise ValueError('posthoc_plan_analysis_archive_mismatch')
    return analysis


def plan_analysis_context(analysis):
    """Retain scientific observations and concrete examples, not local bookkeeping."""
    keys = ('scope', 'summary', 'interpretation_limits', 'topology_scenario_representatives',
            'action_sequence_groups')
    result = {key: copy.deepcopy(analysis[key]) for key in keys}
    result['noncanonical_order_examples'] = [copy.deepcopy(row) for row in analysis['episodes']
                                           if not row['requested_order_equals_actual_closure_order']]
    result['reporting_requirement'] = (
        'This is a post-hoc descriptive analysis of already saved model plans, with zero new '
        'model calls and no new scientific trials. Explicitly identify it as post-hoc if reported. '
        'Matching node sets does not imply identical node order: preserve the noncanonical '
        'but topological ordering example. Repeated signatures are not independent samples. '
        'Episode identifiers identify archived examples, not prose titles or local paths.')
    return result


def checked_sources(original):
    result = copy.deepcopy(original)
    for source in result.values():
        source['authors'] = [author.replace('Nusrat jahan Lia', 'Nusrat Jahan Lia') for author in source['authors']]
    return result


def upgrade_verified_sources(original, manifest):
    """Replace legacy reading notes with primary-version evidence by exact ID."""
    result = checked_sources(original)
    found = manifest.get('sources')
    if not isinstance(found, dict) or not found:
        raise ValueError('no_verified_openalex_sources')
    if not set(result) <= set(found):
        raise ValueError('legacy_sources_require_primary_text_upgrade')
    for source_id, source in found.items():
        if (not isinstance(source, dict) or source.get('id') != source_id
                or source.get('evidence_kind') != 'retrieved'
                or source.get('verification_status') != 'primary_fulltext'
                or not isinstance(source.get('primary_text_excerpt'), str)
                or len(source['primary_text_excerpt']) < 4000):
            raise ValueError('unverified_openalex_source')
        if source_id in result and result[source_id].get('url') != source.get('url'):
            raise ValueError('legacy_primary_version_mismatch')
        result[source_id] = copy.deepcopy(source)
    return result


SOURCE_GUIDANCE = {
    'arxiv:2607.11098v1': 'AgentCheck: cached tool-response intervention and reproduce-intervene-mitigate workbench, sections 4.1, 5.3, 6. This study does not reproduce its baselines. Do not assert globally that it is not a published baseline.',
    'arxiv:2608.12761v1': 'Salas: provenance integrity is relevant context. The older reading note asserted specific transitive recovery and full-rerun claims that the preceding draft could not substantiate; cite such a claim only if its exact proposition appears in the versioned primary excerpt. Do not attribute graph closure or a specific recovery procedure by analogy.',
    'arxiv:2604.16706v1': 'AgentProp-Bench: simulated-tool propagation and runtime mitigation, sections 4.3, 4.4, 5.4. Judge validation is not the same construct as cache freshness; do not make this strong analogy.',
    'arxiv:2603.27775v1': 'Enzyme: production incremental view maintenance uses operator-level delta plans and cost-based refresh selection. It is substantially broader than supplied static dependency closure; do not compare performance numbers to this study.',
    'arxiv:2105.06712v1': 'Parallel self-adjusting computation tracks control and data dependencies and propagates updates. Our study assumes executor dependencies are supplied; do not claim to implement that tracking or its parallel algorithms.',
    'arxiv:2404.13295v1': 'EChecker investigates missing and redundant build dependencies and infers actual build dependencies for incremental builds. Our experiment supplies actual contracts and tests recovery policies, not dependency discovery.'}


class PublicationState(ReplayPaperState):
    def __init__(self, root, source_run, live=False, literature_manifest=None):
        self.root, self.live, self.outputs = Path(root), live, {}
        self.adapter = get_adapter('recovery_v2')
        source_run = Path(source_run).resolve()
        provenance = json.loads((source_run / 'input_provenance.json').read_text())
        study_run = select_study_run(saved=provenance)
        self.evidence = self.adapter.build_evidence(study_run)
        saved_evidence = json.loads((source_run / 'evidence.json').read_text())
        original_sources = json.loads((source_run / 'sources.json').read_text())
        if (digest(self.evidence) != digest(saved_evidence)
                or digest(saved_evidence) != provenance['evidence_sha256']
                or digest(original_sources) != provenance['sources_sha256']):
            raise ValueError('source_evidence_changed')
        self.sources = checked_sources(original_sources)
        self.literature_manifest = literature_manifest
        if literature_manifest is not None:
            self.sources = upgrade_verified_sources(original_sources, literature_manifest)
        self.previous = json.loads((source_run / 'paper.json').read_text())
        self.external_review = None
        external_path = self.root / 'external_review.json'
        if external_path.exists():
            external = json.loads(external_path.read_text())
            if (external.get('schema') != 'bound_external_review/1'
                    or external.get('source_pdf_sha256') != hashlib.sha256(
                        (source_run / 'paper.pdf').read_bytes()).hexdigest()
                    or external.get('service') != 'paperreview.ai'
                    or not isinstance(external.get('sections'), dict)):
                raise ValueError('external_review_source_mismatch')
            self.external_review = external
        self.posthoc_plan_analysis = verified_plan_analysis(study_run)
        self.science = scientific_context(self.evidence)
        self.science['posthoc_plan_analysis'] = plan_analysis_context(self.posthoc_plan_analysis)
        self.profile_hash = profile_digest()
        self.provenance = {'schema': 'publication_revision/1', 'study_kind': 'recovery_v2',
            'source_run_relative': str(source_run.relative_to(HERE)),
            'study_run_relative': provenance['study_run_relative'],
            'source_paper_sha256': digest(self.previous), 'evidence_sha256': digest(self.evidence),
            'original_sources_sha256': digest(original_sources), 'sources_sha256': digest(self.sources),
            'posthoc_plan_analysis_sha256': digest(self.posthoc_plan_analysis),
            'scientific_context_sha256': digest(self.science), 'profile_sha256': self.profile_hash,
            'new_scientific_model_calls': 0, 'external_review_token_reused': False}
        if literature_manifest is not None:
            self.provenance['literature_manifest_sha256'] = digest(literature_manifest)
        if self.external_review is not None:
            self.provenance['external_review_sha256'] = digest(self.external_review)

    def prompt(self, role):
        if profile_digest() != self.profile_hash:
            raise ValueError('publication_profile_changed')
        data = {'scientific_context': self.science, 'sources': self.sources,
                'source_claim_guidance': SOURCE_GUIDANCE, 'evidence_sha256': digest(self.evidence)}
        if self.literature_manifest is not None:
            data['openalex_discovery'] = {
                'selected_verified_ids': sorted(self.literature_manifest['sources']),
                'discovery_count': len(self.literature_manifest.get('discovered', [])),
                'method': 'OpenAlex discovery and metadata, followed by versioned primary full-text acquisition; indexed abstracts alone are not claim-level evidence.'}
        if self.external_review is not None:
            data['external_review_of_previous_pdf'] = self.external_review
        if role == 'writer':
            data['previous_draft_for_criticism_not_imitation'] = self.previous
        else:
            data.update(current_draft=self.outputs['writer'], draft_sha256=digest(self.outputs['writer']))
        if role == 'reviser':
            data['internal_review'] = self.outputs['reviewer']
        return (SKILL / 'roles' / f'{role}.md').read_text() + '\nCURRENT_DATA_JSON\n' + json.dumps(data, ensure_ascii=False)

    def accept(self, role, value):
        if role != 'reviewer':
            from publication_render import validate_publication
            validate_publication(value, self.sources, self.evidence)
            validate_inline_citations(value, self.sources)
        super().accept(role, value)

    def archive_inputs(self):
        for name, value in [('evidence', self.evidence), ('sources', self.sources),
                            ('scientific_context', self.science), ('source_paper', self.previous),
                            ('input_provenance', self.provenance),
                            ('posthoc_plan_analysis', self.posthoc_plan_analysis)]:
            write_json(self.root / f'{name}.json', value)
        if self.literature_manifest is not None:
            write_json(self.root / 'literature_manifest.json', self.literature_manifest)
        (self.root / 'prompt_writer.txt').write_text(self.prompt('writer'))
        for role in ('reviewer', 'reviser'):
            (self.root / f'prompt_{role}_template.txt').write_text((SKILL / 'roles' / f'{role}.md').read_text())
        write_json(self.root / 'prepared.json', {'input_sha256': digest(self.provenance),
            'dependent_prompts': 'Reviewer/reviser receive the saved writer output and, for reviser, its anchored review at execution time.',
            'planned_calls': 3, 'token_stop': None, 'status': 'prepared'})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run', type=Path)
    parser.add_argument('--output-run', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare-only', action='store_true')
    mode.add_argument('--live', action='store_true')
    mode.add_argument('--resume', type=Path, help='Revalidate all saved responses and compile; zero API calls')
    parser.add_argument('--openalex', action='store_true', help='Search OpenAlex and read versioned primary texts before preparing prompts')
    args = parser.parse_args(argv)
    root = (args.resume or args.output_run)
    if root is None:
        parser.error('--output-run or --resume is required')
    root = root.resolve()
    if root.parent != (HERE / 'replay_paper_runs').resolve():
        raise ValueError('invalid_publication_run_location')
    if args.resume and args.output_run:
        raise ValueError('conflicting_output_locations')
    source = args.source_run
    if source is None and root.exists():
        source = HERE / json.loads((root / 'input_provenance.json').read_text())['source_run_relative']
    if source is None:
        parser.error('--source-run is required for a new run')
    existed = (root / 'prepared.json').exists()
    if args.openalex and (args.live or args.resume):
        raise ValueError('openalex_search_only_during_preparation')
    literature = None
    if args.openalex:
        if root.exists():
            raise ValueError('openalex_preparation_requires_new_run')
        root.mkdir(parents=True, exist_ok=False)
        from openalex_literature import build_literature
        literature = build_literature(root / 'openalex', HERE.parent / 'search_api.txt', LITERATURE_SEARCHES)
    elif (root / 'literature_manifest.json').exists():
        literature = json.loads((root / 'literature_manifest.json').read_text())
    state = (PublicationState(root, source, live=args.live, literature_manifest=literature)
             if literature is not None else PublicationState(root, source, live=args.live))
    if existed:
        saved = json.loads((root / 'prepared.json').read_text())
        if saved['input_sha256'] != digest(state.provenance):
            raise ValueError('prepared_publication_inputs_changed')
        if not args.resume and (not args.live or any(root.glob('raw_*'))
                or (root / 'live_started.json').exists() or (root / 'model_summary.json').exists()):
            raise ValueError('existing_run_cannot_be_resent')
    else:
        if args.resume or args.live:
            raise ValueError('prepare_run_before_execution')
        root.mkdir(parents=True, exist_ok=True)
        state.archive_inputs()
    if not args.live and not args.resume:
        print(json.dumps({'status': 'prepared', 'output': str(root), 'model_calls': 0}))
        return 0
    os.chdir(root)
    try:
        if args.resume:
            for role in state.roles:
                prompt = state.prompt(role)
                if (root / f'prompt_{role}.txt').read_text() != prompt:
                    raise ValueError('saved_publication_prompt_changed')
                state.accept(role, state.decode_response((root / f'raw_{role}.txt').read_text()))
        else:
            # The budget rail counts admissions over its entire ledger. Keep
            # each frozen publication campaign's three-call budget separate.
            ledger = publication_request_ledger(root)
            with ledger.with_suffix('.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Exclusive creation is the durable no-resend fence, including unknown usage failures.
                with (root / 'live_started.json').open('x') as fence:
                    json.dump({'input_sha256': digest(state.provenance), 'automatic_retry': False}, fence)
                keys = re.findall(r'\bsk-[A-Za-z0-9_-]{16,}\b', (HERE.parent / 'apis.txt').read_text())
                if len(keys) != 1:
                    raise ValueError('expected_one_credential')
                from run_recovery_v2 import provider_output_capacity
                asyncio.run(native_run(root, SKILL / 'scripts/workflow.py', state,
                    live=True, key=keys[0], ledger=ledger, max_calls=3, token_stop=None,
                    timeout=3600, max_output_tokens=provider_output_capacity(), team_name='publication_paper'))
        from publication_render import render_publication
        metering = json.loads((root / 'model_summary.json').read_text())
        paper = state.outputs['reviser']
        write_json(root / 'paper.json', paper)
        rendered = copy.deepcopy(state.evidence)
        rendered['resource'].update(writing_model_calls=metering['model_calls'], writing_total_tokens=metering['total_tokens'])
        tex = render_publication(root, paper, state.sources, rendered)
        pdf = compile_pdf(root, tex, study_kind='recovery_v2')
        from publication_quality import audit_publication
        quality = audit_publication(paper, state.sources, root / 'paper.pdf')
        write_json(root / 'quality_audit.json', quality)
        summary = {'status': 'manuscript_generated', 'mode': metering['mode'], 'study_kind': 'recovery_v2',
            'publication_profile': True, 'pdf': pdf, 'writing_model_calls': metering['model_calls'],
            'writing_total_tokens': metering['total_tokens'], 'new_scientific_model_calls': 0,
            'external_review_completed': False, 'external_review_token_reused': False,
            'semantic_review_certified': False, 'submission_ready': False,
            'quality_finding_codes': [row['code'] for row in quality['findings']],
            'resume_new_model_calls': 0 if args.resume else None}
        write_json(root / 'summary.json', summary)
        print(json.dumps({'output': str(root), **summary}))
        return 0
    except BaseException as error:
        write_json(root / 'failure.json', {'error_type': type(error).__name__,
            'model_summary_available': (root / 'model_summary.json').exists(), 'automatic_retry': False})
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'output': str(root)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
