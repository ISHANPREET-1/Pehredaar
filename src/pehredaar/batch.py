"""Batch scans every domain in a seeds CSV: a global concurrency cap across domains, on top of
fetcher.py's own per host politeness within each domain's four sequential fetches. Writes one JSON
line per domain as it finishes, and survives an individual domain's failure (DNS error, timeout,
block) without stopping the run, recording the failure reason instead of crashing.
"""

import csv
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pehredaar.config import settings
from pehredaar.detector import run_detector
from pehredaar.fetcher import OptedOutError, fetch_domain

_FAILURE_PATTERNS = (
    ("dns_resolution_failed", "could not resolve"),
    ("ssrf_blocked", "disallowed address"),
    ("host_budget_exceeded", "request budget"),
    ("redirect_hops_exceeded", "redirect hops"),
    ("timeout", "timed out"),
    ("timeout", "timeout"),
    ("connection_error", "connect"),
    ("connection_error", "network"),
)


def classify_failure(error: str) -> str:
    """Group a FetchResult or exception message into a coarse failure type for the summary."""
    lowered = error.lower()
    for label, needle in _FAILURE_PATTERNS:
        if needle in lowered:
            return label
    return "other"


@dataclass
class SeedRow:
    domain: str
    sector: str
    state: str
    institution_name: str


def read_seed_rows(csv_path: Path, limit: int | None = None) -> list[SeedRow]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = [
            SeedRow(row["domain"], row["sector"], row["state"], row["institution_name"])
            for row in csv.DictReader(handle)
        ]
    return rows[:limit] if limit else rows


def scan_one(row: SeedRow) -> dict[str, Any]:
    """Scan one seed row, never raising: every outcome, including a crash, becomes a record."""
    record: dict[str, Any] = {
        "domain": row.domain,
        "sector": row.sector,
        "state": row.state,
        "institution_name": row.institution_name,
        "status": None,
        "failure_type": None,
        "failure_detail": None,
        "profiles_succeeded": 0,
        "profiles_failed": 0,
        "band": None,
        "score": None,
        "injection_class": None,
        "scan_id": None,
        "started_at": None,
        "finished_at": None,
        "signals": None,
    }
    try:
        fetch_results = fetch_domain(row.domain)
    except OptedOutError:
        record["status"] = "opted_out"
        return record
    except Exception as exc:  # noqa: BLE001 - a batch run must never die on one domain
        record["status"] = "failed"
        record["failure_type"] = classify_failure(str(exc))
        record["failure_detail"] = str(exc)
        return record

    succeeded = [r for r in fetch_results.values() if r.error is None]
    failed = [r for r in fetch_results.values() if r.error is not None]
    record["profiles_succeeded"] = len(succeeded)
    record["profiles_failed"] = len(failed)

    if not succeeded:
        first_error = failed[0].error if failed else "no profile returned a result"
        record["status"] = "failed"
        record["failure_type"] = classify_failure(first_error)
        record["failure_detail"] = first_error
        return record

    try:
        result = run_detector(row.domain, fetch_results)
    except Exception as exc:  # noqa: BLE001 - same resilience guarantee applies to scoring
        record["status"] = "failed"
        record["failure_type"] = "detector_error"
        record["failure_detail"] = str(exc)
        return record

    record["status"] = "scanned"
    record["band"] = result.band.value
    record["score"] = result.score
    record["injection_class"] = result.injection_class
    record["scan_id"] = result.scan_id
    record["started_at"] = result.started_at.isoformat()
    record["finished_at"] = result.finished_at.isoformat()
    record["signals"] = [signal.model_dump(mode="json") for signal in result.signals]
    if failed:
        record["failure_detail"] = (
            f"{len(failed)} of {len(fetch_results)} profiles failed: "
            + "; ".join(f"{r.profile_key}: {r.error}" for r in failed)
        )
    return record


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(record["status"] for record in records)
    failure_type_counts = Counter(
        record["failure_type"] for record in records if record["status"] == "failed"
    )
    band_counts = Counter(record["band"] for record in records if record["status"] == "scanned")
    findings = sorted(
        (record for record in records if record["status"] == "scanned" and record["score"]),
        key=lambda record: record["score"],
        reverse=True,
    )
    return {
        "total": len(records),
        "status_counts": dict(status_counts),
        "failure_type_counts": dict(failure_type_counts),
        "band_counts": dict(band_counts),
        "top_findings": findings,
    }


def run_batch(csv_path: Path, output_path: Path, limit: int | None = None) -> dict[str, Any]:
    """Scan every row of csv_path with a global concurrency cap, streaming one JSON line per
    domain to output_path as each finishes, then return the summary."""
    rows = read_seed_rows(csv_path, limit)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    with output_path.open("w", encoding="utf-8") as handle:
        with ThreadPoolExecutor(max_workers=settings.global_concurrency) as pool:
            futures = [pool.submit(scan_one, row) for row in rows]
            for future in as_completed(futures):
                record = future.result()
                handle.write(json.dumps(record) + "\n")
                handle.flush()
                records.append(record)
    return summarize(records)
