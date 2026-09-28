---
name: pilot-study
version: 0.1.0
kind: swarm-skill
description: Revise an agent-generated proposal and run a bounded paired exact-answer pilot.
roles:
  - {id: designer, kind: ai_agent, purpose: Revise a falsifiable proposal, tools: [], skills: []}
  - {id: critic, kind: ai_agent, purpose: Check experimental controls and feasibility, tools: [], skills: []}
  - {id: peer, kind: ai_agent, purpose: Generate real peer answers, tools: [], skills: []}
  - {id: baseline, kind: ai_agent, purpose: Solve with baseline policy, tools: [], skills: []}
  - {id: intervention, kind: ai_agent, purpose: Solve with intervention policy, tools: [], skills: []}
  - {id: analyst, kind: ai_agent, purpose: Interpret measured results cautiously, tools: [], skills: []}
---

Use scripts/workflow.py through run_pilot.py. Read bind.md and workflow.md.
The question and policies are proposed by the designer; available experiment
capabilities are fixed and disclosed. No arbitrary code execution or hidden tools.
