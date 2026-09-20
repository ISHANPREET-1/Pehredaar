"""Command line entry point, python -m pehredaar.cli, for scanning a single domain against a
fixture or against a live host and printing a verdict. The only module in this project allowed to
use print.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pehredaar.batch import run_batch
from pehredaar.detector import run_detector
from pehredaar.fetcher import OptedOutError, fetch_domain
from pehredaar.models import FetchResult, ScanResult, normalize_domain

_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
_OUT_DIR = Path(__file__).resolve().parents[2] / "out"
_PROFILE_KEYS = ("desktop", "mobile", "mobile_serp", "googlebot")


def load_fixture(name: str) -> tuple[str, dict[str, FetchResult]]:
    """Load one tests/fixtures/<name>/ scenario into FetchResults, for fully offline detection."""
    fixture_dir = _FIXTURES_DIR / name
    domain = (fixture_dir / "domain.txt").read_text(encoding="utf-8").strip()
    fetched_at = datetime.now(timezone.utc)
    fetch_results = {}
    for profile_key in _PROFILE_KEYS:
        html = (fixture_dir / f"{profile_key}.html").read_text(encoding="utf-8")
        url = f"https://{domain}/"
        fetch_results[profile_key] = FetchResult(
            profile_key=profile_key,
            domain=domain,
            requested_url=url,
            final_url=url,
            status_code=200,
            html=html,
            elapsed_seconds=0.0,
            fetched_at=fetched_at,
        )
    return domain, fetch_results


def _write_report(result: ScanResult) -> Path:
    """Write the full ScanResult as JSON to ./out/, for a live scan to leave behind evidence."""
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = result.started_at.strftime("%Y%m%dT%H%M%SZ")
    report_path = _OUT_DIR / f"{result.domain}-{timestamp}.json"
    report_path.write_text(result.model_dump_json(indent=2))
    return report_path


def _print_verdict(domain: str, result: ScanResult) -> None:
    print(f"domain: {domain}")
    print(f"band: {result.band.value}")
    print(f"score: {result.score}")
    print(f"injection class: {result.injection_class or 'n/a'}")
    print("signals:")
    for signal in result.signals:
        marker = "FIRED" if signal.fired else "clean"
        print(f"  [{marker}] {signal.name} (weight {signal.weight})")
        if signal.fired:
            print(f"          evidence: {json.dumps(signal.evidence, default=str)}")


def _print_batch_summary(summary: dict, output_path: Path) -> None:
    print(f"scanned: {summary['total']} domains")
    print("status:")
    for status, count in sorted(summary["status_counts"].items(), key=lambda kv: kv[0] or ""):
        print(f"  {status}: {count}")
    if summary["failure_type_counts"]:
        print("failure types:")
        for failure_type, count in sorted(summary["failure_type_counts"].items(), key=lambda kv: -kv[1]):
            print(f"  {failure_type}: {count}")
    print("bands:")
    for band, count in sorted(summary["band_counts"].items(), key=lambda kv: kv[0] or ""):
        print(f"  {band}: {count}")
    print(f"top findings ({len(summary['top_findings'])} domains with a nonzero score):")
    for record in summary["top_findings"][:15]:
        print(
            f"  {record['domain']:35} band={record['band']:20} score={record['score']:6} "
            f"class={record['injection_class'] or 'n/a'}"
        )
    print(f"full results written to {output_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pehredaar.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan_parser = subparsers.add_parser("scan", help="Scan a domain and print a verdict")
    scan_parser.add_argument("domain", nargs="?", help="Live domain to scan")
    scan_parser.add_argument("--fixture", help="Name of a tests/fixtures/ scenario to scan offline")

    batch_parser = subparsers.add_parser("batch", help="Scan every domain in a seeds CSV")
    batch_parser.add_argument("csv_path", help="Path to a seeds CSV with a domain column")
    batch_parser.add_argument("--limit", type=int, default=None, help="Only scan the first N rows")

    args = parser.parse_args(argv)

    if args.command == "batch":
        csv_path = Path(args.csv_path)
        if not csv_path.exists():
            print(f"no such file: {csv_path}", file=sys.stderr)
            return 2
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = _OUT_DIR / f"scan-{timestamp}.jsonl"
        summary = run_batch(csv_path, output_path, limit=args.limit)
        _print_batch_summary(summary, output_path)
        return 0

    if args.command != "scan":
        return 1

    live = False
    if args.fixture:
        domain, fetch_results = load_fixture(args.fixture)
    elif args.domain:
        try:
            domain = normalize_domain(args.domain)
        except ValueError as exc:
            print(f"invalid domain: {exc}", file=sys.stderr)
            return 2
        try:
            fetch_results = fetch_domain(domain)
        except OptedOutError:
            print(f"{domain} is on the opt out list, refusing to scan", file=sys.stderr)
            return 3
        live = True
    else:
        print("pass a domain or --fixture NAME", file=sys.stderr)
        return 2

    result = run_detector(domain, fetch_results)
    _print_verdict(domain, result)
    if live:
        report_path = _write_report(result)
        print(f"report written to {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
