"""
Builds src/data/scanSample.json from the real Phase 3 batch scan output at
out/scan-*.jsonl, one level up from frontend/. Run with:

    python3 scripts/build-scan-sample.py

This is a one time data prep step for the frontend mock, not part of the
app runtime. It never writes attacker infrastructure, only our own scan
verdicts for domains in seeds/domains.csv.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "out" / "scan-20260919T113406Z.jsonl"
OUT = Path(__file__).resolve().parents[1] / "src" / "data" / "scanSample.json"

SECTOR_LABELS = {
    "gov": "Government",
    "edu": "Education",
    "reported_2026": "Reported incident",
}


def load_records():
    records = []
    with SOURCE.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("status") != "scanned":
                continue
            records.append(row)
    return records


def to_lookup_entry(row):
    return {
        "domain": row["domain"],
        "institutionName": row.get("institution_name"),
        "sectorLabel": SECTOR_LABELS.get(row.get("sector"), "Other"),
        "state": row.get("state"),
        "band": row.get("band"),
        "score": round(row.get("score", 0.0), 1),
        "injectionClass": row.get("injection_class"),
        "scannedAt": row.get("started_at"),
    }


def to_redacted_entry(row):
    return {
        "sectorLabel": SECTOR_LABELS.get(row.get("sector"), "Other"),
        "state": row.get("state"),
        "band": row.get("band"),
        "score": round(row.get("score", 0.0), 1),
        "scannedAt": row.get("started_at"),
    }


def main():
    records = load_records()
    records.sort(key=lambda r: r["started_at"], reverse=True)

    lookup = [to_lookup_entry(r) for r in records]

    not_clean = [r for r in records if r.get("band") != "clean"]
    clean = [r for r in records if r.get("band") == "clean"]
    feed_source = (not_clean + clean)[:16]
    feed_source.sort(key=lambda r: r["started_at"], reverse=True)
    recent = [to_redacted_entry(r) for r in feed_source]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "sourceScan": SOURCE.name,
                "totalScanned": len(records),
                "lookup": lookup,
                "recentFindings": recent,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {OUT} with {len(lookup)} lookup entries and {len(recent)} feed entries")


if __name__ == "__main__":
    main()
