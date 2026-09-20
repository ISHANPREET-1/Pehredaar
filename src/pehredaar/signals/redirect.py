"""S1. Fires when the final host differs between profiles, or a redirect chain leaves the original
domain in one profile only.
"""

from urllib.parse import urlparse

from pehredaar.models import FetchResult, Signal
from pehredaar.signals import defang_host, is_same_site, strip_www

NAME = "S1_redirect_divergence"
WEIGHT = 1.5


def evaluate(fetch_results: dict[str, FetchResult]) -> Signal:
    final_hosts: dict[str, str] = {}
    left_original_domain: dict[str, bool] = {}
    for profile_key, result in fetch_results.items():
        if result.error is not None or result.final_url is None:
            continue
        host = (urlparse(str(result.final_url)).hostname or "").lower()
        final_hosts[profile_key] = host
        left_original_domain[profile_key] = not is_same_site(result.domain, host)

    distinct_hosts = {strip_www(host) for host in final_hosts.values() if host}
    fired = len(distinct_hosts) > 1 or any(left_original_domain.values())
    evidence = {
        "final_host_by_profile": {k: defang_host(v) for k, v in final_hosts.items() if v},
        "left_original_domain_by_profile": left_original_domain,
    }
    return Signal(name=NAME, fired=fired, weight=WEIGHT, evidence=evidence)
