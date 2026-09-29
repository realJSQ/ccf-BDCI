from swarmflow import agent, phase

META = {'name': 'followup-rejected-audit', 'description': 'Audit a rejected truncated proposal',
        'phases': ['Audit'], 'workflow_token_limit': 24000}


async def run(args):
    phase('Audit')
    result = await agent('Audit the exact recovered fields; never promote this rejected input.',
                         label='auditor', options={'agent_type': 'auditor', 'timeout': 110})
    if not result:
        raise RuntimeError('missing_followup_audit_response')
    return {'auditor': result}
