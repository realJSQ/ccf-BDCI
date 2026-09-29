from swarmflow import agent, phase
META = {"name":"recovery-v2", "description":"Static dependency recovery", "phases":["Plan"]}
async def run(args):
    phase("Plan")
    outputs = {}
    for role in ('episode_00', 'episode_01', 'episode_02', 'episode_03', 'episode_04', 'episode_05', 'episode_06', 'episode_07', 'episode_08', 'episode_09', 'episode_10', 'episode_11', 'episode_12', 'episode_13', 'episode_14', 'episode_15', 'episode_16', 'episode_17', 'episode_18', 'episode_19', 'episode_20', 'episode_21', 'episode_22', 'episode_23', 'episode_24', 'episode_25', 'episode_26', 'episode_27', 'episode_28', 'episode_29', 'episode_30', 'episode_31', 'episode_32', 'episode_33', 'episode_34', 'episode_35'):
        outputs[role] = await agent("Plan recovery.", label=role, options={"agent_type":role,"timeout":180})
    return outputs
