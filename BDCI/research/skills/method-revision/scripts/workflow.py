from swarmflow import agent, phase

META = {
    'name': 'method-revision',
    'description': 'Grounded candidate revision, critique and development handoff',
    'phases': ['Propose', 'Critique', 'Refine'],
    'workflow_token_limit': 100000,
}


async def run(args):
    results = {}
    for phase_name, role in [('Propose', 'proposer'), ('Critique', 'critic'), ('Refine', 'refiner')]:
        phase(phase_name)
        result = await agent('Execute the supplied role and return the required JSON.',
                             label=role, options={'agent_type': role, 'timeout': 100})
        if not result:
            raise RuntimeError('missing_revision_role_response')
        results[role] = result
    return results
