"""One time loader: reads seeds/domains.csv and upserts a DomainState META item into DynamoDB for
each row, so the dispatcher has domains to find. Run once after `sam deploy`, before the first
manual dispatcher invocation. Requires AWS credentials for the deployed table's account and
region; talks to real AWS, not a fixture.
"""

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pehredaar.models import Band, DomainState  # noqa: E402
from pehredaar.storage import ddb  # noqa: E402

_CSV_PATH = Path(__file__).resolve().parents[1] / "seeds" / "domains.csv"


def _stored_sector(domain: str) -> str:
    """DomainState.sector is gov or edu only; reported_2026 rows are real gov/edu domains too,
    just flagged separately in the CSV for the batch runner's summary, so map by suffix here."""
    return "gov" if domain.endswith((".gov.in", ".nic.in")) else "edu"


def main() -> int:
    now = datetime.now(timezone.utc)
    count = 0
    with _CSV_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            state = DomainState(
                domain=row["domain"],
                sector=_stored_sector(row["domain"]),
                state=row["state"],
                institution_name=row["institution_name"],
                band=Band.CLEAN,
                first_seen=now,
            )
            ddb.upsert_domain_state(state)
            count += 1
    print(f"loaded {count} domains into DynamoDB table")
    return 0


if __name__ == "__main__":
    sys.exit(main())
