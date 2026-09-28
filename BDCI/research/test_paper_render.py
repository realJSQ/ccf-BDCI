import copy
import tempfile
import unittest
from pathlib import Path

try:
    from .paper_render import render_paper, tex_escape, STYLE_FILES
except ImportError:
    from paper_render import render_paper, tex_escape, STYLE_FILES


class PaperRenderTests(unittest.TestCase):
    def setUp(self):
        self.paper = {"title": "Plain draft", "abstract": "Descriptive workflow validation.",
                      "sections": [{"id": name, "text": "Plain discussion.", "source_ids": ["doi:10.1234/x"]}
                                   for name in ("introduction", "related_work", "methods", "discussion", "conclusion")]}
        self.sources = {"doi:10.1234/x": {"id": "doi:10.1234/x", "title": "Fixture metadata", "authors": ["Example Author"],
                                           "year": 2026, "url": "https://example.org/a?x=1&y=2"}}
        self.metrics = {"n": 24, "natural_peer_error_count": 23,
                        "accuracy": {"peer": 1 / 24, "baseline": 1 / 24, "intervention": 1 / 24},
                        "paired": {"wins": 0, "losses": 0, "ties": 24}, "mode": "fixture"}

    def test_truth_table_and_template(self):
        with tempfile.TemporaryDirectory() as d:
            path = render_paper(Path(d), self.paper, self.sources, self.metrics,
                                {"model_calls": 3, "reused_pilot": {"total_tokens": 16176},
                                 "pilot_decision": {"status": "hypothesis_not_supported_in_pilot"}}, "offline_scripted")
            tex = path.read_text()
            self.assertIn("4.17\\%", tex)
            self.assertIn("Natural peer errors & 23", tex)
            self.assertIn("hypothesis is not supported", tex)
            self.assertIn("not a competition submission", tex)
            self.assertIn(r"\lhead{Workflow validation draft}", tex)
            self.assertLess(tex.index("fontenc"), tex.index("iclr2026_conference,times"))
            self.assertLess(tex.index(r"\section{Results}"), tex.index(r"\section{Discussion}"))
            self.assertIn("16176", tex)
            for name in STYLE_FILES:
                self.assertTrue((Path(d) / name).is_file())

    def test_model_and_bibliography_cannot_inject_tex(self):
        payload = r"\input{/tmp/secret} % $ & # _ ~ ^ \end{document}"
        self.paper["title"] = payload
        self.paper["abstract"] = payload
        self.paper["sections"][0]["text"] = payload
        self.sources["doi:10.1234/x"].update(title=payload, authors=[payload], url=payload)
        with tempfile.TemporaryDirectory() as d:
            path = render_paper(Path(d), self.paper, self.sources, self.metrics, {}, "offline_scripted")
            tex, bib = path.read_text(), (Path(d) / "references.bib").read_text()
            self.assertNotIn(r"\input{", tex + bib)
            self.assertIn(r"\textbackslash{}input\{", tex + bib)
            self.assertEqual(tex.count(r"\end{document}"), 1)
            self.assertIn("@misc{ref0001", bib)
            self.assertIn(r"\citep{ref0001}", tex)

    def test_unknown_reference_rejected_before_writes(self):
        self.paper["sections"][0]["source_ids"] = ["unknown"]
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "unknown_source"):
                render_paper(Path(d), self.paper, self.sources, self.metrics, {}, "offline_scripted")
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_bad_counts_and_synthetic_references_rejected(self):
        for field in ("counts", "reference"):
            metrics, sources = copy.deepcopy(self.metrics), copy.deepcopy(self.sources)
            if field == "counts":
                metrics["paired"]["ties"] = 25
            else:
                sources["doi:10.1234/x"]["evidence_kind"] = "synthetic"
            with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
                render_paper(Path(d), self.paper, sources, metrics, {}, "offline_scripted")

    def test_control_characters_and_escape_once(self):
        self.assertEqual(tex_escape("a\x00b"), "a b")
        self.assertEqual(tex_escape("%"), r"\%")
        self.assertEqual(tex_escape("\\"), r"\textbackslash{}")

    def test_missing_or_other_decision_does_not_assert_negative_conclusion(self):
        self.metrics["accuracy"]["intervention"] = 1.0
        self.metrics["paired"] = {"wins": 23, "losses": 0, "ties": 1}
        for resource in ({}, {"pilot_decision": {"status": "positive_effect_observed"}},
                         {"pilot_decision": {"status": "inconclusive"}}):
            with self.subTest(resource=resource), tempfile.TemporaryDirectory() as d:
                path = render_paper(Path(d), self.paper, self.sources, self.metrics, resource, "offline_scripted")
                for content in (path.read_text(), (Path(d) / "paper.md").read_text()):
                    self.assertNotIn("The hypothesis is not supported by this pilot.", content)
                    self.assertIn("does not determine whether the hypothesis is supported", content)
                    self.assertIn("statistical significance", content)
                    self.assertIn("novelty", content)


if __name__ == "__main__":
    unittest.main()
