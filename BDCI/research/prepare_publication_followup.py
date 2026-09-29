"""Merge verified public literature with a saved manuscript for model-only revision."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from replay_paper_evidence import digest
from run_topics import write_json

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_extension(root):
    root = Path(root).resolve()
    manifest = read(root / 'literature_manifest.json')
    if (manifest.get('schema') != 'openalex_literature/1' or not manifest.get('sources')
            or len(manifest['sources']) > 6):
        raise ValueError('invalid_literature_extension')
    for identifier, source in manifest['sources'].items():
        suffix = identifier.removeprefix('arxiv:')
        primary = root / 'primary_html' / f'{suffix}.html'
        if (source.get('verification_status') != 'primary_fulltext'
                or source.get('id') != identifier
                or source.get('primary', {}).get('html_sha256') != sha(primary)
                or source.get('content_sha256') != hashlib.sha256(json.dumps(
                    {key: value for key, value in source.items() if key != 'content_sha256'},
                    ensure_ascii=False, sort_keys=True).encode()).hexdigest()):
            raise ValueError('literature_extension_source_changed:' + identifier)
    for query in manifest['queries']:
        suffix = query['id'].removeprefix('arxiv:')
        if query.get('response_sha256') != sha(root / 'openalex_raw' / f'{suffix}.json'):
            raise ValueError('literature_extension_search_changed:' + suffix)
        if query.get('primary_status') != 'verified':
            raise ValueError('literature_extension_primary_missing:' + suffix)
    return manifest


def prepare(source_run, extension_run, report, output):
    source_run, extension_run, output = map(lambda p: Path(p).resolve(),
                                            (source_run, extension_run, output))
    if (source_run.parent != (HERE / 'replay_paper_runs').resolve()
            or extension_run.parent != (HERE / 'replay_paper_runs').resolve()
            or output.parent != (HERE / 'replay_paper_runs').resolve()
            or output.exists()):
        raise ValueError('invalid_followup_location')
    provenance = read(source_run / 'input_provenance.json')
    inherited = read(source_run / 'literature_manifest.json')
    if (provenance.get('literature_manifest_sha256') != digest(inherited)
            or inherited['sources'] != read(source_run / 'sources.json')):
        raise ValueError('inherited_literature_changed')
    extension = verify_extension(extension_run)
    overlap = set(inherited['sources']) & set(extension['sources'])
    if overlap:
        raise ValueError('extension_duplicates_existing_sources')
    merged = {**inherited, 'schema': 'openalex_literature/1',
              'sources': {**inherited['sources'], **extension['sources']},
              'queries': [*inherited['queries'], *extension['queries']],
              'discovered': [*inherited['discovered'], *extension['discovered']],
              'extension': {'source_run_relative': str(source_run.relative_to(HERE)),
                            'source_manifest_sha256': digest(inherited),
                            'extension_run_relative': str(extension_run.relative_to(HERE)),
                            'extension_manifest_sha256': digest(extension)}}
    review = read(report)
    if (not review.get('success') or review.get('venue') != 'ICLR'
            or not isinstance(review.get('sections'), dict)):
        raise ValueError('invalid_external_review_report')
    bound_review = {'schema': 'bound_external_review/1', 'service': 'paperreview.ai',
                    'source_pdf_sha256': sha(source_run / 'paper.pdf'),
                    'review_report_sha256': sha(report),
                    'venue': review['venue'], 'numerical_score': review.get('numerical_score'),
                    'sections': review['sections'],
                    'interpretation': 'Criticism of the source PDF, not new scientific evidence or an acceptance decision.'}
    output.mkdir(parents=True)
    write_json(output / 'literature_manifest.json', merged)
    write_json(output / 'external_review.json', bound_review)
    write_json(output / 'literature_merge_provenance.json',
               {'source_paper_sha256': sha(source_run / 'paper.json'),
                'source_pdf_sha256': sha(source_run / 'paper.pdf'),
                'merged_manifest_sha256': digest(merged),
                'external_review_sha256': digest(bound_review),
                'new_scientific_model_calls': 0,
                'new_literature_sources': sorted(extension['sources'])})
    return {'output': str(output), 'source_count': len(merged['sources']),
            'new_sources': sorted(extension['sources']), 'model_calls': 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run', type=Path, required=True)
    parser.add_argument('--extension-run', type=Path, required=True)
    parser.add_argument('--review-report', type=Path, required=True)
    parser.add_argument('--output-run', type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(prepare(args.source_run, args.extension_run,
                             args.review_report, args.output_run), ensure_ascii=False))


if __name__ == '__main__':
    main()
