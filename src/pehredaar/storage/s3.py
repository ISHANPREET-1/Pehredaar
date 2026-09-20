"""Writes gzipped HTML snapshots and scan metadata to the pehredaar-snapshots bucket, keyed
<domain>/<scan_id>/<profile>.html.gz and <domain>/<scan_id>/meta.json, per CLAUDE.md section 6.
"""

import gzip
import json

import boto3

from pehredaar.config import settings
from pehredaar.models import FetchResult


def _client():
    return boto3.client("s3", region_name=settings.region)


def write_snapshot(domain: str, scan_id: str, fetch_results: list[FetchResult]) -> str:
    """Gzip each profile's HTML plus a meta.json to S3. Returns the snapshot key prefix."""
    prefix = f"{domain}/{scan_id}"
    client = _client()
    profiles_meta = {}
    for result in fetch_results:
        profiles_meta[result.profile_key] = {
            "status_code": result.status_code,
            "error": result.error,
            "elapsed_seconds": result.elapsed_seconds,
        }
        if result.html is None:
            continue
        client.put_object(
            Bucket=settings.bucket_name,
            Key=f"{prefix}/{result.profile_key}.html.gz",
            Body=gzip.compress(result.html.encode("utf-8")),
            ContentType="text/html",
            ContentEncoding="gzip",
        )
    client.put_object(
        Bucket=settings.bucket_name,
        Key=f"{prefix}/meta.json",
        Body=json.dumps({"domain": domain, "scan_id": scan_id, "profiles": profiles_meta}).encode("utf-8"),
        ContentType="application/json",
    )
    return prefix
