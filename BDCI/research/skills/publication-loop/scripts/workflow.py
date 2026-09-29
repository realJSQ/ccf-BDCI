"""Native bounded writer/reviewer/reviser loop."""
import json

from swarmflow import agent, phase

META = {'name': 'publication-loop', 'description': 'Bounded evidence-anchored manuscript review',
        'phases': ['Write or continue revision', 'Review 1', 'Revise 1', 'Review 2', 'Revise 2', 'Review 3']}


async def _call(role, label):
    phase(label)
    value = await agent('Return the requested manuscript role JSON.', label=role,
                        options={'agent_type': role, 'timeout': 3600})
    if not value:
        raise RuntimeError('missing_publication_loop_response')
    return value


async def run(args):
    initial = (args or {}).get('initial_role', 'writer')
    if initial not in ('writer', 'reviser_0'):
        raise ValueError('invalid_publication_initial_role')
    outputs = {initial: await _call(initial, 'Continue revision' if initial == 'reviser_0' else 'Write')}
    for round_number in (1, 2, 3):
        role = f'reviewer_{round_number}'
        raw = await _call(role, f'Review {round_number}')
        outputs[role] = raw
        review = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(review, dict) or review.get('verdict') not in ('pass', 'revise'):
            raise ValueError('invalid_review_control')
        needs_revision = review['verdict'] == 'revise' or bool(review.get('issues'))
        if round_number >= 2 and not needs_revision:
            break
        if round_number == 3:
            break
        if needs_revision:
            role = f'reviser_{round_number}'
            outputs[role] = await _call(role, f'Revise {round_number}')
    return outputs
