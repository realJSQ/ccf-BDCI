# Recovery replay development experiment

The model proposes one bounded JSON recovery plan for a CPU tool workflow.
The same plan and observation are replayed under four deterministic recovery
policies. This is not a comparison of four independent interactive agents.
Actual tools calculate all values; no model arithmetic calibration is performed.

The runner freezes the dataset, public observations, protocol and source hashes
before any model request. Independent scoring occurs after policy execution.
Use `python BDCI/research/run_replay_study.py` for scripted integration only.
`--live` uses 18 calls from the existing research-v2 campaign (24 total cap).
The output remains a development study, not formal submission evidence.
