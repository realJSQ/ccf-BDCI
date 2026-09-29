"""Contract checks for credential isolation and full-text eligibility."""
import json
from pathlib import Path
import tempfile
import unittest

try:
    from .openalex_literature import LiteratureError, build_literature, reconstruct_abstract
except ImportError:
    from openalex_literature import LiteratureError, build_literature, reconstruct_abstract


IDENTIFIER = "arxiv:2608.10502v1"
TITLE = "From Faulty Memories to Corrected Actions: Dependency-Guided Rollback Repair for Memory-Augmented Agents"
QUERY = [{"id": IDENTIFIER, "title": TITLE, "selected": True}]


def _work(*, linked=True, title=TITLE, author="Caili Yu"):
    return {"id": "https://openalex.org/W123", "display_name": title,
            "doi": "https://doi.org/10.48550/arXiv.2608.10502" if linked else "https://doi.org/10.9999/other",
            "publication_year": 2026,
            "authorships": [{"author": {"display_name": author}}],
            "abstract_inverted_index": {"Faulty": [0], "memories": [1], "propagate.": [2]},
            "locations": []}


def _html(*, title=TITLE, author="Caili Yu"):
    paragraphs = [
        "Persistent memory errors propagate into later actions and answers. " * 8,
        "The method traces dependency edges and rolls back affected memory records. " * 8,
        "Evaluation compares selective replay with a full replay baseline and diagnoses limitations. " * 9,
        "A dependency graph directs repair and invalidation through saved states. " * 10,
        "Discussion of limitations and failure cases of rollback. " * 10,
        "Further analysis of dependency and provenance of cached entries. " * 10,
        "Method details demonstrate how affected actions are rerun in topological order. " * 10,
        "Experiments report recovery and consistency in controlled cases. " * 10,
    ]
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return (f'<html><head><title>{title} [2608.10502]</title>'
            f'<meta name="citation_title" content="{title}">'
            f'<meta name="citation_author" content="{author}">'
            '<meta name="citation_arxiv_id" content="2608.10502"></head>'
            f'<body><h2>Method and limitations</h2>{body}</body></html>').encode()


