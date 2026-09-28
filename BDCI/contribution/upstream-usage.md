# Research evidence and model-admission rails

These two opt-in rails use existing AgentRail callbacks. They do not replace the
workflow engine or establish scientific validity. Target source: JiuwenSwarm
`fc18e5c572a6b3b62bb42ea843cce674140e4266` with agent-core
`9e3390195a9ea15235b2b5f7412cb2aa440622cc`.

## Evidence receipt validation

`ExperimentEvidenceRail(root, tool_name="run_queue_experiment")` runs only after
the named tool. Register it through `register_rail_provider`, then add its
`RailSpec` to the experimental worker's `DeepAgentSpec`. The tool must return:

| Field | Meaning |
| --- | --- |
| `run_id` | Nonempty execution identifier; currently not checked against an expected ID |
| `exit_code` | Integer zero for a successful tool execution |
| `metrics_path` | Relative path resolving inside the allowed root |
| `metrics_sha256` | SHA-256 of the exact metrics file bytes |
| `command` | Nonempty list of command strings, recorded rather than executed by this rail |
| `duration_seconds` | Finite nonnegative numeric elapsed time |

The file must contain a nonempty JSON object of finite numeric values, excluding
booleans. Validation rejects missing files, escaping paths (including symlinks),
hash mismatches and invalid metrics. Accepted receipts go to `evidence.jsonl`;
rejections record fixed reasons in `evidence_rejections.jsonl` and raise
`ValueError`. Extra receipt fields are not archived.

Trust boundary: the selected tool and experiment root must be controlled by the
application. This is file-integrity checking, not authentication, expected-run
binding, metric-semantic validation or protection against a malicious writer
that can replace both a file and its receipt. It does not validate novelty,
statistics or prose. It is not a general claim-evidence graph.

## Persistent model admission

Create `ResearchRunBudget(root, ledger_path, max_calls=..., token_stop=...,
max_prompt_chars=...)`, wrap it in `ResearchBudgetRail`, and register that rail
for the relevant `DeepAgentSpec`. Use one shared budget object and persistent
ledger for the entire sequential campaign, including distinct role workers.

The caller must create parent directories and hold an exclusive process lock on
the campaign for its entire lifetime (for example, `fcntl.flock` on Linux).
The budget class does not acquire this lock and is not a concurrent reservation
service. Do not share one active admission between simultaneous model calls.

`before_model_call` verifies paired admission/usage history, cumulative admitted
calls, cumulative reported tokens and message-preview length, then durably
appends an admission. `after_model_call` records valid integer token usage and
finish reason. Both the campaign ledger and per-run `model_usage.jsonl` are
flushed and fsynced; they are separate writes, not a transaction across files.

A request without valid usage remains unresolved and blocks future admissions,
including after process restart. Do not erase that admission to force a retry.
Token accounting is reported usage, not a tokenizer estimate or invoice. The
token threshold stops subsequent calls and can be exceeded by the final call.
Truncated responses are recorded before cancellation. All cancellation reasons
use `asyncio.CancelledError` so a generic `except Exception` retry handler does
not silently resend a request. Applications must preserve cancellation and also
disable retries at the model client and workflow layers if strict admission
counts are required.

This version deliberately rejects exposed tools. It is intended for tool-free
planning/writing roles, not a drop-in budget for arbitrary tool-enabled agents.
Tool-running experiments need their own execution accounting and configuration.

## Verification

With the pinned upstream runtime dependencies installed, run from the patched
JiuwenSwarm repository root:

```bash
export JIUWENSWARM_HOME="$PWD/.research-test-runtime"
export JIUWENSWARM_DATA_DIR="$JIUWENSWARM_HOME/.jiuwenswarm"
PYTHONPATH="$PWD" python -m unittest discover -s tests -p 'test_research_*_rail.py' -v
```

The two contributed files contain 24 tests: nine receipt checks and fifteen
admission/accounting checks. They use temporary files and synthetic callback
objects, with no API credentials or network. They test the rails' contracts, not
full scientific experiments or upstream-wide compatibility.

An application must separately test its native workflow and actual tool/model
callback wiring. The accompanying BDCI prototype has native offline workflow
and request-blocking traces, but those application files are not dependencies
of this patch. No upstream acceptance or competition score is implied.
