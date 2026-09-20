"""One rejection test per model in pehredaar.models, proving that validation actually rejects bad
input rather than passing it through.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from pehredaar.models import (
    Band,
    DomainState,
    FetchProfile,
    FetchResult,
    RedirectHop,
    ScanResult,
    Signal,
)

NOW = datetime.now(timezone.utc)


def test_band_rejects_unknown_value():
    with pytest.raises(ValueError):
        Band("not_a_band")


def test_fetch_profile_rejects_empty_user_agent():
    with pytest.raises(ValidationError):
        FetchProfile(key="desktop", user_agent="")


def test_redirect_hop_rejects_out_of_range_status_code():
    with pytest.raises(ValidationError):
        RedirectHop(url="https://example.gov.in/", status_code=999)


def test_fetch_result_rejects_ip_address_domain():
    with pytest.raises(ValidationError):
        FetchResult(
            profile_key="desktop",
            domain="192.168.1.1",
            requested_url="https://192.168.1.1/",
            fetched_at=NOW,
        )


def test_signal_rejects_negative_weight():
    with pytest.raises(ValidationError):
        Signal(name="S2", fired=True, weight=-1.0)


def test_scan_result_rejects_compromised_band_with_one_signal():
    weak_signal = Signal(name="S2", fired=True, weight=1.0)
    with pytest.raises(ValidationError):
        ScanResult(
            scan_id="scan-1",
            domain="example.gov.in",
            started_at=NOW,
            finished_at=NOW,
            band=Band.COMPROMISED,
            score=80,
            signals=[weak_signal],
        )


def test_domain_state_rejects_unknown_sector():
    with pytest.raises(ValidationError):
        DomainState(
            domain="example.ac.in",
            sector="other",
            state="Punjab",
            institution_name="Example College",
            first_seen=NOW,
        )
