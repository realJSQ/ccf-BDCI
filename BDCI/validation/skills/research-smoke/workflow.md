# Workflow

1. Experimenter calls the fixed experiment tool. Its result must be a valid
   receipt registered by the source-level ExperimentEvidenceRail.
2. The coordinator reopens the metrics file and checks its hash and values.
3. Writer receives only the verified metrics and role instructions.
4. Local validation checks the evidence again, generates a report with a
   deterministic table, and invokes the separately installed LaTeX compiler.

No step may silently substitute a mock result in live mode. There are no retries.
