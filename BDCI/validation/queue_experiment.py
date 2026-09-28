"""Deterministic CPU simulation, not a new scheduling algorithm or benchmark."""
import json
from pathlib import Path
import sys


def mean_completion(jobs):
    elapsed = 0
    total = 0
    for duration in jobs:
        elapsed += duration
        total += elapsed
    return total / len(jobs)


def run(output):
    jobs = [9, 1, 7, 3, 5]
    metrics = {
        "job_count": len(jobs),
        "fifo_mean_completion_units": mean_completion(jobs),
        "sjf_mean_completion_units": mean_completion(sorted(jobs)),
        "total_service_units": sum(jobs),
    }
    output.write_text(json.dumps(metrics, indent=2) + "\n")
    return metrics


if __name__ == "__main__":
    print(json.dumps(run(Path(sys.argv[1]))))
