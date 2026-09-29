"""Fail-closed topic screening; eligibility is neither novelty nor a review score.

This module validates plans, but does not execute generated code or approve a
paper. Synthetic sources are accepted only for explicitly enabled dry runs.
"""

from collections import Counter
from collections.abc import Mapping
import math


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_and_select(candidates, critiques, sources, *, max_minutes=20,
                        max_api_calls=6, allow_synthetic=False):
    """Return deterministic screening decisions for at most three candidates.

    ``sources`` maps retrieved IDs to source metadata. Each candidate needs two
    distinct, abstract-bearing sources and exactly one independent critique.
    Budgets apply to each proposed pilot; callers must separately enforce any
    aggregate execution budget. Critiques must not be embedded in candidates.
    Passing this gate only permits pilot planning, never establishes novelty.
    """
    if not _number(max_minutes) or max_minutes <= 0:
        raise ValueError("max_minutes must be finite and positive")
    if type(max_api_calls) is not int or max_api_calls < 0:
        raise ValueError("max_api_calls must be a nonnegative integer")
    if not isinstance(allow_synthetic, bool):
        raise ValueError("allow_synthetic must be a boolean")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 3:
        raise ValueError("expected one to three candidates")
    if not isinstance(critiques, list) or not isinstance(sources, Mapping):
        raise ValueError("critiques must be a list and sources an ID mapping")

    ids = Counter(c.get("id") for c in candidates
                  if isinstance(c, Mapping) and _text(c.get("id")))
    reviews = {}
    for review in critiques:
        if isinstance(review, Mapping) and _text(review.get("candidate_id")):
            reviews.setdefault(review["candidate_id"], []).append(review)

    decisions = []
    uses_synthetic = False
    for candidate in candidates:
        reasons = []
        if not isinstance(candidate, Mapping):
            decisions.append({"candidate_id": None, "status": "needs_revision",
                              "reasons": ["candidate_not_object"]})
            continue
        cid = candidate.get("id")
        for field in ("id", "title", "research_question", "hypothesis",
                      "closest_work_id", "difference", "baseline", "metric"):
            if not _text(candidate.get(field)):
                reasons.append(f"missing_or_invalid:{field}")
        if _text(cid) and ids[cid] != 1:
            reasons.append("duplicate_candidate_id")
        risks = candidate.get("risks")
        if not isinstance(risks, list) or not risks or not all(map(_text, risks)):
            reasons.append("missing_or_invalid:risks")

        refs = candidate.get("source_ids")
        valid_refs = isinstance(refs, list) and all(map(_text, refs))
        if not valid_refs or len(set(refs)) < 2:
            reasons.append("at_least_two_distinct_sources_required")
        if valid_refs:
            if candidate.get("closest_work_id") not in refs:
                reasons.append("closest_work_not_in_source_ids")
            for ref in dict.fromkeys(refs):
                source = sources.get(ref)
                if not isinstance(source, Mapping):
                    reasons.append(f"unknown_source:{ref}")
                    continue
                if not _text(source.get("abstract")):
                    reasons.append(f"insufficient_evidence:no_abstract:{ref}")
                kind = source.get("evidence_kind")
                if kind == "synthetic":
                    uses_synthetic = True
                    if not allow_synthetic:
                        reasons.append(f"synthetic_source_not_allowed:{ref}")
                elif kind != "retrieved":
                    reasons.append(f"unverified_source_kind:{ref}")
                if source.get("id") != ref:
                    reasons.append(f"source_id_mismatch:{ref}")

        experiment = candidate.get("experiment")
        if not isinstance(experiment, Mapping):
            reasons.append("missing_or_invalid:experiment")
        else:
            if experiment.get("kind") not in ("local_python", "api_eval"):
                reasons.append("unsupported_experiment_kind")
            if not _text(experiment.get("dataset")):
                reasons.append("missing_or_invalid:experiment.dataset")
            steps = experiment.get("steps")
            if not isinstance(steps, list) or not steps or not all(map(_text, steps)):
                reasons.append("missing_or_invalid:experiment.steps")
            minutes = experiment.get("max_minutes")
            if not _number(minutes) or not 0 < minutes <= max_minutes:
                reasons.append("pilot_time_budget_exceeded_or_invalid")
            calls = experiment.get("max_api_calls")
            if type(calls) is not int or not 0 <= calls <= max_api_calls:
                reasons.append("pilot_api_budget_exceeded_or_invalid")
            if experiment.get("kind") == "api_eval" and calls == 0:
                reasons.append("api_eval_requires_positive_call_budget")
            if experiment.get("needs_gpu") is not False:
                reasons.append("gpu_required_or_unspecified")

        matches = reviews.get(cid, []) if _text(cid) else []
        if len(matches) != 1:
            reasons.append("missing_or_duplicate_critique")
        else:
            review = matches[0]
            for field in ("novelty_concern", "reason"):
                if not _text(review.get(field)):
                    reasons.append(f"missing_or_invalid:critique.{field}")
            if review.get("verdict") != "advance":
                reasons.append("critic_did_not_advance")
        decisions.append({"candidate_id": cid,
                          "status": "needs_revision" if reasons else "eligible_for_pilot",
                          "reasons": reasons})

    eligible = [d["candidate_id"] for d in decisions if d["status"] == "eligible_for_pilot"]
    return {"status": "eligible_for_pilot" if eligible else "needs_revision",
            "eligible_candidate_ids": eligible, "decisions": decisions,
            "evidence_mode": "synthetic" if uses_synthetic else "live",
            "live_pilot_allowed": bool(eligible) and not uses_synthetic,
            "novelty_proven": False, "competition_score": None,
            "limitations": ["Abstract-based screening cannot establish novelty.",
                            "Eligibility does not validate scientific merit or results.",
                            "Pilot budgets are per candidate; execution requires aggregate accounting."]}
