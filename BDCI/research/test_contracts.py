"""Offline adversarial tests for the deterministic topic gate."""

import copy
import unittest

try:
    from .contracts import validate_and_select
except ImportError:
    from contracts import validate_and_select


class TopicGateTests(unittest.TestCase):
    def setUp(self):
        self.sources = {key: {"id": key, "abstract": "Retrieved abstract.",
                              "evidence_kind": "retrieved"} for key in ("a", "b")}
        self.candidate = {
            "id": "c1", "title": "A candidate research question",
            "research_question": "Does the intervention improve the measured outcome?",
            "hypothesis": "It reduces cost at matched quality.",
            "source_ids": ["a", "b"], "closest_work_id": "a",
            "difference": "Measure an additional resource-constrained condition.",
            "baseline": "Unmodified method", "metric": "Quality and API call count",
            "experiment": {"kind": "local_python", "dataset": "Public fixture",
                           "steps": ["Run baseline", "Run intervention", "Compare"],
                           "max_minutes": 5, "max_api_calls": 0, "needs_gpu": False},
            "risks": ["Effect may vanish across random seeds."]}
        self.critique = {"candidate_id": "c1", "novelty_concern": "Related work may overlap.",
                         "verdict": "advance", "reason": "Suitable for a small pilot only."}

    def check_gate(self, **kwargs):
        return validate_and_select([self.candidate], [self.critique], self.sources, **kwargs)

    def assert_blocked(self, reason):
        result = self.check_gate()
        self.assertEqual(result["status"], "needs_revision")
        self.assertFalse(result["live_pilot_allowed"])
        self.assertIn(reason, result["decisions"][0]["reasons"])

    def test_eligible_is_not_proven_novel_or_competition_scored(self):
        self.candidate["competition_score"] = 100
        self.critique["score"] = 100
        result = self.check_gate()
        self.assertEqual(result["eligible_candidate_ids"], ["c1"])
        self.assertTrue(result["live_pilot_allowed"])
        self.assertFalse(result["novelty_proven"])
        self.assertIsNone(result["competition_score"])

    def test_fabricated_citation(self):
        self.candidate["source_ids"].append("invented")
        self.assert_blocked("unknown_source:invented")

    def test_missing_abstract_is_explicit(self):
        self.sources["a"]["abstract"] = None
        self.assert_blocked("insufficient_evidence:no_abstract:a")

    def test_time_and_api_limits(self):
        for field, value, reason in (
                ("max_minutes", 21, "pilot_time_budget_exceeded_or_invalid"),
                ("max_minutes", float("nan"), "pilot_time_budget_exceeded_or_invalid"),
                ("max_api_calls", 7, "pilot_api_budget_exceeded_or_invalid"),
                ("max_api_calls", True, "pilot_api_budget_exceeded_or_invalid")):
            with self.subTest(field=field, value=value):
                original = self.candidate["experiment"][field]
                self.candidate["experiment"][field] = value
                self.assert_blocked(reason)
                self.candidate["experiment"][field] = original

    def test_missing_review(self):
        result = validate_and_select([self.candidate], [], self.sources)
        self.assertIn("missing_or_duplicate_critique", result["decisions"][0]["reasons"])

    def test_reject_and_revise_cannot_advance(self):
        for verdict in ("reject", "revise", "unknown"):
            self.critique["verdict"] = verdict
            self.assert_blocked("critic_did_not_advance")

    def test_synthetic_cannot_become_live_evidence(self):
        self.sources["a"]["evidence_kind"] = "synthetic"
        self.assert_blocked("synthetic_source_not_allowed:a")
        result = self.check_gate(allow_synthetic=True)
        self.assertEqual(result["status"], "eligible_for_pilot")
        self.assertEqual(result["evidence_mode"], "synthetic")
        self.assertFalse(result["live_pilot_allowed"])

    def test_duplicate_references_do_not_satisfy_two_sources(self):
        self.candidate["source_ids"] = ["a", "a"]
        self.assert_blocked("at_least_two_distinct_sources_required")

    def test_closest_work_must_be_cited(self):
        self.candidate["closest_work_id"] = "unseen"
        self.assert_blocked("closest_work_not_in_source_ids")

    def test_gpu_and_missing_fields(self):
        del self.candidate["hypothesis"]
        self.candidate["experiment"]["needs_gpu"] = True
        result = self.check_gate()
        self.assertIn("missing_or_invalid:hypothesis", result["decisions"][0]["reasons"])
        self.assertIn("gpu_required_or_unspecified", result["decisions"][0]["reasons"])

    def test_duplicate_candidates_and_critiques(self):
        result = validate_and_select([self.candidate, copy.deepcopy(self.candidate)],
                                     [self.critique, self.critique], self.sources)
        self.assertEqual(result["eligible_candidate_ids"], [])
        self.assertIn("duplicate_candidate_id", result["decisions"][0]["reasons"])
        self.assertIn("missing_or_duplicate_critique", result["decisions"][0]["reasons"])

    def test_hard_candidate_limit(self):
        with self.assertRaises(ValueError):
            validate_and_select([self.candidate] * 4, [self.critique], self.sources)

    def test_bad_types_fail_closed(self):
        self.candidate["source_ids"] = [{"id": "a"}, "b"]
        self.assert_blocked("at_least_two_distinct_sources_required")
        self.candidate["id"] = []
        result = self.check_gate()
        self.assertEqual(result["status"], "needs_revision")


if __name__ == "__main__":
    unittest.main()
