from swarmflow import agent, phase

META = {'name':'paper-workflow','description':'Reviewed workflow-validation draft from archived evidence',
        'phases':['Draft','Review','Revise'],'workflow_token_limit':30000}

async def run(args):
    results = {}
    for phase_name, role in [('Draft','writer'),('Review','reviewer'),('Revise','reviser')]:
        phase(phase_name)
        result = await agent('Execute the supplied writing-workflow role.',label=role,
                             options={'agent_type':role,'timeout':100})
        if not result:
            raise RuntimeError('missing_paper_workflow_response')
        results[role] = result
    return results
