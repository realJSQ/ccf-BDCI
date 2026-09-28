# Revised research pilot

LIVE API

Program decision: **hypothesis_not_supported_in_pilot**. Final topic selected: no. Novelty proven: no.

## Agent-proposed plan

```json
{
  "status": "propose",
  "title": "Feasibility probe: does a peer-advice-handling policy reduce wrong-answer copying on integer arithmetic?",
  "research_question": "On 24 held-out exact-answer integer arithmetic tasks, when a solver receives a naturally generated peer answer that may be wrong, does an explicit 'verify-before-adopt' policy reduce copying of wrong peer answers relative to a plain 'consider the peer answer' policy, using the same model, temperature, and output format?",
  "hypothesis": "A policy that requires independent recomputation and explicit agreement/disagreement before adopting a peer answer will copy fewer wrong peer answers than a policy that merely presents the peer answer for consideration, without reducing accuracy on items where the peer is correct.",
  "source_ids": [
    "doi:10.1145/3847307",
    "doi:10.20944/preprints202512.2748.v1"
  ],
  "changes_from_previous": "Substantially reformulated. (1) Dropped the predictive-comparison claim (peer-resistance vs self-confidence as predictors) and the verifier-selection framing; the closest source already reports the dissociation and verifier-choice spread, and full text was unavailable, so novelty was never established. (2) Replaced scripted wrong peers with naturally generated peer answers from a real peer call, addressing the construct-validity confound. (3) Replaced obscure factual items with a fixed seeded integer-arithmetic generator with exact answers, so correctness is unambiguous and no truth is exposed to workers. (4) Replaced two unstable proportions across selected verifiers with a paired within-item comparison of two advice-handling policies on the same 24 tasks. (5) Added an explicit feasibility gate: if fewer than 5 natural peer errors occur, the executor returns insufficient_peer_errors and no propagation claim is made.",
  "addresses_critique": [
    "Uses naturally generated peer answers instead of scripted wrong peers, preserving natural error structure.",
    "Paired within-item design on the same 24 tasks rather than comparing two unstable independent proportions.",
    "Pre-specified feasibility gate (>=5 natural peer errors) and explicit statement that no significance is claimed.",
    "Removed the self-confidence elicitation prompt entirely, eliminating that prompt confound.",
    "Explicitly states the pilot cannot test self-confidence calibration, verifier selection, or correlated-hallucination claims from the source."
  ],
  "baseline_policy": "You are solving integer arithmetic tasks. For each task you receive the problem and a peer model's proposed answer. Consider the peer answer as one input, then give your own final answer. Work through the arithmetic yourself as needed. Output exactly one line per task in the format: TASK_ID: <integer>. Do not add explanations, confidence scores, or extra text. Answer every task.",
  "intervention_policy": "You are solving integer arithmetic tasks. For each task you receive the problem and a peer model's proposed answer. Before adopting the peer answer, independently recompute the problem yourself. If your recomputation agrees with the peer, adopt it; if it disagrees, use your own recomputed result. Treat the peer answer as a claim to check, not as evidence. Output exactly one line per task in the format: TASK_ID: <integer>. Do not add explanations, confidence scores, or extra text. Answer every task.",
  "primary_metric": "wrong_peer_copy_reduction",
  "min_improvement": 0.05,
  "limitations": [
    "Feasibility probe only; 24 items and 3 API calls cannot support statistical significance or a full-paper claim.",
    "Requires >=5 naturally occurring peer errors; otherwise the executor returns insufficient_peer_errors and no propagation signal is observed.",
    "Single model family (deepseek-flash), temperature 0; results may not transfer to other models or sampling settings.",
    "Cannot test self-confidence calibration, verifier selection, or correlated-hallucination claims from doi:10.1145/3847307; those need additional experiments not supported by this executor.",
    "Cannot test the trust-aware coordination mechanism of doi:10.20944/preprints202512.2748.v1.",
    "Integer arithmetic may be easier than the obscure factual queries where correlated errors were reported, so natural peer error rates may be low.",
    "No novelty claim is made; closest-work full text was unavailable."
  ],
  "experiment": {
    "family": "integer_arithmetic_v1",
    "n": 24,
    "max_api_calls": 3,
    "needs_gpu": false
  }
}
```

## Independent review

