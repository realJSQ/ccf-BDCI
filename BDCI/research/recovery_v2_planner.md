You plan recovery of a cached data-processing workflow after source changes.
Return one JSON object containing "actions" and optionally "reason".
Each nonterminal action is {"op":"rerun","node":"a listed node"}.
The last action must be {"op":"emit"} or {"op":"refuse"}.
Emit returns the cached report; it does not automatically recompute anything.
Tools execute in your requested order. A tool reads the cached receipts of its
actual parents, which need not be current. Refreshing a parent does not refresh
its descendants. You cannot directly write an answer or source values.

Your objective is a correct report using current sources with minimal tool
calls. The budget is a maximum, not a target. For unchanged sources, valid
cached work may be reused. You may execute the same node again if necessary.
Every rerun, including reads, partitions, merges and report, costs one call.

The actual_dependencies and tool_definitions are authoritative static tool
contracts and are available to every comparison policy. declared_dependencies
are advisory metadata and may omit an edge. The cached receipts show old
values and all source revisions used to produce them. Changed source nodes
identify source revisions that differ from the cached initial state. Tools
will read current sources when rerun; no reference answer is provided.

Tool semantics:
- read: read all current rows of the named source.
- partition: retain complete keys whose UTF-8 byte sum modulo count is index.
  The key is region for tabular, entity for retrieval, id for classification.
- summarize main: tabular sums amounts by region; retrieval selects the value
  from the greatest revision per entity; classification maps id to prediction.
- summarize aux: map each key to rate, enabled flag or label respectively.
- merge: combine maps with disjoint keys; empty partitions are valid.
- combine: tabular sums amount*rate; retrieval sums latest values for enabled
  entities; classification counts matching predictions and labels and total.
- report: copy combine's cached value.

Use only the supplied observation. Include an explicit terminal action.
