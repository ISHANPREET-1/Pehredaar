"""Tests for pehredaar.batch: failure classification, that scan_one never raises, and that the
summary groups failures, bands and findings correctly.
"""

from datetime import datetime, timezone

import pytest

from pehredaar import batch
from pehredaar.batch import SeedRow, classify_failure, scan_one, summarize
from pehredaar.fetcher import OptedOutError
from pehredaar.models import Band, FetchResult, ScanResult, Signal

ROW = SeedRow(domain="example.gov.in", sector="gov", state="Test State", institution_name="Test Office")
NOW = datetime.now(timezone.utc)


@pytest.mark.parametrize(
    "error,expected",
    [
        ("could not resolve example.gov.in: [Errno 8] nodename nor servname provided", "dns_resolution_failed"),
        ("example.gov.in resolves to a disallowed address: 10.0.0.5", "ssrf_blocked"),
        ("example.gov.in has exceeded its request budget for this scan", "host_budget_exceeded"),
        ("exceeded 10 redirect hops", "redirect_hops_exceeded"),
        ("something something Timeout", "timeout"),
        ("ConnectError: connection refused", "connection_error"),
        ("a completely unrelated message", "other"),
    ],
)
def test_classify_failure(error, expected):
    assert classify_failure(error) == expected


def _fetch_result(error: str | None, html: str | None = "<html>ok</html>") -> FetchResult:
    return FetchResult(
        profile_key="desktop",
        domain=ROW.domain,
        requested_url=f"https://{ROW.domain}/",
        final_url=f"https://{ROW.domain}/" if error is None else None,
        status_code=200 if error is None else None,
        html=html if error is None else None,
        fetched_at=NOW,
        error=error,
    )


def test_scan_one_records_opted_out(monkeypatch):
    monkeypatch.setattr(batch, "fetch_domain", lambda domain: (_ for _ in ()).throw(OptedOutError(domain)))
    record = scan_one(ROW)
    assert record["status"] == "opted_out"


def test_scan_one_records_total_failure_without_running_detector(monkeypatch):
    monkeypatch.setattr(
        batch,
        "fetch_domain",
        lambda domain: {"desktop": _fetch_result("could not resolve example.gov.in")},
    )
    record = scan_one(ROW)
    assert record["status"] == "failed"
    assert record["failure_type"] == "dns_resolution_failed"
    assert record["band"] is None


def test_scan_one_never_raises_on_unexpected_exception(monkeypatch):
    def _boom(domain):
        raise RuntimeError("something broke")

    monkeypatch.setattr(batch, "fetch_domain", _boom)
    record = scan_one(ROW)  # must not raise
    assert record["status"] == "failed"
    assert record["failure_type"] == "other"


def test_scan_one_runs_detector_on_success(monkeypatch):
    monkeypatch.setattr(batch, "fetch_domain", lambda domain: {"desktop": _fetch_result(None)})
    fake_result = ScanResult(
        scan_id="scan-1",
        domain=ROW.domain,
        started_at=NOW,
        finished_at=NOW,
        band=Band.CLEAN,
        score=0.0,
        signals=[Signal(name="S2_keywords", fired=False, weight=2.0)],
    )
    monkeypatch.setattr(batch, "run_detector", lambda domain, fetch_results: fake_result)
    record = scan_one(ROW)
    assert record["status"] == "scanned"
    assert record["band"] == "clean"
    assert record["signals"][0]["name"] == "S2_keywords"


def test_summarize_groups_status_bands_and_findings():
    records = [
        {"status": "scanned", "band": "clean", "score": 0.0},
        {"status": "scanned", "band": "compromised", "score": 91.2},
        {"status": "failed", "band": None, "score": None, "failure_type": "dns_resolution_failed"},
        {"status": "opted_out", "band": None, "score": None},
    ]
    summary = summarize(records)
    assert summary["total"] == 4
    assert summary["status_counts"] == {"scanned": 2, "failed": 1, "opted_out": 1}
    assert summary["failure_type_counts"] == {"dns_resolution_failed": 1}
    assert summary["band_counts"] == {"clean": 1, "compromised": 1}
    assert [r["score"] for r in summary["top_findings"]] == [91.2]
