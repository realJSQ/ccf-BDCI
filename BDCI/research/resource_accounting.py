"""Recompute archived live API usage; no provider credentials or model calls."""
import hashlib
import json
from pathlib import Path


def source_path(bdci, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('unsafe_resource_path')
    target = Path(bdci) / path
    if any((Path(bdci) / Path(*path.parts[:i])).is_symlink()
           for i in range(1, len(path.parts) + 1)):
        raise ValueError('unsafe_resource_path')
    return target


def audit_resources(bdci, inventory):
    """Count each listed invocation once, including failed and truncated calls.

    The explicit inventory is a coverage boundary, not proof of all provider
    charges. Summary copies in editorial/resumed directories are not new calls.
    """
    stages, seen_paths, seen_calls = [], set(), set()
    for entry in inventory['runs']:
        usage = source_path(bdci, entry['usage'])
        summary_path = source_path(bdci, entry['summary'])
        if usage in seen_paths or usage.parent != summary_path.parent:
            raise ValueError('duplicate_or_mismatched_resource_run')
        seen_paths.add(usage)
        rows = [json.loads(line) for line in usage.read_text().splitlines() if line.strip()]
        summary = json.loads(summary_path.read_text())
        if summary['mode'] != 'live' or not rows:
            raise ValueError('resource_run_not_live')
        for row in rows:
            if (any(type(row[k]) is not int or row[k] < 0
                    for k in ('input_tokens', 'output_tokens', 'total_tokens'))
                    or row['input_tokens'] + row['output_tokens'] != row['total_tokens']
                    or type(row['call']) is not int or row['call'] < 1):
                raise ValueError('invalid_resource_usage')
            if row.get('mode', 'live') != 'live' or row.get('event', 'usage') != 'usage':
                raise ValueError('resource_usage_not_live')
            identity = (row.get('run_id', str(usage.parent.relative_to(bdci))), row['call'])
            if identity in seen_calls:
                raise ValueError('duplicate_resource_call')
            seen_calls.add(identity)
        total = sum(row['total_tokens'] for row in rows)
        if (summary['model_calls'] != len(rows) or summary['model_usage'] != rows
                or summary.get('total_tokens', total) != total):
            raise ValueError('resource_summary_mismatch')
        stages.append({**entry, 'calls': len(rows),
            **{k: sum(row[k] for row in rows) for k in ('input_tokens', 'output_tokens', 'total_tokens')},
            'recorded_duration_seconds': summary.get('duration_seconds'),
            'usage_sha256': hashlib.sha256(usage.read_bytes()).hexdigest(),
            'summary_sha256': hashlib.sha256(summary_path.read_bytes()).hexdigest()})
    return {'scope': inventory['scope'], 'stages': stages,
        'total_calls': sum(s['calls'] for s in stages),
        'total_tokens': sum(s['total_tokens'] for s in stages),
        'actual_monetary_cost': None, 'wall_clock_end_to_end_seconds': None,
        'limitations': ['Explicit saved-run inventory; not a provider invoice.',
            'Offline fixtures, Codex development, retrieval and external review excluded.',
            'Different stage timing boundaries must not be summed into end-to-end time.',
            'Failed and truncated calls with recorded usage are included.']}


def render_report(audit, study_usage, writing):
    study = next(s for s in audit['stages'] if s['usage'] == study_usage)
    return f'''# Resource report

This packaging operation uses zero model calls.
Selected recovery experiment: {study['calls']} calls / {study['total_tokens']:,} tokens.
Selected manuscript writing: {writing['model_calls']} calls / {writing['total_tokens']:,} tokens.
These stages total {study['calls'] + writing['model_calls']} calls /
{study['total_tokens'] + writing['total_tokens']:,} tokens. Local editorial changes,
CPU replays and post-hoc normalization add zero model calls.

The explicit archived live-run inventory totals {audit['total_calls']} calls /
{audit['total_tokens']:,} tokens, including failed and truncated follow-up design
requests. This is cumulative development usage, not one final submission run.
See resource_audit.json and code/BDCI/research/resource_runs.json for per-run
usage, source hashes and recorded stage durations. Raw usage and summaries are
included in code/BDCI and recomputed by the unpacked bundle verifier.

This inventory excludes offline fixtures, Codex development assistance, retrieval
and external review. Future runs require updating the explicit inventory.
Actual monetary cost and end-to-end wall time remain unknown; recorded stage
durations have different boundaries and are not summed. API usage is not a bill.
The six self-authored study instances are not independent held-out validation.
No GPU training was performed.
'''
