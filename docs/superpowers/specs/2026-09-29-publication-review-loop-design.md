# Bounded publication review loop

## Goal and constraints

Generate a more complete English ICLR-style short paper from the frozen recovery-v2 experiment and six version-verified source excerpts. The previous six-page PDF is model-generated input, never manually edited. Expand only where the scientific argument needs clearer motivation, a worked method example, or fuller interpretation; there is no page target. Do not invent experiments, improved results, or literature claims unsupported by the excerpts.

## Approaches considered

1. Re-run the three-role publication command several times. This reuses code but repeats the full writer prompt and leaves no explicit cross-round review ledger or stopping rule.
2. **Chosen:** one native JiuwenSwarm workflow with a writer and a bounded sequence of anchored reviewer/reviser rounds. It keeps each draft, review, revision, exact prompt, raw response, and usage in one immutable campaign.
3. Ask the external Stanford reviewer after every iteration. Its queue, token and daily limits make it unsuitable as an internal loop; a final external review remains a separate submission step.

## Workflow and evidence

Prepare a fresh run using the existing verified manuscript as source. Recompute the frozen study evidence and plan audit, verify the six-source OpenAlex/arXiv manifest and its source hashes, and archive a profile hash before spending API calls. A prior mechanical quality report becomes explicit model feedback. Preparation makes no model request.

The workflow calls writer, reviewer 1, and then a reviser when review 1 requests changes. It performs at least two independent internal reviews. If review 2 passes, the loop stops; otherwise a second revision and final review 3 follow. Thus the maximum is six model calls: one writer, three reviews, two revisions. The final paper is the most recently accepted writer/reviser output. Every reviewer binds to that draft and the same evidence hash; every revision responds to each anchored issue. A review pass is an internal model judgment, not an external scientific certificate.

The final draft is rendered through the existing citation-aware ICLR renderer and checked with the existing PDF and mechanical quality audits. Mark it ready for external review only if the final internal review passes, the manuscript compiles, all six cited source IDs have primary excerpts, and mechanical findings are empty. Failure, uncertain model usage, or a review-cap result preserves artifacts and never automatically resends a request. A zero-API resume validates saved raw role outputs against the prepared prompts and profile.

## Implementation and validation

Add a separate loop entry point and team-skill workflow so completed three-role runs and historical profile-bound artifacts remain unchanged. Reuse the publication evidence loader, renderer, model adapter, and budget rail. Use a per-run ledger and one-shot execution fence. Add tests for branch order, review/revision hash binding, early pass, final review failure, no-resend behavior, inherited source integrity, and PDF quality reporting. Run the research test suite and one real campaign with the configured model. Deliver the generated PDF and an auditable run report; do not label an unreviewed PDF as having a matching Stanford access token or as already submitted to the competition.
