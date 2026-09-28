Revise the ENGLISH draft using the INTERNAL review and unchanged archived evidence.
No new experiments, capability tests or calibration. Never alter measured values,
reference IDs or run provenance. The paper remains a workflow-validation draft;
no novelty, significance, causal-copying, acceptance or external-review claim.
Retain floor-effect and missing-control caveats, source access/peer-review limits,
and the recorded policy-format ambiguity. Only textual revisions are in scope.
Return the COMPLETE paper JSON, not a diff: title, abstract, sections (the same
five IDs in the same list schema as the draft), plus response_to_review, a list
of {"issue_index":0,"change":"specific change made"}. Cover each review issue
exactly once with zero-based indices; an empty issue list needs an empty response.
Use plain text, known source_ids only, total paper text <=1000 English words
(hard maximum1600, not counting issue responses). Do not add a results section,
TeX commands or tables: code inserts the verified numerical table.
