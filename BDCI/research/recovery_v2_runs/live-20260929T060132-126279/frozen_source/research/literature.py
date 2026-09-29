"""Bounded Crossref metadata retrieval; all returned text is untrusted data.

API contract: https://www.crossref.org/documentation/retrieve-metadata/rest-api/
Only works with abstracts are requested. This coverage cannot establish novelty.
No model calls, credentials, full-text downloads, retries, or followed redirects.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


class LiteratureError(RuntimeError):
    """Retrieval failed; callers must stop or explicitly record missing evidence."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LiteratureError("redirect_refused")


def _fetch(url: str, timeout: float, limit: int) -> bytes:
    request = Request(url, headers={"User-Agent": "BDCI-Research-Prototype/0.1", "Accept": "application/json"})
    with build_opener(_NoRedirect).open(request, timeout=timeout) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise LiteratureError("response_byte_limit")
    return data


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _plain(value: object) -> str:
    if not isinstance(value, str):
        return ""
    parser = _Text()
    parser.feed(value)
    return " ".join(" ".join(parser.parts).split())


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _query(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 300 or any(ord(c) < 32 for c in value):
        raise LiteratureError("invalid_query")
    return " ".join(value.split())


def parse_crossref(raw: bytes, query: str, retrieved_at: str, max_results: int = 5) -> list[dict]:
    """Normalize publisher metadata; never infer a missing abstract or author."""
    try:
        document = json.loads(raw)
        if document.get("status") != "ok":
            raise ValueError()
        items = document["message"]["items"]
        if not isinstance(items, list):
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise LiteratureError("invalid_crossref_response") from exc
    records, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            continue
        doi = item.get("DOI")
        titles = item.get("title", [])
        title = _plain(titles[0]) if isinstance(titles, list) and titles else ""
        if not isinstance(doi, str) or not doi.startswith("10.") or "/" not in doi or not title or doi.lower() in seen:
            continue
        seen.add(doi.lower())
        abstract = _plain(item.get("abstract")) or None
        authors = []
        author_items = item.get("author", [])
        for author in author_items if isinstance(author_items, list) else []:
            if isinstance(author, dict):
                name = " ".join(_plain(author.get(k)) for k in ("given", "family")).strip() or _plain(author.get("name"))
                if name:
                    authors.append(name)
        year = None
        for field in ("published", "published-print", "published-online", "issued"):
            try:
                candidate = item[field]["date-parts"][0][0]
                if type(candidate) is int and 1000 <= candidate <= 3000:
                    year = candidate
                    break
            except (KeyError, TypeError, IndexError):
                pass
        record = {
            "id": "doi:" + doi.lower(), "source": "crossref", "evidence_kind": "retrieved",
            "title": title, "url": "https://doi.org/" + quote(doi, safe="/"),
            "abstract": abstract, "abstract_status": "available" if abstract else "missing",
            "authors": authors, "year": year, "retrieved_at": retrieved_at, "query": query,
            "untrusted_data": True,
            "coverage_limit": "Crossref metadata with abstracts only; relevance and novelty are unverified.",
        }
        record["content_sha256"] = _digest(record)
        records.append(record)
        if len(records) >= max_results:
            break
    return records


class LiteratureClient:
    """Persistent request budget is shared by clients using the same cache_dir.

    Failed network attempts count. Cache hits do not count. Corrupt cache fails
    closed. transport(url, timeout, max_response_bytes)->bytes is for testing.
    Each workflow should use its own cache_dir to set its own explicit budget.
    """

    def __init__(self, cache_dir: Path, *, max_queries=3, max_results=5, timeout=15,
                 max_response_bytes=1_000_000, transport=None):
        if (type(max_queries) is not int or not 1 <= max_queries <= 10 or
                type(max_results) is not int or not 1 <= max_results <= 10 or
                type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 60 or
                type(max_response_bytes) is not int or not 1024 <= max_response_bytes <= 2_000_000):
            raise ValueError("invalid_literature_limits")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_queries, self.max_results = max_queries, max_results
        self.timeout, self.max_response_bytes = timeout, max_response_bytes
        self.transport = transport or _fetch
        self.last_cache_hit = False

    def _admit(self, query: str):
        ledger = self.cache_dir / "requests.jsonl"
        with ledger.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.seek(0)
            if sum(1 for _ in handle) >= self.max_queries:
                raise LiteratureError("literature_query_limit")
            handle.write(json.dumps({"query": query, "requested_at": datetime.now(timezone.utc).isoformat(),
                                     "source": "crossref", "max_results": self.max_results}) + "\n")
            handle.flush()

    def search(self, query: str) -> list[dict]:
        query = _query(query)
        cache = self.cache_dir / (_digest({"query": query, "rows": self.max_results, "schema": 1}) + ".json")
        self.last_cache_hit = False
        if cache.exists():
            try:
                if cache.stat().st_size > self.max_response_bytes * 6 + 2048:
                    raise ValueError()
                entry = json.loads(cache.read_text(encoding="utf-8"))
                raw = entry["raw"].encode("utf-8")
                if len(raw) > self.max_response_bytes or entry["raw_sha256"] != hashlib.sha256(raw).hexdigest():
                    raise ValueError()
                if entry["query"] != query or not isinstance(entry["retrieved_at"], str):
                    raise ValueError()
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                raise LiteratureError("invalid_literature_cache") from exc
            self.last_cache_hit = True
        else:
            self._admit(query)
            url = "https://api.crossref.org/works?" + urlencode({
                "query": query, "rows": self.max_results, "filter": "has-abstract:true",
                "select": "DOI,title,abstract,author,published",
            })
            try:
                raw = self.transport(url, self.timeout, self.max_response_bytes)
                if not isinstance(raw, bytes) or len(raw) > self.max_response_bytes:
                    raise LiteratureError("response_byte_limit")
                entry = {"raw": raw.decode("utf-8"), "raw_sha256": hashlib.sha256(raw).hexdigest(),
                         "query": query, "retrieved_at": datetime.now(timezone.utc).isoformat()}
            except (OSError, UnicodeError, HTTPError, URLError) as exc:
                raise LiteratureError("literature_network_failure") from exc
            # Do not cache malformed API responses.
            parse_crossref(raw, query, entry["retrieved_at"], self.max_results)
            temporary = cache.with_suffix(".tmp")
            temporary.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
            temporary.replace(cache)
        return parse_crossref(raw, query, entry["retrieved_at"], self.max_results)


def synthetic_fixture(query: str) -> list[dict]:
    """Schema fixture only. It is NOT a paper and cannot justify a research claim."""
    record = {"id": "synthetic:fixture-1", "source": "synthetic", "evidence_kind": "synthetic",
              "title": "SYNTHETIC TEST FIXTURE — not a published paper", "url": None,
              "abstract": "Synthetic schema test only; no literature or novelty evidence.",
              "abstract_status": "synthetic", "authors": [], "year": None,
              "retrieved_at": datetime.now(timezone.utc).isoformat(), "query": _query(query),
              "untrusted_data": True, "coverage_limit": "No real source; forbidden as research evidence."}
    record["content_sha256"] = _digest(record)
    return [record]
