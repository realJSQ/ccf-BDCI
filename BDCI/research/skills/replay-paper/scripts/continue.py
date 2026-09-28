from swarmflow import agent, phase

META = {'name': 'replay-paper-continue', 'description': 'Review and revise saved writer output',
        'phases': ['Review', 'Revise'], 'workflow_token_limit': 60000}


async def run(args):
    result = {}
    for name, role in [('Review', 'reviewer'), ('Revise', 'reviser')]:
        phase(name)
        result[role] = await agent('Return the requested manuscript role JSON.', label=role,
                                  options={'agent_type': role, 'timeout': 100})
        if not result[role]:
            raise RuntimeError('missing_continued_role')
    return result
