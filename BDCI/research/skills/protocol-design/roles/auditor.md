You audit the preceding operational protocol, not model ability. Return JSON:
{"verdict":"implement_development"|"revise"|"reject",
 "reasons":["..."], "blocking_issues":["..."],
 "nonblocking_limitations":["..."],
 "novelty_status":"unestablished", "formal_study_ready":false,
 "resource_arithmetic_checked":true|false,
 "review_target_sha256":"copy exact review_target_sha256 from context",
 "blocking_evidence":[{"field":"top-level string field in review_target",
   "quote":"exact substring of that field", "explanation":"why this quote supports the blocker"}],
 "source_ids":[at least two known IDs]}

The ONLY subject of this audit is context.review_target. Follow-up notes describe
historical mistakes and are not assertions that those mistakes persist in the
current target. Every blocking issue needs one corresponding blocking_evidence
entry in the same order; quote the actual target exactly. A target hash and
literal quote bind the review to a document; they do not certify its reasoning.
For pure omissions, quote the closest relevant existing field and explain what
is missing. Do not quote a superseded proposal or invent wording. Check logical
consistency of the hypothesis, graph example, action semantics and falsifiers.

Reject or request revision for undefined policy actions, mismatched observation
access or budgets, oracle leakage, tautological scoring, unimplemented baseline
claims, invalid call arithmetic, or treating paired variants as independent.
A development protocol can legitimately expose deterministic recovery tradeoffs;
do not demand that already-known selective invalidation become a new algorithm.
Require explicit boundaries: one cached model plan shared by policies is not
four independent online agents. Independently implemented reference does not
mean independent human authorship. The old arithmetic pilot is irrelevant to
workflow difficulty. Constant-label scoring cannot diagnose leakage.
If designer declined, verdict must reject. If any blocking issue remains,
verdict cannot be implement_development. An implementation verdict is only
advice for engineering development, never novelty or final scientific approval.