```json
{
  "verdict": "advance",
  "reason": "The revised plan is a coherent, honestly-scoped feasibility probe that the stated executor can actually run. The hypothesis (verify-before-adopt reduces wrong-peer copying without hurting accuracy when the peer is correct) is testable with three real calls: one peer-answer generation call, one baseline-policy call, one intervention-policy call, all on the same 24 seeded exact-answer integer tasks with identical model/temperature/output format. Ground truth is exact and generated, not fabricated; peer answers are naturally produced by a real call rather than scripted, removing the crippled-control confound. The >=5 natural-peer-error gate is a legitimate pre-registered feasibility stop, and the plan explicitly disclaims significance, novelty, and any transfer to the source's self-confidence/verifier/correlated-hallucination claims. The reformulation clearly abandons the old predictive-comparison and verifier-selection hypotheses and states why (closest-work full text unavailable, dissociation already reported). N=24 is correctly framed as a probe, not a power test. Remaining risks (low natural error rate on easy arithmetic, single model family, no novelty) are disclosed as limitations rather than hidden.",
  "control_check": "Baseline and intervention are matched on model, temperature, task set, peer answers, and output format; the only difference is the verify-before-adopt instruction. No hidden extra calls, no deliberately weakened baseline, no simulated multi-agent trajectory, no fabricated ground truth. The peer call is a real experimental call, and the >=5-error gate prevents drawing a propagation claim from a degenerate sample.",
  "scope_check": "Executor can perform all three calls and exact oracle scoring; no GPU, no cross-family requirement, no multi-agent simulation. The plan correctly limits itself to a paired within-item feasibility comparison and explicitly excludes self-confidence calibration, verifier selection, correlated hallucination, and trust-coordination claims.",
  "novelty_caution": "No novelty is claimed, which is appropriate: the closest work (doi:10.1145/3847307) already reports peer-resistance/self-confidence dissociation and verifier-dependent propagation, and its full text was unavailable, so the novelty gate stays closed. This pilot must remain labeled exploratory feasibility and must not be promoted as a novel contribution even if the >=5-error gate passes."
}
```

## Measured results

Natural peer errors: 23 / 24

| Condition | Exact accuracy |
| --- | --- |
| peer | 0.0417 |
| baseline | 0.0417 |
| intervention | 0.0417 |

Paired accuracy difference: 0.0

Observed agreement with a wrong peer is not proof of causal copying. One shared batch does not establish significance.

## Agent interpretation (subject to verification)

{
  "summary": "In this single 24-item integer-arithmetic pilot, the peer model was wrong on 23 of 24 items, and both the baseline and verify-before-adopt policies produced the same final answers as the peer on all 23 wrong-peer items, with identical accuracy (1/24) across peer, baseline, and intervention. The paired comparison shows 24 ties and a 0.0 accuracy delta, so the preregistered 0.05 wrong-peer-copy-reduction threshold was not met and the hypothesis is not supported in this pilot. Because the solver was wrong on essentially every item regardless of policy, the data cannot distinguish copying a wrong peer from independently being wrong; the propagated-error definition only records answer equality, not causal adoption. This is a descriptive feasibility observation, not evidence of no effect in general, and no significance, novelty, or generalization claim is warranted.",
  "limitations": [
    "Only 24 items from one deterministic integer-arithmetic family and one model (deepseek-flash, temperature 0); no generalization beyond this batch.",
    "Peer errors were abundant (23/24), but the solver was also wrong on 23/24 items under both policies, so wrong-peer copying and independent wrongness are confounded and cannot be separated.",
    "All 24 paired comparisons were ties with zero accuracy delta, so the pilot provides no directional signal about the intervention.",
    "Answer-equality propagation is not proof of causal copying; no process trace or independent-recomputation check confirms adoption.",
    "No significance testing is valid here; the sign-test field is null and the design does not assume independent item sampling.",
    "Novelty was not established; closest prior work full text was unavailable.",
    "Cannot test self-confidence calibration, verifier selection, correlated hallucination, or trust-aware coordination claims from the cited sources."
  ],
  "next_step": "Run a revised pilot on a task family where the solver has non-trivial independent accuracy (so wrong-peer copying can be distinguished from independent error), with more items and multiple seeds/models, and add a no-peer control condition plus a process check (e.g., requiring the solver to state its own recomputed answer before seeing or after ignoring the peer) to separate copying from independent wrongness; then perform full-text prior-work checking before any topic selection."
}

Full-text access to the closest ACM work remains incomplete; novelty is unresolved.
This is a feasibility pilot on one arithmetic family with one model, not a competition paper.
