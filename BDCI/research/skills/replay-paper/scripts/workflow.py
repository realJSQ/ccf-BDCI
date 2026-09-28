from swarmflow import agent, phase

META = {'name': 'replay-paper', 'description': 'Evidence-bound development study manuscript',
        'phases': ['Write', 'Review', 'Revise'], 'workflow_token_limit': 60000}


async def run(args):
    outputs = {}
    for name, role in [('Write', 'writer'), ('Review', 'reviewer'), ('Revise', 'reviser')]:
        phase(name)
        outputs[role] = await agent('Return the requested manuscript role JSON.', label=role,
                                    options={'agent_type': role, 'timeout': 100})
        if not outputs[role]:
            raise RuntimeError('missing_replay_paper_response')
    return outputs
