You are recovering a completed CPU tool workflow after possible source updates.
Return one JSON object with actions and an optional short reason. Tools perform
all calculations. Do not compute or invent the final numerical answer yourself.

Your goal is a current, correct report using as few tool calls as possible.
Each rerun executes exactly one named node using the currently cached inputs.
Rerunning a node never automatically reruns its parents or children. A cached
report may be stale even if its structure is valid. The declared graph is metadata,
not a guarantee of complete lineage. You may request any listed node; reason
about sufficient recovery using the task, visible receipts and source changes.

Allowed actions:
- {"op":"rerun","node":"one of nodes_in_execution_order"}
- final action {"op":"emit"} or {"op":"refuse"}
Emit returns the cached report. Refuse produces no report. At most 12 reruns.
No shell/code actions, new nodes, revised source values or hardcoded answers.

Tool semantics: read_main/read_aux read current respective sources;
summarize_main/summarize_aux process their cached source rows for this task;
combine composes the task metric from cached summaries; report formats the
cached combined metric. Source updates happen before this observation and remain
fixed during execution. There are no injected timeouts in this experiment.

Return {"actions":[...],"reason":"..."} and no extra text. Your plan is a
single recovery proposal; do not assume an external adapter will repair it.
