"""Reads and writes the pehredaar DynamoDB table: domain state and scan records, following the
single table design in CLAUDE.md section 6.

domains_due_for_scan does a full table Scan filtered to META items. That is the right call at
hundreds of domains; a GSI keyed on next-scan-time would only earn its keep at a size this project
is not at yet.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

import boto3
from boto3.dynamodb.conditions import Attr

from pehredaar.config import settings
from pehredaar.models import Band, DomainState, FetchResult, ScanResult

_SCAN_RECORD_TTL_DAYS = 30


def _table():
    return boto3.resource("dynamodb", region_name=settings.region).Table(settings.table_name)


def _to_dynamo(value: Any) -> Any:
    """DynamoDB has no native float type; recursively swap every float for a Decimal."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _to_dynamo(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_to_dynamo(val) for val in value]
    return value


def _from_dynamo(value: Any) -> Any:
    """The inverse of _to_dynamo, for reading items back into plain Python/pydantic friendly types."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _from_dynamo(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_from_dynamo(val) for val in value]
    return value


def _domain_state_item(state: DomainState) -> dict:
    return _to_dynamo(
        {
            "PK": f"DOMAIN#{state.domain}",
            "SK": "META",
            "gsi1pk": f"BAND#{state.band.value}",
            "gsi1sk": f"{state.score:06.2f}",
            "domain": state.domain,
            "sector": state.sector,
            "state": state.state,
            "institution_name": state.institution_name,
            "band": state.band.value,
            "score": state.score,
            "first_seen": state.first_seen.isoformat(),
            "last_scanned": state.last_scanned.isoformat() if state.last_scanned else None,
            "last_band_change": state.last_band_change.isoformat() if state.last_band_change else None,
            "scan_interval_hours": state.scan_interval_hours,
            "opt_out": state.opt_out,
        }
    )


def _domain_state_from_item(item: dict) -> DomainState:
    item = _from_dynamo(item)
    return DomainState(
        domain=item["domain"],
        sector=item["sector"],
        state=item["state"],
        institution_name=item["institution_name"],
        band=Band(item["band"]),
        score=item["score"],
        first_seen=item["first_seen"],
        last_scanned=item.get("last_scanned"),
        last_band_change=item.get("last_band_change"),
        scan_interval_hours=item["scan_interval_hours"],
        opt_out=item.get("opt_out", False),
    )


def upsert_domain_state(state: DomainState) -> None:
    """Write or fully replace one domain's META item. Used by the seed loader and, once a scan
    result comes back, by write_scan_result to record the new band and score."""
    _table().put_item(Item=_domain_state_item(state))


def domains_due_for_scan(now: datetime | None = None) -> list[DomainState]:
    """Every non opted out domain whose last scan is missing or older than its own interval."""
    now = now or datetime.now(timezone.utc)
    table = _table()
    due: list[DomainState] = []
    scan_kwargs: dict[str, Any] = {
        "FilterExpression": Attr("SK").eq("META") & Attr("opt_out").eq(False),
    }
    while True:
        response = table.scan(**scan_kwargs)
        for item in response.get("Items", []):
            state = _domain_state_from_item(item)
            stale = state.last_scanned is None or (
                now - state.last_scanned >= timedelta(hours=state.scan_interval_hours)
            )
            if stale:
                due.append(state)
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return due


def _profile_summary(fetch_results: list[FetchResult]) -> dict:
    summary = {}
    for result in fetch_results:
        final_host = urlparse(str(result.final_url)).hostname if result.final_url else None
        summary[result.profile_key] = {
            "status": "ok" if result.error is None else "error",
            "final_host": final_host,
            "error": result.error,
        }
    return summary


def write_scan_result(result: ScanResult) -> None:
    """Write the SCAN# record for this run and update the domain's META item with the new band,
    score and last_scanned. Does not read the previous band first: the worker has write only
    access, and detecting a band change is a job for a DynamoDB Stream reader (Phase 6), not a
    read before write here.

    Assumes the META item already exists, which always holds in the real pipeline: a domain only
    reaches the worker because the dispatcher already found its META item in domains_due_for_scan.
    If it did not exist, UpdateItem would silently create a partial one missing the required
    DomainState fields, which domains_due_for_scan would then fail to parse next cycle.
    """
    table = _table()
    ttl = int((result.finished_at + timedelta(days=_SCAN_RECORD_TTL_DAYS)).timestamp())
    table.put_item(
        Item=_to_dynamo(
            {
                "PK": f"DOMAIN#{result.domain}",
                "SK": f"SCAN#{result.finished_at.isoformat()}",
                "scan_id": result.scan_id,
                "band": result.band.value,
                "score": result.score,
                "injection_class": result.injection_class,
                "signals": [signal.model_dump(mode="json") for signal in result.signals],
                "profiles": _profile_summary(result.fetch_results),
                "snapshot_prefix": result.snapshot_prefix,
                "ttl": ttl,
            }
        )
    )
    table.update_item(
        Key={"PK": f"DOMAIN#{result.domain}", "SK": "META"},
        UpdateExpression="SET band = :band, score = :score, last_scanned = :last_scanned, "
        "gsi1pk = :gsi1pk, gsi1sk = :gsi1sk",
        ExpressionAttributeValues=_to_dynamo(
            {
                ":band": result.band.value,
                ":score": result.score,
                ":last_scanned": result.finished_at.isoformat(),
                ":gsi1pk": f"BAND#{result.band.value}",
                ":gsi1sk": f"{result.score:06.2f}",
            }
        ),
    )
