# Bounds

- One worker at a time; at most three total model calls, 512 output tokens each.
- Experimenter: at most two ReAct iterations. Writer: at most one.
- Only the fixed experiment tool is available to the experimenter; writer has none.
- Input, output and evidence remain in the fresh run directory.
- Missing results, invalid receipts, exhausted budgets and empty answers fail the run.
- Offline mode uses scripted model responses and is clearly marked, never reported as live.
- API credentials are never included in prompts or artifacts.
