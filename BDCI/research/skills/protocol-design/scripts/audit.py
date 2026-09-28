from swarmflow import agent, phase

META = {'name': 'protocol-audit', 'description': 'Audit a saved current protocol',
        'phases': ['Audit'], 'workflow_token_limit': 100000}


async def run(args):
    phase('Audit')
    result = await agent('Audit only the supplied current protocol.', label='auditor',
                         options={'agent_type': 'auditor', 'timeout': 100})
    if not result:
        raise RuntimeError('missing_protocol_audit')
    return result
