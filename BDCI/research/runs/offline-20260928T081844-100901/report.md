# Autonomous topic discovery

OFFLINE SYNTHETIC TEST

Decision: eligible_for_pilot. Pilot executed: no. Novelty proven: no.

Abstract-only Crossref coverage is incomplete. Full-text prior-work checks and actual pilots remain required.

## TEST-C1: SYNTHETIC pipeline test, not a research topic

Can the pipeline retain and gate a hypothetical comparison?

Hypothesis: A synthetic placeholder, not a scientific hypothesis.

Tentative difference: No real novelty claim.

Baseline: Synthetic control
Metric: Synthetic count

```json
{
  "kind": "local_python",
  "dataset": "Synthetic contract fixture",
  "steps": [
    "Validate schema only; do not execute a pilot"
  ],
  "max_minutes": 1,
  "max_api_calls": 0,
  "needs_gpu": false
}
```

Critic: {"candidate_id": "TEST-C1", "novelty_concern": "Synthetic only", "verdict": "advance", "reason": "Exercise gate; no live pilot allowed"}

## Deterministic gate

```json
{
  "status": "eligible_for_pilot",
  "eligible_candidate_ids": [
    "TEST-C1"
  ],
  "decisions": [
    {
      "candidate_id": "TEST-C1",
      "status": "eligible_for_pilot",
      "reasons": []
    }
  ],
  "evidence_mode": "synthetic",
  "live_pilot_allowed": false,
  "novelty_proven": false,
  "competition_score": null,
  "limitations": [
    "Abstract-based screening cannot establish novelty.",
    "Eligibility does not validate scientific merit or results.",
    "Pilot budgets are per candidate; execution requires aggregate accounting."
  ]
}
```

## Sources

- synthetic:fixture-1: SYNTHETIC TEST FIXTURE — not a published paper — SYNTHETIC
- synthetic:fixture-2: SYNTHETIC TEST FIXTURE — not a published paper — SYNTHETIC
