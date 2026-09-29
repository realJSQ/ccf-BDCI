from swarmflow import agent, phase

META = {'name': 'recovery-v2-paper-continue', 'description': 'Review and revise saved recovery-v2 manuscript',
        'phases': ['Review', 'Revise']}


async def run(args):
    outputs = {}
    for name, role in [('Review', 'reviewer'), ('Revise', 'reviser')]:
        phase(name)
        outputs[role] = await agent('Return the requested manuscript role JSON.', label=role,
                                    options={'agent_type': role, 'timeout': 3600})
        if not outputs[role]:
            raise RuntimeError('missing_continued_recovery_v2_role')
    return outputs
