# Add opt-in evidence receipts and persistent model admission for research workflows

Research workflows need to stop before reusing a missing or modified experiment
file, and before resending a model request whose outcome was not recorded.
This patch adds two opt-in AgentRail implementations using existing callbacks.

`ExperimentEvidenceRail` validates a selected tool's file receipt (successful
exit, confined path, content hash and finite numeric metrics) and archives the
acceptance or rejection. `ResearchBudgetRail` durably records model admissions
and token usage, limits subsequent calls, and leaves uncertain requests blocked
across restarts. Optional `None` token and prompt limits disable those checks
while preserving usage accounting, call limits and unresolved-request guards. Callers retain ownership of campaign locking and retry policy.

The patch adds 28 no-network contract tests and documents registration, receipt
fields, accounting and trust boundaries. It makes no global configuration or
default-agent behavior changes.

Limitations are explicit: receipts do not establish scientific correctness or
expected-run identity; the budget is for sequential tool-free calls; token
limits are post-response stop thresholds rather than hard monetary caps. The
two log writes are not a multi-file transaction. The patch and 28 contract
tests passed on the pinned base and a recorded develop commit; full upstream
suite compatibility is not asserted.

Validation results and exact patch digest are in the adjacent `validation.json`.
This is draft PR text; no PR has been submitted or accepted.
