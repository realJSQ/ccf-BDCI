# Research Agent Framework Smoke Test

LIVE API. Not a competition submission.

This fixed-workload scheduling simulation compares two simple policies over five jobs with a total service time of 25 units. Under first-in-first-out, the mean completion time is 16.2 units; under shortest-job-first, it is 11.0 units. The runner reports these verified figures separately. This is a framework smoke test, not a novel research finding: it exercises the simulation pipeline and confirms that jobs are queued, ordered, and summarized as intended.

The limitations follow from that purpose. The workload is tiny and fixed, so the results describe only these five jobs and cannot be generalized to other arrivals, sizes, or priorities. Simulated job time is not measured wall-clock speed; it is an abstract scheduling quantity, not real runtime. The comparison also ignores overheads, preemption, and variability. The smoke test therefore validates mechanics, not policy performance.

- job_count: 5
- fifo_mean_completion_units: 16.2
- sjf_mean_completion_units: 11.0
- total_service_units: 25
