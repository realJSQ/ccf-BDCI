from swarmflow import agent, phase

META = {
    "name": "research-smoke",
    "description": "Bounded experiment and report verification; not novel research.",
    "phases": ["Experiment", "Write"],
    "workflow_token_limit": 12000,
}


async def run(args):
    phase("Experiment")
    experiment = await agent(
        "Run the fixed queue experiment now using run_queue_experiment exactly once. "
        "Then briefly confirm what the tool actually returned.",
        label="experimenter",
        options={"agent_type": "experimenter", "timeout": 100},
    )
    if not experiment:
        raise RuntimeError("Experimenter did not complete")
    # The role router independently verifies the receipt before admitting writer.
    phase("Write")
    report = await agent(
        "Write the English smoke-test explanation using the verified evidence "
        "in your role context. Clearly disclose the simulation and its limitations.",
        label="writer",
        options={"agent_type": "writer", "timeout": 100},
    )
    if not report:
        raise RuntimeError("Writer did not complete")
    return {"experimenter": experiment, "report": report}
