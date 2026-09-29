from swarmflow import agent, phase

META = {'name': 'followup-design', 'description': 'Design and audit follow-up research',
        'phases': ['Design', 'Audit'], 'workflow_token_limit': 100000}


async def run(args):
    results = {}
    for name, role in [('Design', 'designer'), ('Audit', 'auditor')]:
        phase(name)
        result = await agent('Return the required JSON.', label=role,
                             options={'agent_type': role, 'timeout': 110})
        if not result:
            raise RuntimeError('missing_followup_response')
        results[role] = result
    return results
