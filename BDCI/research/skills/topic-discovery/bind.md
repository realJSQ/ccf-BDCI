# Execution bounds

Three sequential workers, one model response each, no model-exposed tools.
The fixed runner performs up to four Crossref searches (five results per query).
All SDK/workflow retries and automatic image probes are disabled. ResearchBudgetRail
persists admission before model invocation; the caller holds a campaign file lock.
Live topic-v1 campaign has at most three requests, 2200 output tokens each; 20000
actual-token post-response stop threshold and 48000 preview-character guard.
Never reset a spent ledger automatically. Missing/invalid output stops the run.
Offline synthetic evidence cannot authorize a live pilot. Pilot plans are data,
not shell commands. The next executor must enforce its own aggregate resource budget.
