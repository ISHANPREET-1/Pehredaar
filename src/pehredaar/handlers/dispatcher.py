"""EventBridge Scheduler triggered Lambda that reads domains due for a scan from DynamoDB and
pushes one SQS message per domain, one domain per message, for the worker to pick up.
"""

import json
import logging

import boto3

from pehredaar.config import settings
from pehredaar.storage import ddb

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict, context: object) -> dict:
    due = ddb.domains_due_for_scan()
    queue = boto3.client("sqs", region_name=settings.region)
    dispatched = []
    for state in due:
        queue.send_message(QueueUrl=settings.queue_url, MessageBody=json.dumps({"domain": state.domain}))
        dispatched.append(state.domain)
    logger.info(json.dumps({"dispatched_count": len(dispatched)}))
    return {"dispatched_count": len(dispatched), "domains": dispatched}
