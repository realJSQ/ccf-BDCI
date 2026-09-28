# Autonomous topic discovery

LIVE API + retrieved metadata

Decision: needs_revision. Pilot executed: no. Novelty proven: no.

Abstract-only Crossref coverage is incomplete. Full-text prior-work checks and actual pilots remain required.

## C1: Does peer-resistance predict error propagation better than self-confidence in LLM verifier chains?

When a calibrated LLM verifier is paired with a deliberately-wrong peer output, does its measured peer-resistance (acceptance rate of wrong peers) predict downstream error propagation better than its self-confidence calibration?

Hypothesis: Peer-resistance and self-confidence dissociate; peer-resistance is the stronger predictor of whether a wrong answer survives a two-agent verify step, so a verifier selected on peer-resistance yields lower propagated error than one selected on self-confidence at matched calibration.

Tentative difference: The source reports the dissociation and a 42-point verifier-choice spread but, per the abstract, does not report whether peer-resistance is a better *predictor* of propagation than self-confidence at matched calibration; that predictive comparison and the trust-score framing in the second source require full-text checking.

Baseline: Verifier selected by highest self-confidence calibration (matched control: same model, same prompts, selection rule swapped).
Metric: Propagated-error rate on held-out items (fraction of wrong peer answers accepted and passed downstream), plus rank correlation between each selection signal and propagation.

```json
{
  "kind": "api_eval",
  "dataset": "Construct 40 obscure factual questions with known short answers; split 20 calibration / 20 held-out by fixed seed. Wrong peer outputs are scripted (not model-generated) to control error content.",
  "steps": [
    "One batched API request per model family returns self-confidence (0-100) and accept/reject for 20 calibration items paired with scripted wrong peers; compute peer-resistance and calibration.",
    "Select two verifiers by the two rules, run both on the 20 held-out items in one batched request each, and compare propagated-error rates; report the difference and note that N=20 cannot establish significance."
  ],
  "max_minutes": 20,
  "max_api_calls": 6,
  "needs_gpu": false
}
```

Critic: {"candidate_id": "C1", "novelty_concern": "The closest source (doi:10.1145/3847307) already reports the self-confidence/peer-resistance dissociation, a 42-point verifier-choice spread in error propagation, and identifies verifier choice as the dominant lever; the candidate's only claimed increment is reframing this as a *predictive* comparison (peer-resistance vs self-confidence as predictors of propagation at matched calibration). That is a narrow analytic re-slicing of the same construct, and the abstract does not confirm the predictive comparison is absent — full text is required. The second source (doi:10.20944/preprints202512.2748.v1) is a trust-aware coordination framework with aggregate success/time/overhead metrics, not a verifier-selection predictor study, so it does not establish the gap either.", "verdict": "revise", "reason": "Feasible within budget (2 batched calls, no GPU, 20 min) and has an operational baseline (self-confidence-selected verifier) and metric (propagated-error rate). But the design cannot test the hypothesis: with N=20 held-out items and scripted wrong peers, the propagated-error rate is a coarse proportion with no power to distinguish two selection rules, and the candidate itself concedes a null would not falsify. Worse, scripted wrong peers remove the very correlated-error structure the source identifies as the dominant driver, so peer-resistance measured on scripted errors may not transfer to natural errors — a construct-validity confound, not just a risk. The self-confidence elicitation prompt also plausibly shifts acceptance behavior, confounding the two selection signals. Revise to: (a) use naturally generated wrong peers from a second model family to preserve correlated-error structure, (b) increase held-out N or use a paired within-item design so the comparison is not two unstable proportions, and (c) pre-specify a falsification condition. As written it is a pilot that can run but cannot yield a useful uncertainty."}

## C2: Does a trust-score-weighted role reassignment reduce cascade propagation versus static roles in a 3-agent chain?

In a three-agent LLM pipeline with one injected failing agent, does dynamically reassigning roles using a running trust score reduce cascade propagation to the other agents compared with static role assignment?

Hypothesis: Trust-weighted reassignment contains cascades: the number of turns until a second agent degrades is larger under dynamic reassignment than under static roles, at equal total API budget.

Tentative difference: The drift study documents cascade propagation and compensatory expansion under a trait-mutation perturbation but, per the abstract, does not test a trust-based orchestration countermeasure; the trust framework reports aggregate success/time gains but not cascade-onset turns, which requires full-text checking.

Baseline: Static role assignment with identical agents and the same injected perturbation (matched control).
Metric: Turns until a second agent's output degrades (cascade onset), scored by a fixed rubric on output substance.

```json
{
  "kind": "api_eval",
  "dataset": "Six short multi-turn planning scenarios (5-8 turns) authored locally; one agent is perturbed at a fixed turn by a scripted trait mutation. Two conditions, three scenarios each, fixed seed.",
  "steps": [
    "Run the static-role condition: one batched request per scenario returns all agent turns; score cascade onset with the rubric.",
    "Run the trust-reassignment condition on the same scenarios with the same perturbation; compare onset turns and note that three scenarios per condition cannot support significance."
  ],
  "max_minutes": 20,
  "max_api_calls": 6,
  "needs_gpu": false
}
```

