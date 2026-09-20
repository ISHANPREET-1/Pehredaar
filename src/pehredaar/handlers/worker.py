"""SQS triggered Lambda that runs detector.py for one domain, writes snapshots to S3, and writes
the scan and updated domain state to DynamoDB. One SQS message is one domain.
"""

import json
import logging

from pehredaar.detector import run_detector
from pehredaar.fetcher import OptedOutError, fetch_domain
from pehredaar.storage import ddb, s3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _scan_one_domain(domain: str) -> None:
    fetch_results = fetch_domain(domain)
    result = run_detector(domain, fetch_results)
    snapshot_prefix = s3.write_snapshot(domain, result.scan_id, list(fetch_results.values()))
    result = result.model_copy(update={"snapshot_prefix": snapshot_prefix})
    ddb.write_scan_result(result)
    logger.info(
        json.dumps(
            {
                "domain": domain,
                "scan_id": result.scan_id,
                "band": result.band.value,
                "score": result.score,
                "snapshot_prefix": snapshot_prefix,
            }
        )
    )


def handler(event: dict, context: object) -> dict:
    processed = []
    for record in event.get("Records", []):
        body = json.loads(record["body"])
        domain = body["domain"]
        try:
            _scan_one_domain(domain)
        except OptedOutError:
            logger.info(json.dumps({"domain": domain, "status": "opted_out"}))
            continue
        processed.append(domain)
    return {"processed": processed}
