"""S3. Fires on external link hosts that are present in one profile's page and absent from the
others.
"""

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from pehredaar.models import FetchResult, Signal
from pehredaar.signals import defang_host, is_same_site

NAME = "S3_outbound_divergence"
WEIGHT = 1.0
_SKIP_SCHEMES = ("#", "mailto:", "tel:", "javascript:")


def _external_hosts(html: str, domain: str, base_url: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    hosts = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(_SKIP_SCHEMES):
            continue
        host = (urlparse(urljoin(base_url, href)).hostname or "").lower()
        if host and not is_same_site(domain, host):
            hosts.add(host)
    return hosts


def evaluate(fetch_results: dict[str, FetchResult]) -> Signal:
    hosts_by_profile: dict[str, set[str]] = {}
    for profile_key, result in fetch_results.items():
        if result.error is not None or result.html is None:
            continue
        hosts_by_profile[profile_key] = _external_hosts(result.html, result.domain, str(result.requested_url))

    all_hosts: set[str] = set().union(*hosts_by_profile.values()) if hosts_by_profile else set()
    divergent = {
        host
        for host in all_hosts
        if any(host in hosts for hosts in hosts_by_profile.values())
        and any(host not in hosts for hosts in hosts_by_profile.values())
    }
    fired = len(divergent) > 0
    evidence = {
        "external_hosts_by_profile": {k: sorted(defang_host(h) for h in v) for k, v in hosts_by_profile.items()},
        "divergent_hosts": sorted(defang_host(h) for h in divergent),
    }
    return Signal(name=NAME, fired=fired, weight=WEIGHT, evidence=evidence)
