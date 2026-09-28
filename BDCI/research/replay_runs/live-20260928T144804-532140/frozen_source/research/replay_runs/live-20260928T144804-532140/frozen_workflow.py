from swarmflow import agent, phase
META = {"name":"recovery-replay", "description":"Paired CPU recovery replay", "phases":["Recover"], "workflow_token_limit":100000}
async def run(args):
    phase("Recover")
    outputs = {}
    for role in ('episode_00', 'episode_01', 'episode_02', 'episode_03', 'episode_04', 'episode_05', 'episode_06', 'episode_07', 'episode_08', 'episode_09', 'episode_10', 'episode_11', 'episode_12', 'episode_13', 'episode_14', 'episode_15', 'episode_16', 'episode_17'):
        outputs[role] = await agent("Produce the bounded recovery plan.", label=role, options={"agent_type":role,"timeout":100})
        if not outputs[role]:
            raise RuntimeError("missing_recovery_plan")
    return outputs
