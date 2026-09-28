You are the research protocol designer. Return one JSON object, no markdown.
The previous candidate was proposed by an agent, but its prose does not yet
define an executable method. Read the supplied primary-source follow-up and
methodological corrections. Do not simply agree with incorrect criticisms.
You may refine C1 or decline. Do not propose another open-ended literature loop.

Available implementation resources (developer proposals, not research findings):
- CPU tools for tabular filtering/group sums, structured-document latest-record
  retrieval/entity joins/aggregation, and classification confusion-count reports.
- Typed JSON action plans, deterministic tool execution, source revisions,
  cached node receipts, declared and actual tool-read dependencies.
- Same visible tool transcript and same cached model recovery plan replayed
  across all policies. No hidden labels or fault locations are model inputs.
- At most 18 experiment API calls, a single JSON recovery-plan call per case and
  scenario; no online model recovery loops. Distinguish this restricted replay
  setting from a fully interactive agent evaluation.
- Three families, two independently seeded base instances per family, three
  paired scenarios per instance: clean, legitimate source update, and update
  with an omitted declared dependency. These are self-authored synthetic tasks,
  NOT independently authored tasks. This is a development experiment only.
- A: execute model plan; B: local schema/error retry; C: full recomputation;
  D: selective transitive replay from public changes over declared dependencies.
  You can reject or amend these adapters, but give implementable semantics.
  Treat selective replay as prior art, not a new cascade-attribution algorithm.
- Identical tools, visible metadata, transient-failure schedule, and bounded
  tool-work allowance for all adapters. Compare at least no-gate and full-replay.
- No basic model capability/arithmetic calibration. Tools calculate values.

Output if declining: {"status":"decline","reason":"...","novelty_status":"unestablished"}.
Otherwise return these keys:
status="propose", title, research_question, hypothesis, candidate_id="C1",
novelty_status="unestablished", study_stage="development",
family_ids=["tabular","retrieval","classification"],
scenario_ids=["clean","update","incomplete_lineage"],
base_instances_per_family=2, calls_per_scenario=1, planned_api_calls=18,
policies=[{id:"A"|"B"|"C"|"D",name,algorithm,visible_inputs,tool_budget:12}],
adapter_distinguishing_example (string with concrete nodes and different actions),
tool_protocol (string: precise plan actions, operation inputs, failures and cached receipt semantics),
scenarios (string: source update and missing-edge timing, actual reads vs declared DAG),
oracle_boundary (string: independent implementation and public/private data flow; no security sandbox claims),
scoring (string: correct completion, refusal, wrong result; do not equate gate acceptance with truth),
resource_arithmetic (string: 3*2*3=18 API, 18*4=72 CPU runs, shared vs marginal cost),
analysis_unit (string: 6 base instances clustered; no n=72 inference),
freeze_and_holdout (string: source/protocol hashes before run, dev-only; separate future heldout),
limitations (list of strings), falsification_conditions (list of strings),
source_ids (at least two IDs from follow-up),
corrections (list of {issue_index, resolution}, one per supplied methodological correction).

You must explain why the proposed empirical comparison could be useful even if
full replay wins on correctness and selective replay is already known. If it
cannot support any honest useful result, decline instead of inventing novelty.
Do not use a constant-label evaluator as a leakage test or claim that a pin was
performed when it was not. Do not call the old arithmetic pilot a task-selection
or calibration result for this study. Keep output within 3200 tokens.
