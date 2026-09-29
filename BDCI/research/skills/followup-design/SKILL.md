---
name: followup-design
description: Design and audit a bounded CPU follow-up from frozen negative recovery evidence.
---

Use the native SwarmFlow designer → auditor workflow. Both workers have no tools.
Input is verified recovery evidence, versioned public sources and prior methodological corrections.
Do not execute an experiment. A recommended design is not scientific certification.

The live campaign is `followup-design-v1-requests.jsonl`: at most 2 model requests,
24,000-token post-response stop threshold, 4,500 output tokens per request, zero retries.
Never clear or replace its ledger. The proposed later experiment may use at most
36 API calls, current CPU and API; no arithmetic calibration or training.
A decline is valid and must still receive the current-target audit.

Preserve prompt, raw response, context, usage and failure summary. Bind the audit to
the current design and evidence hashes. Every blocking issue quotes an exact field.
Always emit `execution_enabled=false`, including an `implement` recommendation.

If a failed designer response was recovered with verified `finish_reason=length`,
`--audit-rejected-run PATH` extracts only complete top-level JSON values and spends
the remaining campaign request on the auditor. It does not repeat the designer,
repair truncated text, or allow implementation. Prior usage is included in handoff
totals. The original source run is never modified by this recovery command.
