"""A deterministic arithmetic pilot, with private oracle and paired scoring.

No generated code or model text is evaluated. Peer errors must arise naturally;
this module never changes peer answers to manufacture a treatment effect.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from math import comb
import random

FAMILY = "integer_arithmetic_v1"


def make_dataset(seed=20260928, n=24):
    """Generate unique four-product-operand modular arithmetic questions.

    The oracle stays in the returned local dataset. Only ``public_inputs`` may
    be sent to a model. Each operand has three or four decimal digits.
    """
    if type(seed) is not int or type(n) is not int or not 1 <= n <= 10000:
        raise ValueError("invalid_dataset_parameters")
    rng = random.Random(seed)
    inputs, oracle, seen = [], [], set()
    while len(inputs) < n:
        operands = tuple(rng.randint(100, 9999) for _ in range(4))
        modulus = rng.randint(101, 997)
        values = operands + (modulus,)
        if values in seen:
            continue
        seen.add(values)
        a, b, c, d = operands
        identifier = f"A{len(inputs) + 1:04d}"
        question = f"Compute ({a} * {b} + {c} * {d}) % {modulus}, where % means the nonnegative remainder. Return an integer."
        inputs.append({"id": identifier, "question": question})
        oracle.append({"id": identifier, "answer": (a * b + c * d) % modulus})
    public_hash = hashlib.sha256(json.dumps(inputs, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    return {"family": FAMILY, "seed": seed, "inputs": inputs, "oracle": oracle,
            "public_inputs_sha256": public_hash}


def _dataset_ids(dataset):
    if not isinstance(dataset, Mapping) or dataset.get("family") != FAMILY:
        raise ValueError("invalid_dataset_family")
    rows = dataset.get("inputs")
    if not isinstance(rows, list) or not rows:
        raise ValueError("invalid_dataset_inputs")
    ids = []
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {"id", "question"}
                or not isinstance(row["id"], str) or not row["id"].strip()
                or not isinstance(row["question"], str) or not row["question"].strip()):
            raise ValueError("invalid_dataset_input_row")
        ids.append(row["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate_dataset_id")
    return ids


def public_inputs(dataset):
    """Return fresh public records, excluding oracle, seed and other metadata."""
    _dataset_ids(dataset)
    return [{"id": row["id"], "question": row["question"]} for row in dataset["inputs"]]


def parse_answers(jsondata, dataset):
    """Strictly validate an already decoded full answer array; never repair it.

    JSON decoding is the caller's responsibility. Extra fields, duplicate IDs,
    unknown or missing IDs and non-integer answers are all errors.
    """
    ids = _dataset_ids(dataset)
    if not isinstance(jsondata, list):
        raise ValueError("answer_array_required")
    answers = {}
    for row in jsondata:
        if not isinstance(row, dict) or set(row) != {"id", "answer"}:
            raise ValueError("invalid_answer_row")
        identifier, answer = row["id"], row["answer"]
        if not isinstance(identifier, str) or identifier not in ids:
            raise ValueError("unknown_answer_id")
        if identifier in answers:
            raise ValueError("duplicate_answer_id")
        if type(answer) is not int:
            raise ValueError("answer_must_be_integer")
        answers[identifier] = answer
    if set(answers) != set(ids):
        raise ValueError("missing_answer_ids")
    return answers


def _answers(value, dataset):
    if isinstance(value, Mapping):
        value = [{"id": key, "answer": answer} for key, answer in value.items()]
    return parse_answers(value, dataset)


def score_paired(dataset, peer_answers, baseline_answers, intervention_answers,
                 min_peer_errors=5):
    """Score two conditions on exactly the same items and natural peer answers.

    Correctness is exact integer equality. A propagated error equals the peer's
    incorrect answer; another incorrect answer is counted separately as an error.
    This cannot establish that agreement was causally influenced by the peer.
    """
    if type(min_peer_errors) is not int or min_peer_errors < 1:
        raise ValueError("invalid_min_peer_errors")
    ids = _dataset_ids(dataset)
    oracle = parse_answers(dataset.get("oracle"), dataset)
    peer = _answers(peer_answers, dataset)
    baseline = _answers(baseline_answers, dataset)
    intervention = _answers(intervention_answers, dataset)
    n = len(ids)
    wrong_ids = [i for i in ids if peer[i] != oracle[i]]
    wrong_n = len(wrong_ids)
    accuracy = {name: sum(answers[i] == oracle[i] for i in ids) / n
                for name, answers in (("peer", peer), ("baseline", baseline),
                                      ("intervention", intervention))}
    subset = {"size": wrong_n, "ids": wrong_ids,
              "propagated_error_definition": "Final answer equals the naturally incorrect peer answer; agreement is not proof of causal copying."}
    for name, answers in (("baseline", baseline), ("intervention", intervention)):
        propagated = sum(answers[i] == peer[i] for i in wrong_ids)
        errors = sum(answers[i] != oracle[i] for i in wrong_ids)
        subset[f"{name}_propagated_error_count"] = propagated
        subset[f"{name}_propagated_error_rate"] = propagated / wrong_n if wrong_n else None
        subset[f"{name}_any_error_count"] = errors
        subset[f"{name}_any_error_rate"] = errors / wrong_n if wrong_n else None
    items, wins, losses = [], 0, 0
    for identifier in ids:
        before = baseline[identifier] == oracle[identifier]
        after = intervention[identifier] == oracle[identifier]
        outcome = "win" if after and not before else "loss" if before and not after else "tie"
        wins += outcome == "win"
        losses += outcome == "loss"
        items.append({"id": identifier, "oracle_answer": oracle[identifier],
                      "peer_answer": peer[identifier], "peer_correct": peer[identifier] == oracle[identifier],
                      "baseline_answer": baseline[identifier], "baseline_correct": before,
                      "intervention_answer": intervention[identifier], "intervention_correct": after,
                      "outcome": outcome})
    discordant = wins + losses
    p = min(1.0, 2 * sum(comb(discordant, k) for k in range(min(wins, losses) + 1)) / 2 ** discordant) if discordant else None
    return {"family": FAMILY, "n": n,
            "status": "signal_observable" if wrong_n >= min_peer_errors else "insufficient_peer_errors",
            "natural_peer_error_count": wrong_n, "min_peer_errors": min_peer_errors,
            "accuracy": accuracy, "wrong_peer_subset": subset,
            "paired": {"items": items, "wins": wins, "losses": losses,
                       "ties": n - discordant, "accuracy_delta": (wins - losses) / n,
                       "sign_test_two_sided_p_descriptive": p,
                       "sign_test_interpretation": "Descriptive reference only; independent item sampling and independence within a model batch are not assumed."},
            "condition_balance": {"baseline": n, "intervention": n, "same_items": True,
                                  "shared_peer_answers": True},
            "pilot_descriptive_only": True, "novelty_proven": False,
            "limitations": ["Natural peer-error count determines observability, not whether an intervention helps.",
                            "One deterministic arithmetic family and paired batch cannot establish generalization.",
                            "Inputs and peer answers must actually be shared by the runner; scoring alone cannot verify model prompts."]}
