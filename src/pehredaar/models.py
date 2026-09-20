"""Pydantic v2 contracts shared by the fetcher, the signal modules, scoring, the detector and storage.

These are the boundary objects named in CLAUDE.md section 6. Nothing in this
project should pass a loose dict between modules; it should pass one of these.
"""

import ipaddress
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, Field, HttpUrl, model_validator

from pehredaar.config import settings


def normalize_domain(value: str) -> str:
    """Lowercase a domain, strip scheme, path and port, and reject IPs and out of scope suffixes."""
    text = value.strip().lower()
    if "://" in text:
        text = urlsplit(text).netloc
    text = text.split("/")[0].split("?")[0]
    if "@" in text:
        text = text.rsplit("@", 1)[-1]
    host, _, port = text.partition(":")
    if port:
        raise ValueError(f"domain must not include a port: {value!r}")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError(f"domain must not be an IP address: {value!r}")
    if not host or "." not in host:
        raise ValueError(f"not a valid domain: {value!r}")
    if not any(host.endswith(suffix) for suffix in settings.allowed_domain_suffixes):
        raise ValueError(
            f"domain {host!r} is outside the allowed suffixes {settings.allowed_domain_suffixes}"
        )
    return host


Domain = Annotated[str, AfterValidator(normalize_domain)]


class Band(str, Enum):
    """The four verdict bands a scan can land in, ordered from least to most severe."""

    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    LIKELY_COMPROMISED = "likely_compromised"
    COMPROMISED = "compromised"


class FetchProfile(BaseModel):
    """One of the four visitor identities we fetch a domain as. Defined as data in data/profiles.yaml."""

    key: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    user_agent: str = Field(min_length=1)
    extra_headers: dict[str, str] = Field(default_factory=dict)


class RedirectHop(BaseModel):
    """One hop in a redirect chain: the URL that was returned and the status that sent us there."""

    url: HttpUrl
    status_code: int = Field(ge=100, le=599)


class FetchResult(BaseModel):
    """Everything captured from fetching one domain with one profile.

    error is set and html is left None when the fetch itself failed, for
    example a timeout or a DNS failure, so downstream signal modules can
    treat a missing profile as missing evidence rather than crashing.
    """

    profile_key: str = Field(min_length=1)
    domain: Domain
    requested_url: HttpUrl
    final_url: HttpUrl | None = None
    redirect_chain: list[RedirectHop] = Field(default_factory=list)
    status_code: int | None = Field(default=None, ge=100, le=599)
    headers: dict[str, str] = Field(default_factory=dict)
    html: str | None = None
    elapsed_seconds: float | None = Field(default=None, ge=0)
    fetched_at: datetime
    error: str | None = None


class Signal(BaseModel):
    """The typed result a signal module returns. No signal module may decide a final verdict."""

    name: str = Field(min_length=1)
    fired: bool
    weight: float = Field(ge=0.0)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ScanResult(BaseModel):
    """The result of fetching a domain, running every signal and scoring it: the record for one scan."""

    scan_id: str = Field(min_length=1)
    domain: Domain
    started_at: datetime
    finished_at: datetime
    band: Band
    score: float = Field(ge=0, le=100)
    signals: list[Signal] = Field(default_factory=list)
    fetch_results: list[FetchResult] = Field(default_factory=list)
    snapshot_prefix: str | None = None
    injection_class: Literal["A", "B"] | None = None

    @model_validator(mode="after")
    def _compromised_needs_enough_signals(self) -> "ScanResult":
        if self.band == Band.COMPROMISED:
            fired = sum(1 for signal in self.signals if signal.fired)
            if fired < settings.min_signals_for_compromised:
                raise ValueError(
                    "compromised band requires at least "
                    f"{settings.min_signals_for_compromised} fired signals, got {fired}"
                )
        return self


class DomainState(BaseModel):
    """Persisted state for one seed domain: its identity plus the latest verdict."""

    domain: Domain
    sector: str = Field(pattern=r"^(gov|edu)$")
    state: str = Field(min_length=1)
    institution_name: str = Field(min_length=1)
    band: Band = Band.CLEAN
    score: float = Field(default=0.0, ge=0, le=100)
    first_seen: datetime
    last_scanned: datetime | None = None
    last_band_change: datetime | None = None
    scan_interval_hours: int = Field(default=6, gt=0)
    opt_out: bool = False
