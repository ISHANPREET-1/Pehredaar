"""Smoke tests for the Lambda handler entry points: event parsing and wiring, not the detection
logic itself (already covered elsewhere). fetch_domain and run_detector are monkeypatched; ddb and
s3 run against moto.
"""

import json
from datetime import datetime, timezone

import boto3
import pytest
from moto import mock_aws

from pehredaar.config import settings
from pehredaar.fetcher import OptedOutError
from pehredaar.handlers import dispatcher, worker
from pehredaar.models import Band, DomainState, FetchResult, ScanResult
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
def aws(monkeypatch):
    with mock_aws():
        _create_table()
        boto3.client("s3", region_name=settings.region).create_bucket(
            Bucket=settings.bucket_name,
            CreateBucketConfiguration={"LocationConstraint": settings.region},
        )
        boto3.client("sqs", region_name=settings.region).create_queue(QueueName="pehredaar-scan-queue")
        monkeypatch.setattr(settings, "queue_url", boto3.client("sqs", region_name=settings.region).get_queue_url(QueueName="pehredaar-scan-queue")["QueueUrl"])
        yield


def test_dispatcher_reads_due_domains_and_sends_one_message_each(aws):
    ddb.upsert_domain_state(
        DomainState(domain="example.gov.in", sector="gov", state="Test", institution_name="Test Office", first_seen=NOW)
    )
    result = dispatcher.handler({}, None)
    assert result["dispatched_count"] == 1
    assert result["domains"] == ["example.gov.in"]

    messages = boto3.client("sqs", region_name=settings.region).receive_message(QueueUrl=settings.queue_url)
    assert json.loads(messages["Messages"][0]["Body"]) == {"domain": "example.gov.in"}


def test_worker_scans_writes_snapshot_and_scan_result(aws, monkeypatch):
    # The worker only ever sees a domain the dispatcher already found in DynamoDB, so its META
    # item always exists by the time write_scan_result runs; seed it here to match that invariant.
    ddb.upsert_domain_state(
        DomainState(domain="example.gov.in", sector="gov", state="Test", institution_name="Test Office", first_seen=NOW)
    )
    fetch_results = {
        "desktop": FetchResult(
            profile_key="desktop",
            domain="example.gov.in",
            requested_url="https://example.gov.in/",
            final_url="https://example.gov.in/",
            status_code=200,
            html="<html>hello</html>",
            fetched_at=NOW,
        )
    }
    fake_result = ScanResult(
        scan_id="scan-1",
        domain="example.gov.in",
        started_at=NOW,
        finished_at=NOW,
        band=Band.CLEAN,
        score=0.0,
    )
    monkeypatch.setattr(worker, "fetch_domain", lambda domain: fetch_results)
    monkeypatch.setattr(worker, "run_detector", lambda domain, results: fake_result)

    event = {"Records": [{"body": json.dumps({"domain": "example.gov.in"})}]}
    result = worker.handler(event, None)

    assert result["processed"] == ["example.gov.in"]
    table = boto3.resource("dynamodb", region_name=settings.region).Table(settings.table_name)
    meta = table.get_item(Key={"PK": "DOMAIN#example.gov.in", "SK": "META"})["Item"]
    assert meta["band"] == "clean"
    assert meta["institution_name"] == "Test Office"  # the original META fields survived the update

    scan_item = table.get_item(Key={"PK": "DOMAIN#example.gov.in", "SK": f"SCAN#{NOW.isoformat()}"})["Item"]
    assert scan_item["scan_id"] == "scan-1"
    assert scan_item["snapshot_prefix"] == "example.gov.in/scan-1"

    s3_object = boto3.client("s3", region_name=settings.region).get_object(
        Bucket=settings.bucket_name, Key="example.gov.in/scan-1/desktop.html.gz"
    )
    assert s3_object["ContentEncoding"] == "gzip"


def test_worker_skips_opted_out_domain_without_raising(aws, monkeypatch):
    def _raise_opted_out(domain):
        raise OptedOutError(domain)

    monkeypatch.setattr(worker, "fetch_domain", _raise_opted_out)
    event = {"Records": [{"body": json.dumps({"domain": "example.gov.in"})}]}
    result = worker.handler(event, None)
    assert result["processed"] == []
