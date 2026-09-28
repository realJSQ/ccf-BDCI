Review ONLY current_draft against current_evidence and source notes. Older
proposals are not the review target. Return one JSON object:
{verdict:"pass"|"revise", external_reviewer:false,
 issues:[{severity:"blocking"|"major"|"minor",section_id:"abstract"|"introduction"|"related_work"|"methods"|"discussion"|"conclusion",message:"..."}],
 revision_instructions:["..."], draft_sha256:"copy supplied value",
 evidence_sha256:"copy supplied value", issue_quotes:["exact substring of corresponding reviewed section", ...]}.
One exact quote per issue, in the same order. For an omission quote the closest
related text and explain the missing item. Do not invent absent claims.
Check all quantitative claims against evidence, especially strict versus posthoc
distinction, malformed output versus voluntary refusal, paired analysis unit,
absence of benefit beyond A, and existing selective replay prior art. Request
concrete fixes for unsupported superiority/novelty or unimplemented mechanisms.
Do not manufacture an issue simply to force revision. Pass cannot coexist with
blocking or major issues. This is internal review, not Agentic Reviewer.

Check draft_word_count against final_word_limit. Oversized drafts can be reviewed
but cannot be rendered as final papers. Request concise substantive revision,
especially of repetitive abstract/discussion/conclusion; aim at1200 words.
