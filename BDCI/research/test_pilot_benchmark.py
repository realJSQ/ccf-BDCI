"""Offline correctness and fail-closed tests for the arithmetic pilot."""
import copy
import re
import unittest

try:
    from .pilot_benchmark import make_dataset, public_inputs, parse_answers, score_paired
except ImportError:
    from pilot_benchmark import make_dataset, public_inputs, parse_answers, score_paired


class PilotBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.dataset = make_dataset()
        self.truth = parse_answers(self.dataset["oracle"], self.dataset)

    def wrong(self, count):
        values = self.truth.copy()
        for identifier in list(values)[:count]:
            values[identifier] += 1
        return values

    def test_reproducible_unique_questions_and_independent_oracle(self):
        self.assertEqual(self.dataset, make_dataset())
        self.assertNotEqual(self.dataset["inputs"], make_dataset(seed=7)["inputs"])
        questions = [row["question"] for row in self.dataset["inputs"]]
        self.assertEqual(len(set(questions)), 24)
        for row in self.dataset["inputs"]:
            a, b, c, d, modulus = map(int, re.findall(r"\d+", row["question"]))
            self.assertEqual(self.truth[row["id"]], divmod(a * b + c * d, modulus)[1])
            self.assertTrue(all(100 <= value <= 9999 for value in (a, b, c, d)))

    def test_public_inputs_no_oracle_and_no_shared_mutable_rows(self):
        public = public_inputs(self.dataset)
        self.assertTrue(all(set(row) == {"id", "question"} for row in public))
        public[0]["question"] = "modified"
        self.assertNotEqual(public[0], self.dataset["inputs"][0])

    def test_answers_strict_types_ids_fields_and_completeness(self):
        original = self.dataset["oracle"]
        variants = [original[:-1], original + [original[0]], {"answers": original}, "[]"]
        for patch in ({"id": "unseen"}, {"id": 1}, {"id": []}, {"answer": True},
                      {"answer": 3.0}, {"answer": "3"}, {"extra": "field"}):
            rows = copy.deepcopy(original)
            rows[0].update(patch)
            variants.append(rows)
        variants.append([None] + original[1:])
        for rows in variants:
            with self.subTest(rows=str(rows)[:80]):
                with self.assertRaises(ValueError):
                    parse_answers(rows, self.dataset)

    def test_answer_order_can_differ(self):
        self.assertEqual(parse_answers(list(reversed(self.dataset["oracle"])), self.dataset), self.truth)

    def test_perfect_peer_cannot_claim_error_signal(self):
        result = score_paired(self.dataset, self.truth, self.wrong(5), self.truth)
        self.assertEqual(result["status"], "insufficient_peer_errors")
        self.assertIsNone(result["wrong_peer_subset"]["baseline_propagated_error_rate"])
        self.assertEqual(result["natural_peer_error_count"], 0)
        self.assertTrue(result["pilot_descriptive_only"])
        self.assertFalse(result["novelty_proven"])

    def test_identical_conditions_have_no_effect(self):
        peer = self.wrong(6)
        result = score_paired(self.dataset, peer, peer, peer)
        self.assertEqual(result["status"], "signal_observable")
        self.assertEqual(result["paired"]["accuracy_delta"], 0)
        self.assertEqual(result["paired"]["wins"], 0)
        self.assertEqual(result["paired"]["losses"], 0)
        self.assertEqual(result["paired"]["ties"], 24)
        self.assertIsNone(result["paired"]["sign_test_two_sided_p_descriptive"])

    def test_negative_effect_is_reported(self):
        peer = self.wrong(6)
        result = score_paired(self.dataset, peer, self.truth, peer)
        self.assertEqual(result["paired"]["accuracy_delta"], -0.25)
        self.assertEqual(result["paired"]["losses"], 6)
        self.assertEqual(result["wrong_peer_subset"]["intervention_propagated_error_rate"], 1)
        self.assertEqual(result["wrong_peer_subset"]["baseline_propagated_error_rate"], 0)

    def test_positive_effect_is_computed_not_assumed(self):
        peer = self.wrong(6)
        result = score_paired(self.dataset, peer, peer, self.truth)
        self.assertEqual(result["paired"]["accuracy_delta"], 0.25)
        self.assertEqual(result["paired"]["wins"], 6)
        self.assertEqual(result["paired"]["sign_test_two_sided_p_descriptive"], 0.03125)
        self.assertEqual(result["condition_balance"]["baseline"], 24)
        self.assertEqual(result["condition_balance"]["intervention"], 24)

    def test_different_wrong_answer_is_not_peer_error_agreement(self):
        peer, baseline = self.wrong(6), self.wrong(6)
        for identifier in list(baseline)[:6]:
            baseline[identifier] += 1
        result = score_paired(self.dataset, peer, baseline, self.truth)
        self.assertEqual(result["wrong_peer_subset"]["baseline_propagated_error_count"], 0)
        self.assertEqual(result["wrong_peer_subset"]["baseline_any_error_count"], 6)

    def test_minimum_peer_error_threshold(self):
        self.assertEqual(score_paired(self.dataset, self.wrong(4), self.truth, self.truth)["status"], "insufficient_peer_errors")
        self.assertEqual(score_paired(self.dataset, self.wrong(5), self.truth, self.truth)["status"], "signal_observable")

    def test_scoring_revalidates_mapping_and_oracle(self):
        bad = self.truth.copy()
        bad.pop(next(iter(bad)))
        with self.assertRaises(ValueError):
            score_paired(self.dataset, bad, self.truth, self.truth)
        self.dataset["oracle"][0]["answer"] = True
        with self.assertRaises(ValueError):
            score_paired(self.dataset, self.truth, self.truth, self.truth)

    def test_invalid_dataset_parameters(self):
        for seed, n in ((True, 24), (1, 0), (1, True), (1, 10001)):
            with self.assertRaises(ValueError):
                make_dataset(seed, n)


if __name__ == "__main__":
    unittest.main()