class OpenAlexLiteratureTests(unittest.TestCase):
    def _prepare(self, directory, work=None, primary=None, search_work=None):
        directory = Path(directory)
        key = directory / "search_api.txt"
        key.write_text("openalex : private-test-key-123456789\n")
        requests = []
        def transport(url, timeout, limit, accept):
            requests.append((url, timeout, limit, accept))
            if "/works/https%3A" in url:
                return json.dumps(work or _work()).encode()
            if "api.openalex.org" in url:
                return json.dumps({"meta": {"count": 1},
                                   "results": [search_work or work or _work()]}).encode()
            if url == "https://arxiv.org/html/2608.10502v1":
                return primary or _html()
            raise AssertionError("unexpected_network_target")
        return key, transport, requests

    def test_selected_needs_search_metadata_and_primary_fulltext(self):
        with tempfile.TemporaryDirectory() as name:
            key, transport, requests = self._prepare(name)
            root = Path(name) / "run"
            manifest = build_literature(root, key, QUERY, transport=transport)
            self.assertEqual(len(requests), 2)
            self.assertEqual(manifest["queries"][0]["returned_count"], 1)
            source = manifest["sources"][IDENTIFIER]
            self.assertEqual(source["verification_status"], "primary_fulltext")
            self.assertEqual(source["authors"], ["Caili Yu"])
            self.assertTrue(source["openalex_identifier_linked"])
            self.assertGreater(len(source["primary_text_excerpt"]), 4000)
            self.assertEqual(source["url"], "https://arxiv.org/abs/2608.10502v1")
            self.assertTrue((root / "primary_html/2608.10502v1.html").exists())
            public = (root / "literature_manifest.json").read_text()
            self.assertNotIn("private-test-key", public)
            self.assertNotIn("private-test-key", json.dumps(manifest))

    def test_title_collision_without_arxiv_identifier_is_not_eligible(self):
        with tempfile.TemporaryDirectory() as name:
            key, transport, _ = self._prepare(name, work=_work(linked=False))
            with self.assertRaisesRegex(LiteratureError, "openalex_arxiv_identifier_missing"):
                build_literature(Path(name) / "run", key, QUERY, transport=transport)

    def test_search_ranking_miss_uses_canonical_doi_lookup(self):
        with tempfile.TemporaryDirectory() as name:
            other = _work(linked=False, title="An Unrelated Cache Paper")
            key, transport, requests = self._prepare(name, search_work=other)
            manifest = build_literature(Path(name) / "run", key, QUERY, transport=transport)
            self.assertEqual(len(requests), 3)
            self.assertIn("canonical_doi_lookup", manifest["queries"][0])
            self.assertEqual(len(manifest["sources"]), 1)
            self.assertEqual(len(manifest["discovered"]), 2)

    def test_canonical_doi_may_correct_stale_index_title_only_with_primary_match(self):
        with tempfile.TemporaryDirectory() as name:
            stale = _work(title="Stale Index Title")
            key, transport, requests = self._prepare(name, work=stale)
            manifest = build_literature(Path(name) / "run", key, QUERY, transport=transport)
            self.assertEqual(len(requests), 3)
            self.assertTrue(manifest["sources"][IDENTIFIER]["openalex_title_differs"])
            self.assertEqual(manifest["sources"][IDENTIFIER]["title"], TITLE)
            self.assertEqual(manifest["sources"][IDENTIFIER]["openalex_title"], "Stale Index Title")

    def test_primary_title_and_author_mismatch_fail_closed(self):
        for document, code in [(_html(title="A Different Paper"), "primary_title_mismatch"),
                               (_html(author="Other Writer"), "primary_openalex_author_mismatch")]:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as name:
                key, transport, _ = self._prepare(name, primary=document)
                with self.assertRaisesRegex(LiteratureError, code):
                    build_literature(Path(name) / "run", key, QUERY, transport=transport)

    def test_author_accent_and_order_do_not_hide_same_person(self):
        with tempfile.TemporaryDirectory() as name:
            key, transport, _ = self._prepare(name, work=_work(author="Yu, Caili"),
                                              primary=_html(author="Cailí Yu"))
            manifest = build_literature(Path(name) / "run", key, QUERY, transport=transport)
            self.assertEqual(manifest["sources"][IDENTIFIER]["authors"], ["Cailí Yu"])

    def test_index_only_middle_initial_does_not_reject_primary_author(self):
        with tempfile.TemporaryDirectory() as name:
            key, transport, _ = self._prepare(name, work=_work(author="Caili K. Yu"))
            manifest = build_literature(Path(name) / "run", key, QUERY, transport=transport)
            self.assertEqual(manifest["sources"][IDENTIFIER]["authors"], ["Caili Yu"])

    def test_primary_title_spacing_is_readable_without_changing_identity(self):
        with tempfile.TemporaryDirectory() as name:
            key, transport, _ = self._prepare(name, primary=_html(title=TITLE.replace(": ", ":")))
            manifest = build_literature(Path(name) / "run", key, QUERY, transport=transport)
            self.assertEqual(manifest["sources"][IDENTIFIER]["title"], TITLE)

    def test_discovery_only_does_not_enter_sources(self):
        with tempfile.TemporaryDirectory() as name:
            key, transport, _ = self._prepare(name)
            manifest = build_literature(Path(name) / "run", key,
                                        [{**QUERY[0], "selected": False}], transport=transport)
            self.assertFalse(manifest["sources"])
            self.assertEqual(len(manifest["discovered"]), 1)
            self.assertFalse(manifest["discovered"][0]["eligible"])

    def test_network_exception_never_exposes_key(self):
        with tempfile.TemporaryDirectory() as name:
            key, _, _ = self._prepare(name)
            def fail(url, *_):
                raise RuntimeError(url)
            with self.assertRaises(LiteratureError) as caught:
                build_literature(Path(name) / "run", key, QUERY, transport=fail)
            self.assertNotIn("private-test-key", str(caught.exception))
            self.assertNotIn("private-test-key", (Path(name) / "run/literature_manifest.json").read_text())

    def test_abstract_positions_are_reconstructed_not_sorted_alphabetically(self):
        self.assertEqual(reconstruct_abstract({"B": [1], "A": [0], "C": [2]}), "A B C")
        with self.assertRaisesRegex(LiteratureError, "invalid_abstract_index"):
            reconstruct_abstract({"A": [0], "B": [2]})


if __name__ == "__main__":
    unittest.main()
