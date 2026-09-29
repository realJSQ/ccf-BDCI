# Recovery manuscript publication revision

User requested continued improvement after uploading the existing PDF, identifying bad citations, internal run paths, and poor scientific presentation. Existing authorization covers local implementation and normal configured model testing; no official PR publication is requested.

## Diagnosis

The old role contract prohibited inline citation markers and only supplied section-level source_ids. The renderer appended every section reference after the entire section. BibTeX protected full personal names as if corporate authors, yielding full-name in-text citations. Evidence notes and audit metadata were copied into prose, while the reviewer encouraged repetition. Hash and schema tests did not detect poor reader-facing quality. Three fixed-version arXiv sources exist; some interpretations still need narrowing. The user supplied OpenAlex credentials and requires its literature search inside the pipeline. OpenAlex is a metadata index; selected claims require source-version primary text.

## Chosen change

Preserve uploaded paper and historical workflows. Add an independent publication renderer and native three-role revision entry, without editing old profile-hashed code or skills. References use validated inline [[cite:source_id]] / [[citet:source_id]] markers placed next to supported claims and rendered into natbib commands. Normalize known authors, keep cited versions, and identify preprints. Unknown IDs, unplaced section references, raw markers and internal audit terminology fail validation. Use numbered table captions and short scientific case labels.

Prepare and save prompts before model invocation. Writer receives the existing manuscript for revision, verified scientific context, fixed-version reading notes, OpenAlex-discovered versioned primary text, positive/negative examples, and specific corrections. Reviewer checks actual errors once, does not pad issues or demand limitations in every section. Reviser may rebut unsound feedback. No artificial word/token cap. One explicit live campaign, usage recorded including failure; no blind resend. Saved-role resume performs zero API calls. The literature stage runs during preparation and is bound into prompt provenance; missing selected full text stops preparation.

Keep numerical data, policy semantics, nine paired units and null result fixed. Explain the split, scoring and policy definitions, but remove historical file paths, adapter status and audit inventories from the main text. Disclose developer assistance once. The model cannot claim new experiments or stronger evidence.

## Acceptance

Verify exact citation IDs and source-version metadata, personal-name BibTeX formatting, no section-end citation dump or internal paths, raw text safely escaped, tables/References present, no undefined citations, all PDF pages visually reviewed. Preserve raw model text and prompts; verify source evidence before and after. Existing bundles continue verifying with their own code. New manuscript is a revision, not automatically covered by the submitted PDF's Reviewer Token.

## External review handling

User-reported upload matches PDF SHA256 2f28be6eae0d1464889f9f72021121ebafb1badff1e7a88fe2a0b3d845d96850. Token and submission record are local in ignored runtime/external-review; status was retrieved as complete for the uploaded old PDF; no token or full review enters the new model prompt. Never put token into prompts, public Git or new manuscript. PR deferred per user request.
