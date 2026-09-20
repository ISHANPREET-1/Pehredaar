"""Tests for pehredaar.storage.ddb against a moto mocked DynamoDB table, never a real one.
"""

from datetime import datetime, timedelta, timezone

import boto3
import pytest
from moto import mock_aws

from pehredaar.config import settings
from pehredaar.models import Band, DomainState, FetchResult, ScanResult, Signal
from pehredaar.storage import ddb

NOW = datetime.now(timezone.utc)


def _create_table():
    client = boto3.client("dynamodb", region_name=settings.region)
    client.create_table(
        TableName=settings.table_name,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "gsi1pk", "AttributeType": "S"},
            {"AttributeName": "gsi1sk", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "GSI1",
                "KeySchema": [
                    {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                    {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )


@pytest.fixture
def ddb_table():
    with mock_aws():
        _create_table()
        yield


def _domain_state(domain: str, **overrides) -> DomainState:
    defaults = dict(
        domain=domain,
        sector="gov",
        state="Test State",
        institution_name="Test Office",
        first_seen=NOW,
    )
    defaults.update(overrides)
    return DomainState(**defaults)


def test_upsert_and_due_for_scan_finds_never_scanned_domain(ddb_table):
    ddb.upsert_domain_state(_domain_state("example.gov.in"))
    due = ddb.domains_due_for_scan(now=NOW)
    assert [state.domain for state in due] == ["example.gov.in"]


def test_due_for_scan_excludes_opted_out_domain(ddb_table):
    ddb.upsert_domain_state(_domain_state("example.gov.in", opt_out=True))
    due = ddb.domains_due_for_scan(now=NOW)
    assert due == []


def test_due_for_scan_excludes_recently_scanned_domain(ddb_table):
    ddb.upsert_domain_state(
        _domain_state("example.gov.in", last_scanned=NOW - timedelta(hours=1), scan_interval_hours=6)
    )
    due = ddb.domains_due_for_scan(now=NOW)
    assert due == []


def test_due_for_scan_includes_domain_past_its_interval(ddb_table):
    ddb.upsert_domain_state(
        _domain_state("example.gov.in", last_scanned=NOW - timedelta(hours=7), scan_interval_hours=6)
    )
    due = ddb.domains_due_for_scan(now=NOW)
    assert [state.domain for state in due] == ["example.gov.in"]


def test_write_scan_result_updates_domain_meta_band_and_score(ddb_table):
    ddb.upsert_domain_state(_domain_state("example.gov.in"))
    fetch_result = FetchResult(
        profile_key="desktop",
        domain="example.gov.in",
        requested_url="https://example.gov.in/",
        final_url="https://example.gov.in/",
        status_code=200,
        html="<html>ok</html>",
        fetched_at=NOW,
    )
    result = ScanResult(
        scan_id="scan-1",
        domain="example.gov.in",
        started_at=NOW,
        finished_at=NOW,
        band=Band.SUSPICIOUS,
        score=42.0,
        signals=[Signal(name="S2_keywords", fired=True, weight=2.0)],
        fetch_results=[fetch_result],
    )
    ddb.write_scan_result(result)

    table = boto3.resource("dynamodb", region_name=settings.region).Table(settings.table_name)
    meta = table.get_item(Key={"PK": "DOMAIN#example.gov.in", "SK": "META"})["Item"]
    assert meta["band"] == "suspicious"
    assert float(meta["score"]) == 42.0
    assert meta["gsi1pk"] == "BAND#suspicious"

    scan_item = table.get_item(Key={"PK": "DOMAIN#example.gov.in", "SK": f"SCAN#{NOW.isoformat()}"})["Item"]
    assert scan_item["scan_id"] == "scan-1"
    assert scan_item["profiles"]["desktop"]["status"] == "ok"
    assert scan_item["profiles"]["desktop"]["final_host"] == "example.gov.in"
