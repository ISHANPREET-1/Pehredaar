"""Orchestrates one scan of one domain: run every signal module against four already fetched
profiles, score the result, classify cloaked versus persistent injection, and assemble a
ScanResult. Takes FetchResults in; fetcher.py is what will produce them in Phase 2.
"""

import uuid
from datetime import datetime, timezone

from pehredaar.models import FetchResult, Band, ScanResult, Signal
from pehredaar.scoring import decide
from pehredaar.signals import ALL_SIGNALS

_SPAM_EVIDENCE_SIGNALS = ("S2_keywords", "S5_hidden_text")


def _classify_injection(signals: list[Signal], total_profiles: int) -> str | None:
    """Class A: spam shows up in some profiles and not others. Class B: it shows up in all of them."""
    profiles_with_spam: set[str] = set()
    for signal in signals:
        if signal.name in _SPAM_EVIDENCE_SIGNALS:
            profiles_with_spam.update(signal.evidence.get("hits_by_profile", {}).keys())

    if not profiles_with_spam or total_profiles == 0:
        return None
    return "B" if len(profiles_with_spam) >= total_profiles else "A"


def run_detector(domain: str, fetch_results: dict[str, FetchResult]) -> ScanResult:
    """Run every signal module against one domain's four fetches and assemble a ScanResult."""
    started_at = datetime.now(timezone.utc)
    signals = [evaluate(fetch_results) for evaluate in ALL_SIGNALS]
    score, band = decide(signals)
    injection_class = _classify_injection(signals, len(fetch_results)) if band != Band.CLEAN else None
    finished_at = datetime.now(timezone.utc)

    return ScanResult(
        scan_id=str(uuid.uuid4()),
        domain=domain,
        started_at=started_at,
        finished_at=finished_at,
        band=band,
        score=score,
        signals=signals,
        fetch_results=list(fetch_results.values()),
        injection_class=injection_class,
    )
