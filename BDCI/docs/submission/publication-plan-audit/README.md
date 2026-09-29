# Saved-plan audit (post-hoc, no model calls)

This is a descriptive analysis of the existing frozen study, prompted by manuscript review. It is **not** a new experiment, an additional model sample, or a preregistered analysis. The statistical units remain nine base instances. No frozen input or result was edited.

From the repository root, rerun with Python's standard library only:

```bash
python BDCI/docs/submission/publication-plan-audit/audit_plans.py \
  --run BDCI/research/recovery_v2_runs/live-20260929T060132-126279 \
  --output /tmp/publication-plan-audit.json
cmp BDCI/docs/submission/publication-plan-audit/analysis.json /tmp/publication-plan-audit.json
```

`analysis.json` binds every inspected input, the frozen engine and its replay dependency, and this analysis script by SHA-256. It records all 36 plans, all 12 topology/scenario groups (three task families each), and all seven action-sequence equivalence groups. Reproduction was run twice with byte-identical output. Raw response JSON and accepted plan JSON agree exactly in all 36 cases. Replaying A with the frozen engine reproduces every saved semantic field; variable runtime timing is excluded from equality checks.

## Findings

| Measure | Observed count |
| --- | ---: |
| Plans with repeated rerun nodes | 0 / 36 |
| A trace exactly preserves raw plan order | 36 / 36 |
| Requested node set equals actual forward closure | 36 / 36 |
| Requested sequence equals canonical engine closure order | 35 / 36 |
| Requested sequence is a valid topological order | 36 / 36 |
| Unique action sequences, ignoring explanation text | 7 |
| Unique complete plans, including explanation text | 34 |

The seven action sequences occur 12, 9, 6, 3, 3, 2, and 1 times. Identical actions do not imply identical explanation text. Clean episodes share an empty rerun sequence followed by emit. Different task families can share an action sequence because the tool graph names and topology are shared.

The exception to canonical engine order is `episode_18`: retrieval, topology (3 main shards, 2 auxiliary shards), joint update. Its plan reads both sources first and groups partition operations before shard summaries. A preserves this alternative valid topological order exactly. The requested set still equals the actual closure. Therefore, saying that all plans have the engine's identical canonical order would be false.

## Engine semantics checked in frozen source

In `frozen_source/research/recovery_v2_engine.py`, `replay` constructs `nodes` from the original action list. Only D/E/F enter the set-union / canonical-order branch; A bypasses it. `validate_plan` checks actions and the terminal operation but does not reject repeated nodes or reorder actions. `Runtime.execute` consumes currently cached parent receipts; it does not implicitly rerun ancestors. The engine's initial static contract consistency check validates public tool definitions and does not reorder A's action list.

Thus A does not silently deduplicate or force topological execution. No saved plan contains duplicate reruns, so the duplicate-node runtime behavior is established by source inspection rather than by claiming an observed duplicate episode. There are no extra synthetic intervention tests in this analysis.

The closure comparison uses an independently written queue-based traversal of the saved actual dependency graph and cross-checks the frozen closure function. It characterizes these supplied-graph plans; it does not show graph discovery, superiority to G, or generalization to unseen structures. D/E/F can deduplicate and reorder requests by design, a distinction that should remain explicit in the manuscript.
