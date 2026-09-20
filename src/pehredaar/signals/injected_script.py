"""S7. Fires, at low weight, on a script src host that is neither the site's own host nor on the
cdn_hosts allowlist in data/allowlist.yaml.
"""

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from pehredaar.models import FetchResult, Signal
from pehredaar.signals import defang_host, is_same_site, load_data_yaml

NAME = "S7_injected_script"
WEIGHT = 0.75

_ALLOWLIST_DATA = load_data_yaml("allowlist.yaml")
_CDN_HOSTS = {h.lower() for h in _ALLOWLIST_DATA.get("cdn_hosts", [])}


def _untrusted_script_hosts(html: str, domain: str, base_url: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    hosts = set()
    for script in soup.find_all("script", src=True):
        src = script["src"].strip()
        if not src:
            continue
        host = (urlparse(urljoin(base_url, src)).hostname or "").lower()
        if not host or is_same_site(domain, host) or host in _CDN_HOSTS:
            continue
        hosts.add(host)
    return hosts


def evaluate(fetch_results: dict[str, FetchResult]) -> Signal:
    hosts_by_profile: dict[str, list[str]] = {}
    for profile_key, result in fetch_results.items():
        if result.error is not None or result.html is None:
            continue
        hosts = _untrusted_script_hosts(result.html, result.domain, str(result.requested_url))
        if hosts:
            hosts_by_profile[profile_key] = sorted(defang_host(h) for h in hosts)

    fired = len(hosts_by_profile) > 0
    return Signal(name=NAME, fired=fired, weight=WEIGHT, evidence={"untrusted_script_hosts_by_profile": hosts_by_profile})