Critic: {"candidate_id": "C2", "novelty_concern": "The drift source (doi:10.2139/ssrn.6420858) already documents cascade propagation and compensatory expansion under a trait-mutation perturbation, and the trust source (doi:10.20944/preprints202512.2748.v1) already reports a trust-score-driven dynamic role-assignment framework with success/time/overhead gains. The candidate's claimed gap — cascade-onset turns as the outcome — is a metric substitution on top of an existing countermeasure, not a new mechanism; the abstract of the trust paper does not confirm cascade-onset turns are unmeasured, so full text is needed. The overlap is substantial: trust-weighted reassignment vs static roles is essentially the trust paper's core comparison.", "verdict": "reject", "reason": "The plan cannot be evaluated as specified. The primary metric — 'turns until a second agent's output degrades' scored by a locally authored rubric — is subjective, has no inter-rater reliability check, and the candidate concedes it may not be reproducible; a non-reproducible metric cannot support a falsifiable claim. With three scenarios per condition and a scripted perturbation, the perturbation likely dominates behavior, masking any orchestration effect, and trust scores over 5-8 turns are too noisy to drive reassignment — so the manipulation may not even be active. The design also lacks a matched-budget control beyond 'same perturbation,' and no operational definition of 'degradation' is given. This is not fixable within 20 minutes and 6 API calls; it needs a validated degradation rubric, more scenarios, and a manipulation check. Reject rather than revise because the core outcome measure is not operational."}

## Deterministic gate

```json
{
  "status": "needs_revision",
  "eligible_candidate_ids": [],
  "decisions": [
    {
      "candidate_id": "C1",
      "status": "needs_revision",
      "reasons": [
        "critic_did_not_advance"
      ]
    },
    {
      "candidate_id": "C2",
      "status": "needs_revision",
      "reasons": [
        "critic_did_not_advance"
      ]
    }
  ],
  "evidence_mode": "live",
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

- doi:10.1145/3847307: When Too Many Cooks Spoil the Broth: Three Failure Modes of Multi-Agent LLM Reliability — https://doi.org/10.1145/3847307
- doi:10.2139/ssrn.7041478: Failure Modes in Production Multi-Agent LLM Systems: Lessons from Real Deployments — https://doi.org/10.2139/ssrn.7041478
- doi:10.2139/ssrn.6420858: Behavioral Drift in Multi-Agent LLM Systems: Emergent Failure Modes, Cascade Dynamics, and Measurement Challenges — https://doi.org/10.2139/ssrn.6420858
- doi:10.2139/ssrn.6368071: Long-Horizon Reliability in Human–LLM Interaction: Observations, Failure Modes, and Limits of Procedural Control — https://doi.org/10.2139/ssrn.6368071
- doi:10.2139/ssrn.6641752: Structural Simulation Benchmark for Reasoning Large Language Models: Accuracy, Reliability, and Failure Modes — https://doi.org/10.2139/ssrn.6641752
- doi:10.2139/ssrn.4918035: Large Language Model-Based Planning Agent with Generative Memory Strengthens Performance in Textualized World — https://doi.org/10.2139/ssrn.4918035
- doi:10.1007/s10994-019-05864-5: Improving coordination in small-scale multi-agent deep reinforcement learning through memory-driven communication — https://doi.org/10.1007/s10994-019-05864-5
- doi:10.20944/preprints202512.2748.v1: Contextual Trust Evaluation for Robust Coordination in Large Language Model Multi-Agent Systems — https://doi.org/10.20944/preprints202512.2748.v1
- doi:10.21203/rs.3.rs-10732437/v1: A Simple and Reproducible Rat Model of Urethral Spongiofibrosis: Evaluation of Colchicine as a Potential Antifibrotic Agent — https://doi.org/10.21203/rs.3.rs-10732437/v1
- doi:10.64898/2026.09.11.751004: From Prompt to Pipeline: A Comparative Evaluation of Large Language Model Coding Agents for Reproducible Bioinformatics Pipeline Construction — https://doi.org/10.64898/2026.09.11.751004
- doi:10.1093/med/9780197509326.003.0006: Confidence Versus Error — https://doi.org/10.1093/med/9780197509326.003.0006
- doi:10.3389/frai.2026.1857934: Confidence-aware pseudo-label selection and verifier training for semi-supervised LLM reasoning with minimal labels — https://doi.org/10.3389/frai.2026.1857934
- doi:10.31224/7995: Executable but Wrong: Verifier-Grounded Contracts and Counterexamples for LLM-Generated Music Programs — https://doi.org/10.31224/7995
- doi:10.31227/osf.io/zfe9y: Student’s Self-Confidence Restoration with Peer Mentoring Strategy — https://doi.org/10.31227/osf.io/zfe9y
- doi:10.2139/ssrn.6947162: A Verifier-Grounded Knowledge-Based LLM Framework with Reinforcement Learning for Reliable NL-to-CTL Specification Generation — https://doi.org/10.2139/ssrn.6947162
- doi:10.22541/au.177499233.37732392/v1: Emergent Misinformation Genesis in Multi-Agent LLM Clinical Pipelines — https://doi.org/10.22541/au.177499233.37732392/v1
- doi:10.21203/rs.3.rs-9350097/v1: Who Broke the Pipeline? Traceability andAccountability in Multi-Agent LLM SoftwareEngineering Pipelines — https://doi.org/10.21203/rs.3.rs-9350097/v1
- doi:10.36227/techrxiv.175693284.49252769/v1: Adaptive Multi-Agent Role Reassignment over Model Context Protocol for Resilient AI Orchestration — https://doi.org/10.36227/techrxiv.175693284.49252769/v1
- doi:10.2139/ssrn.5402052: Adaptive Multi-Agent Role Reassignment over Model Context Protocol for Resilient AI Orchestration — https://doi.org/10.2139/ssrn.5402052
