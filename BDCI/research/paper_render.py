"""Render plain-text agent writing with code-owned evidence and safe TeX.

This renderer does not certify scientific claims, novelty or submission readiness.
It never accepts executable LaTeX from model output or bibliographic metadata.
"""
from __future__ import annotations

import math
import shutil
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "validation/latex/iclr-template/iclr2026"
STYLE_FILES = ("iclr2026_conference.sty", "iclr2026_conference.bst", "natbib.sty", "fancyhdr.sty")
SECTION_NAMES = {"introduction": "Introduction", "related_work": "Related Work", "methods": "Methods",
                 "discussion": "Discussion", "conclusion": "Conclusion"}
NOTICE = "Workflow validation draft—not a competition submission"
LIMITATION = ("These descriptive results do not establish "
              "statistical significance, equivalence, generalization, or novelty. Agreement with an incorrect "
              "peer answer does not by itself establish causal copying. This draft validates the paper workflow.")


def tex_escape(value: object) -> str:
    """Escape once, character-by-character: replacement commands are never re-read."""
    replacements = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&",
                    "%": r"\%", "#": r"\#", "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
                    "—": "---", "–": "--", "‘": "`", "’": "'", "“": "``", "”": "''", "…": "..."}
    return "".join(replacements.get(c, c) if ord(c) >= 32 or c == "\n" else " " for c in str(value))


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid_" + field)
    return value.strip()


