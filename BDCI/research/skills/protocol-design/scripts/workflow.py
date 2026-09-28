from swarmflow import agent, phase

META = {'name': 'protocol-design', 'description': 'Operationalize and audit a research proposal',
        'phases': ['Design', 'Audit'], 'workflow_token_limit': 100000}


async def run(args):
    results = {}
    for name, role in [('Design', 'designer'), ('Audit', 'auditor')]:
        phase(name)
        result = await agent('Return the requested protocol JSON.', label=role,
                             options={'agent_type': role, 'timeout': 100})
        if not result:
            raise RuntimeError('missing_protocol_response')
        results[role] = result
    return results
