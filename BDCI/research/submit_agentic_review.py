"""Submit one final PDF through paperreview.ai's published upload form flow.

Use only after the exact PDF is frozen. A one-shot fence prevents silent retries.
The returned token is saved locally, never printed or committed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import requests

BASE = 'https://paperreview.ai'


def submit(pdf: Path, output: Path, email: str, venue: str = 'ICLR') -> dict:
    pdf, output = pdf.resolve(), output.resolve()
    if pdf.suffix.lower() != '.pdf' or not pdf.is_file() or pdf.stat().st_size > 10_000_000:
        raise ValueError('invalid_or_oversized_review_pdf')
    if not email or '@' not in email or output.exists() or output.with_suffix('.started').exists():
        raise ValueError('invalid_review_contact_or_existing_attempt')
    pdf_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    fence = output.with_suffix('.started')
    with fence.open('x', encoding='utf-8') as stream:
        json.dump({'pdf_sha256': pdf_hash, 'pdf_bytes': pdf.stat().st_size,
                   'venue': venue, 'automatic_retry': False}, stream)
    session = requests.Session()
    response = session.post(BASE + '/api/get-upload-url',
                            json={'filename': pdf.name, 'venue': venue}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not (payload.get('success') and payload.get('presigned_url')
            and payload.get('s3_key') and isinstance(payload.get('presigned_fields'), dict)):
        raise ValueError('invalid_review_upload_url_response')
    with pdf.open('rb') as stream:
        response = session.post(payload['presigned_url'], data=payload['presigned_fields'],
                                files={'file': (pdf.name, stream, 'application/pdf')}, timeout=120)
    response.raise_for_status()
    response = session.post(BASE + '/api/confirm-upload',
                            data={'s3_key': payload['s3_key'], 'venue': venue, 'email': email},
                            timeout=60)
    response.raise_for_status()
    confirmed = response.json()
    if not confirmed.get('success') or not isinstance(confirmed.get('token'), str) or not confirmed['token']:
        raise ValueError('review_confirmation_without_token')
    record = {'schema': 'final_agentic_review/1', 'pdf_sha256': pdf_hash,
              'venue': venue, 'service': BASE, 'access_token': confirmed['token'],
              'submission_acknowledged': True, 'review_completed': False}
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return {'status': 'submitted', 'pdf_sha256': pdf_hash,
            'record': str(output), 'token_saved': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--email-env', default='PAPER_REVIEW_EMAIL',
                        help='environment variable containing the explicitly authorized contact email')
    parser.add_argument('--contact-authorized', action='store_true',
                        help='affirm that the owner explicitly authorized this contact use')
    args = parser.parse_args(argv)
    if not args.contact_authorized:
        parser.error('explicit contact authorization is required before submission')
    email = os.environ.get(args.email_env, '').strip()
    if not email:
        parser.error('contact email is absent; obtain explicit authorization before setting the environment variable')
    print(json.dumps(submit(args.pdf, args.output, email), ensure_ascii=False))


if __name__ == '__main__':
    main()
