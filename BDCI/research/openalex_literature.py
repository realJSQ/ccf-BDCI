"""Bounded OpenAlex discovery with independent, versioned primary-text checks.

OpenAlex supplies discovery and bibliographic metadata. It does not supply the
full text used here. The primary text is fetched separately from a versioned
arxiv.org/html URL; neither search ranking nor an abstract proves a paper's
claims. All remote material remains untrusted data for the writing roles.
"""
from __future__ import annotations

import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


API = "https://api.openalex.org/works"
ARXIV_ID = re.compile(r"^arxiv:([0-9]{4}\.[0-9]{4,5}v[1-9][0-9]*)$")
MAX_SEARCHES = 12
MAX_RESULTS = 10
MAX_SEARCH_BYTES = 2_000_000
MAX_HTML_BYTES = 8_000_000
TIMEOUT_SECONDS = 20


class LiteratureError(RuntimeError):
    """A selected source could not be established from the saved evidence."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise LiteratureError("redirect_refused")


def _network(url: str, timeout: int, limit: int, accept: str) -> bytes:
    """Never expose URLs in exceptions: the OpenAlex URL contains the key."""
    request = Request(url, headers={"User-Agent": "BDCI-Literature/1.0", "Accept": accept})
    try:
        with build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            raw = response.read(limit + 1)
    except (HTTPError, URLError, OSError, LiteratureError) as exc:
        raise LiteratureError("literature_network_failure") from None
    if len(raw) > limit:
        raise LiteratureError("literature_response_too_large")
    return raw


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _key(path: Path) -> str:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        raise LiteratureError("openalex_key_file_unreadable") from None
    values = []
    for line in lines:
        match = re.fullmatch(r"\s*openalex\s*[:=]\s*([^\s]+)\s*", line, re.I)
        if match:
            values.append(match.group(1))
    if len(values) != 1 or len(values[0]) < 8:
        raise LiteratureError("expected_one_openalex_key")
    return values[0]


def _clean_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", html.unescape(value)).casefold()
    return " ".join(re.findall(r"[^\W_]+", value, flags=re.UNICODE))


def _author_tokens(value: str) -> set[str]:
    # Indexes commonly omit accents or invert "family, given" names. Compare
    # identity tokens while retaining the primary source's actual spelling.
    value = unicodedata.normalize("NFKD", html.unescape(value)).casefold()
    value = "".join(char for char in value if not unicodedata.combining(char))
    return set(re.findall(r"[^\W_]+", value, flags=re.UNICODE))


def _plain(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(html.unescape(value).split())


class _PrimaryHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta_title = ""
        self.meta_arxiv_id = ""
        self.meta_authors = []
        self.html_authors = []
        self.body = []
        self.paragraphs = []
        self._title = False
        self._skip = 0
        self._paragraph = None
        self._heading = None
        self.current_heading = ""
        self._personname = None

    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "title":
            self._title = True
        if tag == "p" and self._paragraph is None:
            self._paragraph = []
        if tag == "span" and "ltx_personname" in (props.get("class") or "").split():
            self._personname = []
        if tag in ("h1", "h2", "h3", "h4"):
            self._heading = []
        if tag == "meta":
            name = (props.get("name") or "").lower()
            content = _plain(props.get("content"))
            if name == "citation_title":
                self.meta_title = content
            elif name == "citation_arxiv_id":
                self.meta_arxiv_id = content
            elif name == "citation_author" and content:
                self.meta_authors.append(content)

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag == "title":
            self._title = False
        if tag == "p" and self._paragraph is not None:
            value = " ".join(" ".join(self._paragraph).split())
            if len(value) >= 60:
                self.paragraphs.append({"heading": self.current_heading, "text": value})
            self._paragraph = None
        if tag == "span" and self._personname is not None:
            value = " ".join(" ".join(self._personname).split())
            if value:
                self.html_authors.extend(name for part in value.split(",")
                                         if (name := re.sub(r"[\s*†‡]+$", "", part).strip()))
            self._personname = None
        if tag in ("h1", "h2", "h3", "h4") and self._heading is not None:
            self.current_heading = " ".join(" ".join(self._heading).split())[:140]
            self._heading = None

    def handle_data(self, data):
        if self._title:
            self.title += data
        if not self._skip:
            self.body.append(data)
            if self._paragraph is not None:
                self._paragraph.append(data)
            if self._heading is not None:
                self._heading.append(data)
            if self._personname is not None:
                self._personname.append(data)


def _select_excerpts(paragraphs: list[dict]) -> tuple[str, list[dict]]:
    """Deterministically take opening context and the most relevant text passages."""
    if len(paragraphs) < 3 or sum(len(p["text"]) for p in paragraphs) < 2000:
        raise LiteratureError("primary_fulltext_missing")
    terms = {"dependency": 6, "dependencies": 6, "invalidation": 6,
             "rollback": 6, "replay": 5, "cache": 4, "recovery": 4,
             "provenance": 3, "method": 3, "evaluation": 3,
             "limitation": 5, "discussion": 3, "result": 2}
    def rank(index):
        row = paragraphs[index]
        content = (row["heading"] + " " + row["text"]).casefold()
        score = sum(weight * min(content.count(word), 3) for word, weight in terms.items())
        if re.search(r"method|approach|design|limitation|discussion", row["heading"], re.I):
            score += 12
        return (-score, index)
    opening = set(range(min(2, len(paragraphs))))
    order = sorted(opening) + [i for i in sorted(range(len(paragraphs)), key=rank) if i not in opening]
    selected, used = [], 0
    for index in order:
        paragraph = paragraphs[index]
        heading = paragraph["heading"]
        piece = (f"[{heading}] " if heading else "") + paragraph["text"]
        if used + len(piece) + 2 > 11_000:
            continue
        selected.append((index, piece))
        used += len(piece) + 2
    selected.sort()
    if used < 4000:
        raise LiteratureError("primary_excerpt_insufficient")
    selection = [{"paragraph_index": index, "heading": paragraphs[index]["heading"],
                  "chars": len(piece)} for index, piece in selected]
    return "\n\n".join(piece for _, piece in selected), selection


def _primary(raw: bytes, expected_id: str, expected_title: str) -> dict:
    if len(raw) > MAX_HTML_BYTES:
        raise LiteratureError("primary_html_too_large")
    try:
        document = raw.decode("utf-8")
    except UnicodeError:
        raise LiteratureError("primary_html_not_utf8") from None
    if "<html" not in document[:10000].lower():
        raise LiteratureError("primary_html_missing")
    parser = _PrimaryHTML()
    parser.feed(document)
    title = _plain(parser.meta_title or parser.title)
    # arXiv HTML often ends its <title> with a bracketed arXiv identifier.
    title = re.sub(r"\s*\[\d{4}\.\d{4,5}(?:v\d+)?\]\s*$", "", title)
    if _clean_title(title) != _clean_title(expected_title):
        raise LiteratureError("primary_title_mismatch")
    title = re.sub(r"(?<=[,:;])(?=[^\W\d_])", " ", title)
    identifier = expected_id.removeprefix("arxiv:")
    base = identifier.split("v", 1)[0]
    if parser.meta_arxiv_id and parser.meta_arxiv_id not in (base, identifier):
        raise LiteratureError("primary_identifier_mismatch")
    if base not in document:
        raise LiteratureError("primary_identifier_missing")
    text = " ".join(" ".join(parser.body).split())
    if len(text) < 1000:
        raise LiteratureError("primary_fulltext_missing")
    excerpt, selection = _select_excerpts(parser.paragraphs)
    # The version is enforced by the requested URL and no-redirect transport.
    return {"title": title, "authors": parser.meta_authors or parser.html_authors,
            "text_sha256": _sha(text.encode("utf-8")),
            "excerpt": excerpt, "excerpt_selection": selection,
            "html_sha256": _sha(raw),
            "html_bytes": len(raw), "text_chars": len(text)}


def reconstruct_abstract(index: object) -> str | None:
    """OpenAlex abstracts are position maps; malformed maps are not guessed."""
    if index is None:
        return None
    if not isinstance(index, dict) or len(index) > 1000:
        raise LiteratureError("invalid_abstract_index")
    by_position = {}
    for token, positions in index.items():
        if (not isinstance(token, str) or not token or len(token) > 100
                or any(ord(c) < 32 for c in token)
                or not isinstance(positions, list) or len(positions) > 1000):
            raise LiteratureError("invalid_abstract_index")
        for position in positions:
            if (type(position) is not int or not 0 <= position < 5000
                    or position in by_position):
                raise LiteratureError("invalid_abstract_index")
            by_position[position] = token
    if not by_position:
        return None
    if set(by_position) != set(range(len(by_position))):
        raise LiteratureError("invalid_abstract_index")
    result = " ".join(by_position[i] for i in range(len(by_position)))
    if len(result) > 30_000:
        raise LiteratureError("invalid_abstract_index")
    return result


def _arxiv_ids(work: dict) -> set[str]:
    urls = []
    for key in ("doi",):
        if isinstance(work.get(key), str):
            urls.append(work[key])
    for location in work.get("locations") or []:
        if isinstance(location, dict):
            urls.extend(location.get(k) for k in ("landing_page_url", "pdf_url") if isinstance(location.get(k), str))
    for key in ("best_oa_location", "primary_location"):
        location = work.get(key)
        if isinstance(location, dict):
            urls.extend(location.get(k) for k in ("landing_page_url", "pdf_url") if isinstance(location.get(k), str))
    ids = set()
    for url in urls:
        parsed = urlparse(url)
        if parsed.hostname == "arxiv.org":
            match = re.fullmatch(r"/(?:abs|pdf|html)/([0-9]{4}\.[0-9]{4,5})(?:v\d+)?(?:\.pdf)?/?", parsed.path, re.I)
        elif parsed.hostname == "doi.org":
            match = re.fullmatch(r"/10\.48550/arxiv\.([0-9]{4}\.[0-9]{4,5})", parsed.path, re.I)
        else:
            match = None
        if match:
            ids.add(match.group(1))
    return ids


def _linked_to_arxiv(record: dict, identifier: str) -> bool:
    base = identifier.split("v", 1)[0]
    if base in record["arxiv_ids"]:
        return True
    doi = record.get("doi")
    return isinstance(doi, str) and doi.rstrip("/").lower().endswith("/arxiv." + base)


def _work(work: dict) -> dict | None:
    if not isinstance(work, dict):
        return None
    openalex_id = work.get("id")
    title = _plain(work.get("display_name") or work.get("title"))
    if (not isinstance(openalex_id, str) or
            not re.fullmatch(r"https://openalex\.org/W[0-9]+", openalex_id)
            or not title):
        return None
    authors = []
    for entry in work.get("authorships") or []:
        if isinstance(entry, dict) and isinstance(entry.get("author"), dict):
            name = _plain(entry["author"].get("display_name"))
            if name:
                authors.append(name)
    doi = work.get("doi")
    if doi is not None and (not isinstance(doi, str) or urlparse(doi).hostname != "doi.org"):
        doi = None
    year = work.get("publication_year")
    if type(year) is not int or not 1800 <= year <= 2100:
        year = None
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    return {"openalex_id": openalex_id, "title": title, "authors": authors,
            "year": year, "doi": doi, "abstract": abstract,
            "abstract_status": "available" if abstract else "missing",
            "arxiv_ids": sorted(_arxiv_ids(work))}


def _matching(results: list, title: str, identifier: str) -> tuple[dict | None, list[dict]]:
    records = []
    seen = set()
    for raw in results:
        record = _work(raw)
        if record is None or record["openalex_id"] in seen:
            continue
        seen.add(record["openalex_id"])
        records.append(record)
    exact = [r for r in records if _clean_title(r["title"]) == _clean_title(title)]
    if len(exact) > 1:
        linked = [r for r in exact if _linked_to_arxiv(r, identifier)]
        exact = linked if len(linked) == 1 else exact
    if len(exact) > 1:
        raise LiteratureError("ambiguous_exact_title_match")
    return (exact[0] if exact else None), records


def _search_spec(spec: dict) -> tuple[str, str, str, bool]:
    if not isinstance(spec, dict):
        raise LiteratureError("invalid_search_spec")
    identifier = spec.get("id")
    title = spec.get("title")
    query = spec.get("query", title)
    selected = spec.get("selected", True)
    if (not isinstance(identifier, str) or not ARXIV_ID.fullmatch(identifier)
            or not isinstance(title, str) or not 8 <= len(title) <= 300
            or not isinstance(query, str) or not 3 <= len(query) <= 300
            or type(selected) is not bool
            or any(ord(char) < 32 for char in title + query)):
        raise LiteratureError("invalid_search_spec")
    return identifier, " ".join(title.split()), " ".join(query.split()), selected


def build_literature(run_dir: Path, key_path: Path, searches: list[dict] | tuple[dict, ...], *, transport=None) -> dict:
    """Search chosen titles and verify versioned primary HTML before eligibility.

    `searches` contains {id, title, optional query, optional selected}. Selected
    entries must have an unambiguous exact OpenAlex title and valid primary HTML.
    A discovery-only entry records retrieval status but never enters `sources`.
    """
    if not isinstance(searches, (list, tuple)) or not 1 <= len(searches) <= MAX_SEARCHES:
        raise LiteratureError("invalid_search_count")
    parsed = [_search_spec(item) for item in searches]
    if len({row[0] for row in parsed}) != len(parsed):
        raise LiteratureError("duplicate_search_id")
    key = _key(key_path)
    fetch = transport or _network
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    raw_dir = root / "openalex_raw"
    html_dir = root / "primary_html"
    raw_dir.mkdir(exist_ok=True)
    html_dir.mkdir(exist_ok=True)
    manifest = {"schema": "openalex_literature/1", "service": "OpenAlex works search",
                "api_documentation": "https://developers.openalex.org/api-reference/works",
                "fulltext_origin": "versioned arxiv.org HTML, fetched separately",
                "sources": {}, "discovered": [], "queries": [],
                "limits": {"max_searches": MAX_SEARCHES, "results_per_query": MAX_RESULTS,
                           "timeout_seconds": TIMEOUT_SECONDS,
                           "max_search_bytes": MAX_SEARCH_BYTES,
                           "max_html_bytes": MAX_HTML_BYTES}}
    for identifier, title, query, selected in parsed:
        suffix = identifier.removeprefix("arxiv:")
        url = API + "?" + urlencode({"search": query, "per_page": MAX_RESULTS,
                                      "select": "id,display_name,doi,publication_year,authorships,abstract_inverted_index,locations,best_oa_location,primary_location",
                                      "api_key": key})
        query_audit = {"id": identifier, "query": query, "selected": selected,
                       "endpoint": API, "response_status": "pending"}
        manifest["queries"].append(query_audit)
        try:
            try:
                raw = fetch(url, TIMEOUT_SECONDS, MAX_SEARCH_BYTES, "application/json")
            except Exception:
                raise LiteratureError("literature_network_failure") from None
            if not isinstance(raw, bytes) or len(raw) > MAX_SEARCH_BYTES:
                raise LiteratureError("openalex_response_too_large")
            payload = json.loads(raw)
            results = payload.get("results")
            if not isinstance(results, list) or len(results) > MAX_RESULTS:
                raise LiteratureError("invalid_openalex_response")
            (raw_dir / f"{suffix}.json").write_bytes(raw)
            query_audit.update(response_status="ok", response_sha256=_sha(raw),
                               returned_count=len(results), reported_count=(payload.get("meta") or {}).get("count"))
            candidate, discovered = _matching(results, title, suffix)
            for item in discovered:
                manifest["discovered"].append({"query_id": identifier, **item,
                    "exact_title_match": _clean_title(item["title"]) == _clean_title(title),
                    "eligible": False})
            if candidate is None or not _linked_to_arxiv(candidate, suffix):
                # Ranking can omit an indexed work. The canonical arXiv DOI is
                # a second, bounded lookup; the original discovery response is
                # retained even when it contained no exact title match.
                canonical_doi = f"https://doi.org/10.48550/arXiv.{suffix.split('v', 1)[0]}"
                lookup_url = "https://api.openalex.org/works/" + quote(canonical_doi, safe="") + "?" + urlencode({"api_key": key})
                try:
                    doi_raw = fetch(lookup_url, TIMEOUT_SECONDS, MAX_SEARCH_BYTES, "application/json")
                except Exception:
                    raise LiteratureError("literature_network_failure") from None
                if not isinstance(doi_raw, bytes) or len(doi_raw) > MAX_SEARCH_BYTES:
                    raise LiteratureError("openalex_response_too_large")
                doi_work = json.loads(doi_raw)
                (raw_dir / f"{suffix}-doi.json").write_bytes(doi_raw)
                query_audit["canonical_doi_lookup"] = {"endpoint": "https://api.openalex.org/works/{canonical DOI}",
                    "doi": canonical_doi, "response_sha256": _sha(doi_raw)}
                candidate, direct = _matching([doi_work], title, suffix)
                if candidate is None and len(direct) == 1 and _linked_to_arxiv(direct[0], suffix):
                    # A stale index title is possible even for the canonical
                    # arXiv DOI. The primary version must still match the
                    # requested title exactly before this work is eligible.
                    candidate = direct[0]
                for item in direct:
                    manifest["discovered"].append({"query_id": identifier, "discovery_method": "canonical_doi_lookup",
                        **item, "exact_title_match": _clean_title(item["title"]) == _clean_title(title),
                        "eligible": False})
            if candidate is None:
                raise LiteratureError("exact_openalex_title_missing")
            if not _linked_to_arxiv(candidate, suffix):
                raise LiteratureError("openalex_arxiv_identifier_missing")
            primary_url = f"https://arxiv.org/html/{suffix}"
            if urlparse(primary_url).hostname != "arxiv.org":
                raise LiteratureError("primary_host_not_allowed")
            try:
                primary_raw = fetch(primary_url, TIMEOUT_SECONDS, MAX_HTML_BYTES, "text/html")
            except Exception:
                raise LiteratureError("literature_network_failure") from None
            if not isinstance(primary_raw, bytes) or len(primary_raw) > MAX_HTML_BYTES:
                raise LiteratureError("primary_html_too_large")
            primary = _primary(primary_raw, identifier, title)
            if not primary["authors"]:
                raise LiteratureError("primary_authors_missing")
            if candidate["authors"]:
                first_primary = _author_tokens(primary["authors"][0])
                first_openalex = _author_tokens(candidate["authors"][0])
                if not first_primary or not first_openalex or first_primary != first_openalex:
                    raise LiteratureError("primary_openalex_author_mismatch")
            (html_dir / f"{suffix}.html").write_bytes(primary_raw)
            query_audit.update(primary_status="verified", primary_url=primary_url,
                               primary_html_sha256=primary["html_sha256"])
            if selected:
                source = {"id": identifier, "evidence_kind": "retrieved",
                          "verification_status": "primary_fulltext",
                          "source": "OpenAlex metadata; arXiv primary HTML", "title": primary["title"],
                          "authors": primary["authors"],
                          "openalex_authors": candidate["authors"],
                          "openalex_authors_differ": [ _clean_title(a) for a in candidate["authors"] ] != [ _clean_title(a) for a in primary["authors"] ],
                          "year": candidate["year"], "doi": candidate["doi"],
                          "url": f"https://arxiv.org/abs/{suffix}", "openalex_id": candidate["openalex_id"],
                          "abstract": candidate["abstract"], "abstract_status": candidate["abstract_status"],
                          "openalex_title": candidate["title"],
                          "openalex_title_differs": _clean_title(candidate["title"]) != _clean_title(primary["title"]),
                          "openalex_identifier_linked": _linked_to_arxiv(candidate, suffix),
                          "primary_text_excerpt": primary["excerpt"],
                          "primary": {"url": primary_url, "html_sha256": primary["html_sha256"],
                                      "text_sha256": primary["text_sha256"],
                                      "text_chars": primary["text_chars"],
                                      "excerpt_selection": primary["excerpt_selection"],
                                      "excerpt_rule": "opening two paragraphs plus ranked dependency, invalidation, rollback, method, evaluation, and limitation passages; <=11000 characters",
                                      "access_status": "verified"},
                          "untrusted_data": True,
                          "coverage_limit": "OpenAlex bibliographic metadata and arXiv HTML access do not establish claim support; the writer must inspect the saved primary text."}
                source["content_sha256"] = _sha(json.dumps(source, ensure_ascii=False, sort_keys=True).encode())
                manifest["sources"][identifier] = source
            else:
                query_audit["primary_status"] = "verified_discovery_only"
        except (LiteratureError, ValueError, UnicodeError, TypeError, KeyError) as exc:
            # Never include a network exception or URL containing api_key.
            code = str(exc) if isinstance(exc, LiteratureError) else "invalid_openalex_response"
            if code not in {"literature_network_failure", "literature_response_too_large",
                            "openalex_response_too_large", "invalid_openalex_response",
                            "exact_openalex_title_missing", "ambiguous_exact_title_match",
                            "openalex_arxiv_identifier_missing", "primary_authors_missing",
                            "primary_openalex_author_mismatch",
                            "invalid_abstract_index", "primary_html_too_large",
                            "primary_html_not_utf8", "primary_html_missing",
                            "primary_title_mismatch", "primary_identifier_mismatch",
                            "primary_identifier_missing", "primary_fulltext_missing",
                            "primary_excerpt_insufficient",
                            "primary_host_not_allowed"}:
                code = "literature_retrieval_failure"
            query_audit["response_status"] = query_audit["response_status"] if query_audit["response_status"] != "pending" else "failed"
            query_audit["error"] = code
            if selected:
                (root / "literature_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
                raise LiteratureError(f"selected_source_unavailable:{identifier}:{code}") from None
    (root / "literature_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest
