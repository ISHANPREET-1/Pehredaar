"""FastAPI application exposing the endpoints listed in CLAUDE.md section 7, wrapped by Mangum for
API Gateway. Built in Phase 5.

Only two endpoints so far, enough to connect the frontend to a real local backend for the demo:
a live single domain lookup and a redacted recent findings feed read from the newest local batch
scan file. No storage layer, no queueing, no authentication, this talks straight to the existing
fetcher and detector from phases 1 and 2, no new detection logic lives here.
"""

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from pydantic import BaseModel

from pehredaar.detector import run_detector
from pehredaar.fetcher import OptedOutError, fetch_domain
from pehredaar.models import ScanResult, normalize_domain

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_OUT_DIR = Path(__file__).resolve().parents[3] / "out"
_RECENT_FEED_LIMIT = 16

# Mirrors the mapping in frontend/scripts/build-scan-sample.py, kept in sync by hand since this
# is presentation labelling, not a detection signal.
_SECTOR_LABELS = {
    "gov": "Government",
    "edu": "Education",
    "reported_2026": "Reported incident",
}

app = FastAPI(title="Pehredaar API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/domains/{domain}", response_model=ScanResult)
def get_domain(domain: str) -> ScanResult:
    """Run a live scan of one domain with the existing fetcher and detector, and return the
    ScanResult as is. Rejects anything outside the allowed suffixes in config.py."""
    try:
        normalized = normalize_domain(domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        fetch_results = fetch_domain(normalized)
    except OptedOutError as exc:
        raise HTTPException(
            status_code=403, detail=f"{normalized} is on the opt out list and will not be scanned"
        ) from exc
    except Exception as exc:  # noqa: BLE001 - surface a clean API error, not a stack trace
        logger.info(json.dumps({"domain": normalized, "status": "fetch_failed", "error": str(exc)}))
        raise HTTPException(status_code=502, detail=f"could not fetch {normalized}: {exc}") from exc

    try:
        return run_detector(normalized, fetch_results)
    except Exception as exc:  # noqa: BLE001 - a scoring failure should return an error, not crash
        logger.info(json.dumps({"domain": normalized, "status": "detector_failed", "error": str(exc)}))
        raise HTTPException(status_code=502, detail=f"could not score {normalized}: {exc}") from exc


class RecentFinding(BaseModel):
    """One redacted row for the public feed. Field names match the frontend's existing JSON shape
    directly, camelCase included, since this model exists only to describe that response."""

    sectorLabel: str
    state: str
    band: str
    score: float
    scannedAt: str


def _latest_scan_file() -> Path | None:
    candidates = sorted(_OUT_DIR.glob("scan-*.jsonl"))
    return candidates[-1] if candidates else None


@app.get("/findings/recent", response_model=list[RecentFinding])
def get_recent_findings() -> list[RecentFinding]:
    """Redacted rows from the newest local batch scan file, no domain names, matching the
    redaction rule in CLAUDE.md section 2 rule 6."""
    scan_file = _latest_scan_file()
    if scan_file is None:
        return []

    records: list[dict[str, Any]] = []
    with scan_file.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("status") == "scanned":
                records.append(row)

    records.sort(key=lambda row: row["started_at"], reverse=True)
    not_clean = [row for row in records if row.get("band") != "clean"]
    clean = [row for row in records if row.get("band") == "clean"]
    feed = (not_clean + clean)[:_RECENT_FEED_LIMIT]
    feed.sort(key=lambda row: row["started_at"], reverse=True)

    return [
        RecentFinding(
            sectorLabel=_SECTOR_LABELS.get(row.get("sector"), "Other"),
            state=row.get("state") or "",
            band=row.get("band"),
            score=round(row.get("score", 0.0), 1),
            scannedAt=row.get("started_at"),
        )
        for row in feed
    ]


handler = Mangum(app)
