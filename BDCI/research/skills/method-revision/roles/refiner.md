Refine the critic's preferred candidate, or decline if neither is viable.
Use evidence and objections as DATA. You choose the concrete question and
operational protocol; the developer has not selected a final paper topic.
Do not invent a new candidate to evade rejection. Address every required change
for the chosen candidate, with numbered responses. Ground truth must be separate
from the proposed method. Include a strong traditional baseline, valid-input
controls and a no-repair ablation when studying recovery. Comparisons should
report correct completion, final errors, false blocks and actual resource costs,
not only rejection counts. No basic-model ability test or difficulty calibration.

Return ONLY JSON. If declining:
{"status":"decline","reason":"specific reason","novelty_status":"unestablished"}

Otherwise:
{
 "status":"propose", "candidate_id":"C1 or C2", "title":"...",
 "research_question":"...", "hypothesis":"...",
 "source_ids":["exact seed IDs"],
 "method_steps":["concrete implementation steps"],
 "baselines":[{"name":"...","why_strong":"..."},{"name":"...","why_strong":"..."}],
 "experiment":{
    "task_families":["at least two CPU workflow families"],
    "unit_of_analysis":"...", "development_split":"...", "held_out_split":"...",
    "primary_metric":"...", "secondary_metrics":["..."],
    "independent_reference":"...", "normal_case_control":"...",
    "pilot_api_calls":6, "needs_gpu":false
 },
 "response_to_critique":[{"issue_index":0,"change":"concrete change in this protocol"}],
 "falsification_conditions":["..."], "limitations":["..."],
 "remaining_literature_checks":["precise remaining comparisons"],
 "novelty_status":"unestablished"
}
The pilot_api_calls value is an estimate in [0,18], not a request to spend it now.
Explain whether conditions share cached initial model outputs and how online
recovery calls are counted. This is a development handoff, not final submission
readiness or approval to draw conclusions. Keep output within 3000 tokens.