def _results(metrics):
    n = metrics.get("n")
    if type(n) is not int or n <= 0:
        raise ValueError("invalid_metric_n")
    errors = metrics.get("natural_peer_error_count")
    if type(errors) is not int or not 0 <= errors <= n:
        raise ValueError("invalid_peer_errors")
    accuracy, paired = metrics["accuracy"], metrics["paired"]
    rows = [("Evaluated items", str(n)), ("Natural peer errors", str(errors))]
    for key, label in (("peer", "Peer accuracy"), ("baseline", "Baseline accuracy"), ("intervention", "Intervention accuracy")):
        value = accuracy[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("invalid_accuracy")
        rows.append((label, f"{value:.6f} ({100 * value:.2f}%)"))
    counts = [paired[key] for key in ("wins", "losses", "ties")]
    if any(type(v) is not int or v < 0 for v in counts) or sum(counts) != n:
        raise ValueError("invalid_paired_counts")
    rows.extend(zip(("Intervention wins", "Intervention losses", "Ties"), map(str, counts)))
    return rows


def render_paper(root: Path, paper: dict, sources: dict, metrics: dict,
                 resource: dict, mode: str) -> Path:
    """Write paper.tex, references.bib, paper.md and four vendored template files.

    sources maps exact source IDs to metadata records. Unknown IDs fail before
    writing. Return the TeX entry point; compilation is the caller's responsibility.
    """
    title, abstract = _text(paper.get("title"), "title"), _text(paper.get("abstract"), "abstract")
    mode = _text(mode, "mode")
    sections = paper.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("invalid_sections")
    normalized, cited, seen = [], [], set()
    for section in sections:
        section_id = section.get("id")
        if section_id not in SECTION_NAMES or section_id in seen:
            raise ValueError("invalid_section_id")
        seen.add(section_id)
        body = _text(section.get("text"), "section_text")
        ids = section.get("source_ids", [])
        if not isinstance(ids, list) or any(not isinstance(s, str) for s in ids):
            raise ValueError("invalid_source_ids")
        for source_id in ids:
            if source_id not in sources:
                raise ValueError("unknown_source_id")
            if source_id not in cited:
                cited.append(source_id)
        normalized.append((section_id, body, list(dict.fromkeys(ids))))
    rows = _results(metrics)
    pilot_decision = resource.get("pilot_decision")
    if isinstance(pilot_decision, dict) and pilot_decision.get("status") == "hypothesis_not_supported_in_pilot":
        conclusion = "The hypothesis is not supported by this pilot. "
    else:
        conclusion = "This renderer does not determine whether the hypothesis is supported. "
    limitation = conclusion + LIMITATION
    keys = {source_id: f"ref{i:04d}" for i, source_id in enumerate(cited, 1)}
    bib_entries, md_refs = [], []
    for source_id in cited:
        source = sources[source_id]
        if source.get("evidence_kind", "retrieved") != "retrieved":
            raise ValueError("non_retrieved_reference")
        source_title = _text(source.get("title"), "source_title")
        authors = source.get("authors", [])
        if not isinstance(authors, list) or any(not isinstance(a, str) for a in authors):
            raise ValueError("invalid_authors")
        year = source.get("year")
        if year is not None and (type(year) is not int or not 1000 <= year <= 3000):
            raise ValueError("invalid_year")
        fields = ["title = {{" + tex_escape(source_title) + "}}"]
        if authors:
            fields.append("author = {" + " and ".join("{" + tex_escape(a) + "}" for a in authors) + "}")
        if year is not None:
            fields.append("year = {" + str(year) + "}")
        # Use normal text fields, not URL/DOI macros interpreting arbitrary content.
        detail = []
        if source_id.startswith("doi:"):
            detail.append("DOI: " + source_id[4:])
        if source.get("url"):
            detail.append(_text(source["url"], "source_url"))
        if detail:
            fields.append("note = {" + tex_escape("; ".join(detail)) + "}")
        bib_entries.append("@misc{" + keys[source_id] + ",\n  " + ",\n  ".join(fields) + "\n}")
        md_refs.append(f"- [{keys[source_id]}] {source_title}. {'; '.join(authors)}. {year or 'Year unavailable'}. {'; '.join(detail)}")
    resources = []
    for key in ("model_calls", "total_tokens", "duration_seconds", "cost"):
        if key in resource:
            value = resource[key]
            resources.append((key.replace("_", " "), "unknown" if value is None else str(value)))
    resource_text = "; ".join(f"{k}: {v}" for k, v in resources) or "Resource totals unavailable; see the run ledger."
    reused = resource.get("reused_pilot")
    if isinstance(reused, dict):
        prior = "; ".join(f"{k.replace('_', ' ')}: {reused[k]}" for k in ("model_calls", "total_tokens", "duration_seconds") if k in reused)
        resource_text = "Paper stage: " + resource_text + ". Reused pilot (no new experiment): " + (prior or "see original ledger") + "."
    result_tex = "\n".join([
        r"\section{Results}", tex_escape("Evidence mode: " + str(metrics.get("mode", "unspecified")) + ". Rendering mode: " + mode + "."),
        r"\begin{center}\begin{tabular}{lr}\hline", r"Measure & Observed value \\\hline",
        *[tex_escape(label) + " & " + tex_escape(value) + r" \\" for label, value in rows],
        r"\hline\end{tabular}\end{center}", tex_escape(limitation),
        r"\paragraph{Recorded resources.}" + tex_escape(resource_text),
    ])
    md = ["# " + title, "**" + NOTICE + "**", "Author label: Workflow validation (no personal authorship asserted).",
          "## Abstract", abstract]
    tex = [r"\documentclass{article}", r"\usepackage[T1]{fontenc}", r"\usepackage{iclr2026_conference,times}",
           r"\usepackage{url}", r"\iclrfinalcopy", r"\title{" + tex_escape(title) + r"\\[0.4em]{\small " + tex_escape(NOTICE) + "}}",
           r"\author{Workflow validation}", r"\begin{document}", r"\maketitle",
           r"\lhead{Workflow validation draft}", r"\begin{abstract}", tex_escape(abstract), r"\end{abstract}"]
    inserted = False
    for section_id, body, ids in normalized:
        if not inserted and section_id in ("discussion", "conclusion"):
            tex.append(result_tex)
            md.extend(["## Results", "Rendering mode: " + mode + "; evidence mode: " + str(metrics.get("mode", "unspecified")),
                       "| Measure | Observed value |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in rows), limitation, resource_text])
            inserted = True
        tex.extend([r"\section{" + SECTION_NAMES[section_id] + "}", tex_escape(body)])
        if ids:
            tex.append(r"\citep{" + ",".join(keys[i] for i in ids) + "}.")
        md.extend(["## " + SECTION_NAMES[section_id], body, "References: " + ", ".join(keys[i] for i in ids) if ids else ""])
    if not inserted:
        tex.append(result_tex)
        md.extend(["## Results", "\n".join(f"{k}: {v}" for k, v in rows), limitation, resource_text])
    if cited:
        tex.extend([r"\bibliographystyle{iclr2026_conference}", r"\bibliography{references}"])
    tex.append(r"\end{document}")
    md.extend(["## References", *md_refs])
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for filename in STYLE_FILES:
        shutil.copyfile(TEMPLATE / filename, root / filename)
    (root / "paper.tex").write_text("\n\n".join(tex) + "\n", encoding="utf-8")
    (root / "references.bib").write_text("\n\n".join(bib_entries) + "\n", encoding="utf-8")
    (root / "paper.md").write_text("\n\n".join(md) + "\n", encoding="utf-8")
    return root / "paper.tex"
