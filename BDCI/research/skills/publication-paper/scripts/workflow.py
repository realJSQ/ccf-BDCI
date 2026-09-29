from swarmflow import agent, phase

META = {'name': 'publication-paper', 'description': 'Evidence-bound publication rewrite',
        'phases': ['Write', 'Review', 'Revise']}


async def run(args):
    outputs = {}
    for name, role in [('Write', 'writer'), ('Review', 'reviewer'), ('Revise', 'reviser')]:
        phase(name)
        outputs[role] = await agent('Return the requested manuscript role JSON.', label=role,
                                    options={'agent_type': role, 'timeout': 3600})
        if not outputs[role]:
            raise RuntimeError('missing_publication_response')
    return outputs
