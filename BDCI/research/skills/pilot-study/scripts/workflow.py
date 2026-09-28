import json
from swarmflow import agent, phase

META = {'name':'pilot-study', 'description':'Critique-driven preregistered paired pilot',
        'phases':['Revise','Review','Experiment','Interpret'], 'workflow_token_limit':30000}


async def call(role):
    result = await agent('Execute your role using the supplied data and bounds.',
                         label=role, options={'agent_type':role,'timeout':100})
    if not result:
        raise RuntimeError('missing_pilot_role_result')
    return json.loads(result)


async def run(args):
    phase('Revise')
    plan = await call('designer')
    if plan.get('status') != 'propose':
        return {'status':'designer_declined'}
    phase('Review')
    review = await call('critic')
    if review.get('verdict') != 'advance':
        return {'status':'needs_revision'}
    phase('Experiment')
    await call('peer')
    await call('baseline')
    await call('intervention')
    phase('Interpret')
    await call('analyst')
    return {'status':'pilot_completed'}
