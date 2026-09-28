---
name: research-smoke
version: 0.1.0
description: Validate a bounded research workflow with a real local experiment and an English report. This is a smoke test, not novel scientific research.
kind: swarm-skill
roles:
  - id: experimenter
    kind: ai_agent
    purpose: Execute the fixed local experiment and report its observed result.
    skills: []
    tools: [run_queue_experiment]
  - id: writer
    kind: ai_agent
    purpose: Explain the verified result and its limitations in English.
    skills: []
    tools: []
---

# Research framework smoke test

Use the deterministic workflow in `scripts/workflow.py`. Read `workflow.md`,
`bind.md`, `dependencies.yaml`, and the matching role file before execution.
The local validation runner injects each role file as that worker's instructions.

Success requires an actual experiment receipt, verified metrics, observed Rail
callbacks, a bounded call ledger, an English report, and a compiled PDF.
Do not describe this as a competition submission or a new scheduling method.
