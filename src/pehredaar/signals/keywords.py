"""S2. Matches the gambling and pharma keyword lists from data/keywords.yaml against each profile's
visible text, records position and surrounding text, and downweights a hit that sits near a
legal_context word. A domain listed in data/allowlist.yaml is never scored by this signal.

Matching is on word boundaries, not raw substring: "satta" must not fire inside an unrelated word
like a surname ("Benchasattabuse"), only as a standalone word or inside a matched phrase.
"""

import re

from pehredaar.models import FetchResult, Signal
from pehredaar.normalize import normalize_html_to_text
from pehredaar.signals import load_data_yaml

NAME = "S2_keywords"
WEIGHT = 2.0
_CONTEXT_WINDOW = 90


def _keyword_pattern(keyword: str) -> re.Pattern:
    return re.compile(r"\b" + re.escape(keyword) + r"\b")


_KEYWORDS_DATA = load_data_yaml("keywords.yaml")
_ALLOWLIST_DATA = load_data_yaml("allowlist.yaml")
_GAMBLING = [(k.lower(), _keyword_pattern(k.lower())) for k in _KEYWORDS_DATA.get("gambling", [])]
_PHARMA = [(k.lower(), _keyword_pattern(k.lower())) for k in _KEYWORDS_DATA.get("pharma", [])]
_LEGAL_CONTEXT = [k.lower() for k in _KEYWORDS_DATA.get("legal_context", [])]
_ALLOWLISTED_DOMAINS = {d.lower() for d in _ALLOWLIST_DATA.get("domains", [])}


def _find_hits(text: str, keyword_patterns: list[tuple[str, re.Pattern]], category: str) -> list[dict]:
    hits = []
    for keyword, pattern in keyword_patterns:
        for match in pattern.finditer(text):
            window_start = max(0, match.start() - _CONTEXT_WINDOW)
            window_end = min(len(text), match.end() + _CONTEXT_WINDOW)
            context = text[window_start:window_end]
            downweighted = any(legal_word in context for legal_word in _LEGAL_CONTEXT)
            hits.append(
                {
                    "category": category,
                    "keyword": keyword,
                    "context": context.strip(),
                    "downweighted": downweighted,
                }
            )
    return hits


def _summarize_hits(hits: list[dict]) -> list[dict]:
    """Collapse repeated occurrences of the same keyword into one evidence entry with a count."""
    grouped: dict[tuple[str, str], dict] = {}
    for hit in hits:
        key = (hit["category"], hit["keyword"])
        entry = grouped.setdefault(
            key,
            {
                "category": hit["category"],
                "keyword": hit["keyword"],
                "occurrences": 0,
                "downweighted_occurrences": 0,
                "sample_context": hit["context"],
            },
        )
        entry["occurrences"] += 1
        if hit["downweighted"]:
            entry["downweighted_occurrences"] += 1
    return list(grouped.values())


def evaluate(fetch_results: dict[str, FetchResult]) -> Signal:
    domain = next(iter(fetch_results.values())).domain
    if domain.lower() in _ALLOWLISTED_DOMAINS:
        return Signal(
            name=NAME,
            fired=False,
            weight=WEIGHT,
            evidence={"skipped": "domain is on the allowlist"},
        )

    hits_by_profile: dict[str, list[dict]] = {}
    counted_hits = 0
    for profile_key, result in fetch_results.items():
        if result.error is not None or result.html is None:
            continue
        text = normalize_html_to_text(result.html)
        hits = _find_hits(text, _GAMBLING, "gambling") + _find_hits(text, _PHARMA, "pharma")
        if hits:
            hits_by_profile[profile_key] = _summarize_hits(hits)
            counted_hits += sum(1 for hit in hits if not hit["downweighted"])

    fired = counted_hits > 0
    return Signal(name=NAME, fired=fired, weight=WEIGHT, evidence={"hits_by_profile": hits_by_profile})
