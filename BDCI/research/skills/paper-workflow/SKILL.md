---
name: paper-workflow
version: 0.1.0
kind: swarm-skill
description: Turn an existing verified pilot into a reviewed workflow-validation draft and ICLR PDF.
roles:
  - {id: writer, kind: ai_agent, purpose: Write a bounded evidence-grounded draft, skills: [], tools: []}
  - {id: reviewer, kind: ai_agent, purpose: Internally review claims and limitations, skills: [], tools: []}
  - {id: reviser, kind: ai_agent, purpose: Revise and respond to each issue, skills: [], tools: []}
---

Run scripts/workflow.py through run_paper.py. Existing experiment evidence is
reused; this skill never schedules new experiments or task-difficulty calibration.
All model text is rendered as escaped text, not executable TeX. Review is internal,
not Stanford Agentic Reviewer. Read bind.md and workflow.md.
