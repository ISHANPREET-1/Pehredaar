"""Fetches a domain as each of the four profiles in data/profiles.yaml: builds the request, walks
the redirect chain by hand since httpx is configured with follow_redirects=False, enforces the per
host delay and the per scan request cap from config.py, retries on 429 and 5xx with backoff and
jitter, and refuses private and loopback addresses after DNS resolution.

Only GET is ever issued here. Rule 1 in CLAUDE.md section 2 is read only, always.
"""

import ipaddress
import random
import socket
import time
import yaml
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from pehredaar.config import settings
from pehredaar.models import FetchProfile, FetchResult, RedirectHop

_DATA_DIR = Path(__file__).resolve().parent / "data"
_SEEDS_DIR = Path(__file__).resolve().parents[2] / "seeds"
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class FetcherError(Exception):
    """Base class for this module's own exceptions."""


class OptedOutError(FetcherError):
    """Raised when a domain is listed in seeds/optout.txt. Never fetched, not even once."""


class SSRFBlockedError(FetcherError):
    """Raised when a hostname resolves to a private, loopback, link local or reserved address."""


class DNSResolutionError(FetcherError):
    """Raised when a hostname cannot be resolved at all."""


class HostBudgetExceededError(FetcherError):
    """Raised once a host has already received max_requests_per_host_per_scan requests this scan."""


def resolve_host(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve a hostname to its IP addresses. A standalone function so tests can mock DNS."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise DNSResolutionError(f"could not resolve {hostname}: {exc}") from exc
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def _is_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def guard_ssrf(hostname: str) -> None:
    """Resolve hostname first and refuse to proceed if any address it resolves to is unsafe.

    Required by CLAUDE.md section 10: the fetcher must refuse private and loopback ranges after
    DNS resolution, to prevent SSRF through a redirect or through the on demand scan endpoint.
    """
    addresses = resolve_host(hostname)
    unsafe = [str(ip) for ip in addresses if _is_unsafe_ip(ip)]
    if unsafe:
        raise SSRFBlockedError(f"{hostname} resolves to a disallowed address: {', '.join(unsafe)}")


class _HostState:
    def __init__(self) -> None:
        self.request_count = 0
        self.last_request_at: float | None = None


class _PolitenessTracker:
    """Tracks, per host, the minimum delay between requests and the hard request cap for a scan."""

    def __init__(self) -> None:
        self._hosts: dict[str, _HostState] = {}

    def before_request(self, host: str) -> None:
        state = self._hosts.setdefault(host, _HostState())
        if state.request_count >= settings.max_requests_per_host_per_scan:
            raise HostBudgetExceededError(
                f"{host} has exceeded its request budget for this scan "
                f"({state.request_count} requests already made)"
            )
        if state.last_request_at is not None:
            remaining = settings.per_host_delay_seconds - (time.monotonic() - state.last_request_at)
            if remaining > 0:
                time.sleep(remaining)
        state.request_count += 1
        state.last_request_at = time.monotonic()


def _load_profiles() -> list[FetchProfile]:
    with (_DATA_DIR / "profiles.yaml").open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return [FetchProfile(**entry) for entry in data.get("profiles", [])]


def _load_optout_domains() -> set[str]:
    optout_path = _SEEDS_DIR / "optout.txt"
    if not optout_path.exists():
        return set()
    return {
        line.strip().lower()
        for line in optout_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def _backoff_seconds(attempt: int) -> float:
    base = 2**attempt
    return base + random.uniform(0, base * 0.5)


def _retry_delay_seconds(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    return _backoff_seconds(attempt)


def _fetch_one_hop(client: httpx.Client, url: str, headers: dict[str, str], tracker: _PolitenessTracker) -> httpx.Response:
    """Fetch one URL, retrying on a transport error, a 429 or a 5xx, up to max_fetch_retries times."""
    host = urlparse(url).hostname or ""
    guard_ssrf(host)
    for attempt in range(settings.max_fetch_retries + 1):
        tracker.before_request(host)
        try:
            response = client.get(url, headers=headers)
        except httpx.TransportError:
            if attempt < settings.max_fetch_retries:
                time.sleep(_backoff_seconds(attempt))
                continue
            raise
        if response.status_code == 429 or 500 <= response.status_code < 600:
            if attempt < settings.max_fetch_retries:
                time.sleep(_retry_delay_seconds(response, attempt))
                continue
        return response


def _fetch_profile(client: httpx.Client, domain: str, profile: FetchProfile, tracker: _PolitenessTracker) -> FetchResult:
    requested_url = f"https://{domain}/"
    url = requested_url
    redirect_chain: list[RedirectHop] = []
    headers = {"User-Agent": profile.user_agent, **profile.extra_headers}
    started = time.monotonic()

    try:
        for _ in range(settings.max_redirect_hops):
            response = _fetch_one_hop(client, url, headers, tracker)
            if response.status_code in _REDIRECT_STATUSES and "location" in response.headers:
                redirect_chain.append(RedirectHop(url=url, status_code=response.status_code))
                url = urljoin(url, response.headers["location"])
                continue
            return FetchResult(
                profile_key=profile.key,
                domain=domain,
                requested_url=requested_url,
                final_url=url,
                redirect_chain=redirect_chain,
                status_code=response.status_code,
                headers=dict(response.headers),
                html=response.text,
                elapsed_seconds=round(time.monotonic() - started, 3),
                fetched_at=datetime.now(timezone.utc),
            )
        return FetchResult(
            profile_key=profile.key,
            domain=domain,
            requested_url=requested_url,
            redirect_chain=redirect_chain,
            elapsed_seconds=round(time.monotonic() - started, 3),
            fetched_at=datetime.now(timezone.utc),
            error=f"exceeded {settings.max_redirect_hops} redirect hops",
        )
    except (SSRFBlockedError, DNSResolutionError, HostBudgetExceededError, httpx.TransportError) as exc:
        return FetchResult(
            profile_key=profile.key,
            domain=domain,
            requested_url=requested_url,
            redirect_chain=redirect_chain,
            elapsed_seconds=round(time.monotonic() - started, 3),
            fetched_at=datetime.now(timezone.utc),
            error=str(exc) or exc.__class__.__name__,
        )


def fetch_domain(domain: str) -> dict[str, FetchResult]:
    """Fetch one domain as all four profiles from data/profiles.yaml, sequentially and politely.

    Checks seeds/optout.txt before anything else, so an opted out domain is never contacted.
    """
    if domain.lower() in _load_optout_domains():
        raise OptedOutError(domain)

    profiles = _load_profiles()
    tracker = _PolitenessTracker()
    timeout = httpx.Timeout(
        connect=settings.connect_timeout_seconds,
        read=settings.read_timeout_seconds,
        write=settings.read_timeout_seconds,
        pool=settings.read_timeout_seconds,
    )
    results: dict[str, FetchResult] = {}
    with httpx.Client(follow_redirects=False, timeout=timeout) as client:
        for profile in profiles:
            results[profile.key] = _fetch_profile(client, domain, profile, tracker)
    return results
