"""Tests for pehredaar.fetcher. Every HTTP call is mocked with respx; no test touches the real
network. DNS resolution is mocked too, by monkeypatching resolve_host, so the SSRF guard is
testable without a real lookup.
"""

import ipaddress

import httpx
import pytest
import respx

from pehredaar import fetcher
from pehredaar.fetcher import (
    HostBudgetExceededError,
    OptedOutError,
    SSRFBlockedError,
    _PolitenessTracker,
    fetch_domain,
    guard_ssrf,
)
from pehredaar.models import FetchProfile

DOMAIN = "gpranipur.ac.in"
URL = f"https://{DOMAIN}/"


def _fetch_single_profile():
    """fetch_domain fetches all four profiles against the same URL, which makes respx side_effect
    lists ambiguous across profiles. Tests that care about one profile's retry or redirect
    behaviour call _fetch_profile directly instead, with a throwaway client and tracker.
    """
    profile = FetchProfile(key="desktop", user_agent="pehredaar-test/1.0")
    tracker = _PolitenessTracker()
    with httpx.Client(follow_redirects=False) as client:
        return fetcher._fetch_profile(client, DOMAIN, profile, tracker)


@pytest.fixture(autouse=True)
def _no_real_dns(monkeypatch):
    """Every test gets a safe, public looking IP for the target domain unless it overrides this."""
    monkeypatch.setattr(fetcher, "resolve_host", lambda host: [ipaddress.ip_address("93.184.216.34")])


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Backoff and politeness delays would make the suite slow; skip the actual waiting."""
    monkeypatch.setattr(fetcher.time, "sleep", lambda seconds: None)


# SSRF guard ------------------------------------------------------------


def test_guard_ssrf_blocks_private_address(monkeypatch):
    monkeypatch.setattr(fetcher, "resolve_host", lambda host: [ipaddress.ip_address("10.0.0.5")])
    with pytest.raises(SSRFBlockedError):
        guard_ssrf("internal.example")


def test_guard_ssrf_blocks_loopback_address(monkeypatch):
    monkeypatch.setattr(fetcher, "resolve_host", lambda host: [ipaddress.ip_address("127.0.0.1")])
    with pytest.raises(SSRFBlockedError):
        guard_ssrf("localhost")


def test_guard_ssrf_allows_public_address(monkeypatch):
    monkeypatch.setattr(fetcher, "resolve_host", lambda host: [ipaddress.ip_address("93.184.216.34")])
    guard_ssrf("example.gov.in")  # must not raise


def test_fetch_domain_blocks_before_any_http_call_when_ssrf(monkeypatch):
    monkeypatch.setattr(fetcher, "resolve_host", lambda host: [ipaddress.ip_address("169.254.1.1")])
    with respx.mock(assert_all_called=False) as router:
        route = router.route(host=DOMAIN).mock(return_value=httpx.Response(200))
        results = fetch_domain(DOMAIN)
    assert route.call_count == 0
    assert all(result.error and "disallowed address" in result.error for result in results.values())


# opt out -----------------------------------------------------------


def test_fetch_domain_refuses_opted_out_domain_before_any_request(monkeypatch):
    monkeypatch.setattr(fetcher, "_load_optout_domains", lambda: {DOMAIN})
    with respx.mock(assert_all_called=False) as router:
        route = router.route(host=DOMAIN).mock(return_value=httpx.Response(200))
        with pytest.raises(OptedOutError):
            fetch_domain(DOMAIN)
    assert route.call_count == 0


# basic fetch and redirect chain -----------------------------------------


@respx.mock
def test_fetch_domain_success_for_all_four_profiles():
    respx.get(URL).mock(return_value=httpx.Response(200, html="<html><body>hello</body></html>"))
    results = fetch_domain(DOMAIN)
    assert set(results.keys()) == {"desktop", "mobile", "mobile_serp", "googlebot"}
    for result in results.values():
        assert result.error is None
        assert result.status_code == 200
        assert result.html == "<html><body>hello</body></html>"


@respx.mock
def test_redirect_chain_is_recorded():
    other = "https://gpranipur.ac.in/home"
    respx.get(URL).mock(return_value=httpx.Response(302, headers={"Location": other}))
    respx.get(other).mock(return_value=httpx.Response(200, html="<html>final</html>"))
    results = fetch_domain(DOMAIN)
    result = results["desktop"]
    assert result.error is None
    assert len(result.redirect_chain) == 1
    assert result.redirect_chain[0].status_code == 302
    assert str(result.final_url) == other
    assert result.html == "<html>final</html>"


@respx.mock
def test_redirect_loop_gives_up_after_max_hops(monkeypatch):
    monkeypatch.setattr(fetcher.settings, "max_requests_per_host_per_scan", 1000)
    respx.get(URL).mock(return_value=httpx.Response(301, headers={"Location": URL}))
    results = fetch_domain(DOMAIN)
    result = results["desktop"]
    assert result.error is not None
    assert "redirect hops" in result.error
    assert len(result.redirect_chain) == fetcher.settings.max_redirect_hops


# retries -----------------------------------------------------------


@respx.mock
def test_retries_on_503_then_succeeds():
    route = respx.get(URL)
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(200, html="<html>ok</html>"),
    ]
    result = _fetch_single_profile()
    assert result.error is None
    assert result.html == "<html>ok</html>"
    assert route.call_count == 2


@respx.mock
def test_gives_up_after_max_retries_on_persistent_5xx():
    respx.get(URL).mock(return_value=httpx.Response(500))
    results = fetch_domain(DOMAIN)
    result = results["desktop"]
    assert result.error is None
    assert result.status_code == 500


@respx.mock
def test_honours_retry_after_header(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(fetcher.time, "sleep", lambda seconds: sleeps.append(seconds))
    route = respx.get(URL)
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(200, html="<html>ok</html>"),
    ]
    _fetch_single_profile()
    assert 7.0 in sleeps


# politeness: delay and request budget ------------------------------------


def test_politeness_tracker_enforces_minimum_delay(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(fetcher.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(fetcher.settings, "per_host_delay_seconds", 2.0)
    tracker = _PolitenessTracker()
    tracker.before_request("gpranipur.ac.in")
    tracker.before_request("gpranipur.ac.in")
    assert sleeps and sleeps[0] > 0


def test_politeness_tracker_enforces_request_budget(monkeypatch):
    monkeypatch.setattr(fetcher.settings, "per_host_delay_seconds", 0.0)
    monkeypatch.setattr(fetcher.settings, "max_requests_per_host_per_scan", 2)
    tracker = _PolitenessTracker()
    tracker.before_request("gpranipur.ac.in")
    tracker.before_request("gpranipur.ac.in")
    with pytest.raises(HostBudgetExceededError):
        tracker.before_request("gpranipur.ac.in")


@respx.mock
def test_fetch_domain_stops_once_host_budget_is_exhausted(monkeypatch):
    monkeypatch.setattr(fetcher.settings, "max_requests_per_host_per_scan", 1)
    respx.get(URL).mock(return_value=httpx.Response(200, html="<html>ok</html>"))
    results = fetch_domain(DOMAIN)
    succeeded = [r for r in results.values() if r.error is None]
    failed = [r for r in results.values() if r.error is not None]
    assert len(succeeded) == 1
    assert len(failed) == 3
    assert all("request budget" in r.error for r in failed)


# only GET is used --------------------------------------------------------


@respx.mock
def test_only_get_requests_are_ever_made():
    route = respx.get(URL).mock(return_value=httpx.Response(200, html="<html>ok</html>"))
    fetch_domain(DOMAIN)
    assert route.called
    assert all(call.request.method == "GET" for call in route.calls)
