from swarmflow import agent, phase

META = {
    "name": "topic-discovery", "description": "Evidence-grounded pilot planning, not novelty proof.",
    "phases": ["Search", "Propose", "Critique"], "workflow_token_limit": 20000,
}


async def run(args):
    phase("Search")
    planner = await agent("Plan the literature search under the supplied constraints.",
                          label="planner", options={"agent_type": "planner", "timeout": 100})
    if not planner:
        raise RuntimeError("missing_planner")
    phase("Propose")
    proposer = await agent("Propose grounded questions and bounded pilot plans.",
                           label="proposer", options={"agent_type": "proposer", "timeout": 100})
    if not proposer:
        raise RuntimeError("missing_proposer")
    phase("Critique")
    critic = await agent("Challenge every candidate using all retrieved evidence.",
                         label="critic", options={"agent_type": "critic", "timeout": 100})
    if not critic:
        raise RuntimeError("missing_critic")
    return {"planner": planner, "proposer": proposer, "critic": critic}
