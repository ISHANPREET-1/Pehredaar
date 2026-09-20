"""One fires and one does not fire test per signal module in pehredaar.signals. Each module reads
its data from data/keywords.yaml and data/allowlist.yaml, nothing is hardcoded here.
"""

from datetime import datetime, timezone

from pehredaar.models import FetchResult
from pehredaar.signals import hidden, injected_script, keywords, outbound, redirect, similarity, title

NOW = datetime.now(timezone.utc)
PROFILE_KEYS = ("desktop", "mobile", "mobile_serp", "googlebot")


def make_fetch_map(
    domain: str,
    html_by_profile: dict[str, str],
    final_url_by_profile: dict[str, str] | None = None,
) -> dict[str, FetchResult]:
    final_url_by_profile = final_url_by_profile or {}
    fetch_results = {}
    for profile_key in PROFILE_KEYS:
        html = html_by_profile.get(profile_key, html_by_profile["desktop"])
        fetch_results[profile_key] = FetchResult(
            profile_key=profile_key,
            domain=domain,
            requested_url=f"https://{domain}/",
            final_url=final_url_by_profile.get(profile_key, f"https://{domain}/"),
            status_code=200,
            html=html,
            fetched_at=NOW,
        )
    return fetch_results


CLEAN_HTML = "<html><head><title>Clean Page</title></head><body><p>Nothing unusual here.</p></body></html>"


# S1 redirect ----------------------------------------------------------------


def test_redirect_fires_when_final_host_diverges():
    fetch_results = make_fetch_map(
        "gpranipur.ac.in",
        {"desktop": CLEAN_HTML},
        final_url_by_profile={"mobile_serp": "https://sattaplay247.xyz/"},
    )
    signal = redirect.evaluate(fetch_results)
    assert signal.fired is True


def test_redirect_does_not_fire_when_all_hosts_match():
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": CLEAN_HTML})
    signal = redirect.evaluate(fetch_results)
    assert signal.fired is False


def test_redirect_does_not_fire_when_www_seed_redirects_to_bare_apex():
    """Regression: www.iiits.ac.in redirecting to iiits.ac.in is the same site, not a departure."""
    fetch_results = make_fetch_map(
        "www.iiits.ac.in",
        {"desktop": CLEAN_HTML},
        final_url_by_profile={key: "https://iiits.ac.in/" for key in PROFILE_KEYS},
    )
    signal = redirect.evaluate(fetch_results)
    assert signal.fired is False


# S2 keywords ------------------------------------------------------------


def test_keywords_fires_on_gambling_terms():
    html = "<html><body><p>Play satta matka and teen patti online now.</p></body></html>"
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": CLEAN_HTML, "mobile_serp": html})
    signal = keywords.evaluate(fetch_results)
    assert signal.fired is True


def test_keywords_does_not_fire_on_clean_text():
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": CLEAN_HTML})
    signal = keywords.evaluate(fetch_results)
    assert signal.fired is False


def test_keywords_downweights_legal_context():
    html = (
        "<html><body><p>Satta matka is banned under the Public Gambling Act. Police "
        "arrested persons running satta matka and registered an FIR under the "
        "relevant Section; assets were seized as part of the prohibition.</p></body></html>"
    )
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": html})
    signal = keywords.evaluate(fetch_results)
    assert signal.fired is False


def test_keywords_skips_allowlisted_domain():
    html = "<html><body><p>Weekly online lottery results published here.</p></body></html>"
    fetch_results = make_fetch_map("statelotteries.nic.in", {"desktop": html})
    signal = keywords.evaluate(fetch_results)
    assert signal.fired is False


def test_keywords_does_not_fire_on_gambling_substring_inside_unrelated_word():
    """Regression: iitgoa.ac.in scored "suspicious" because "satta" is a substring of a
    researcher's surname, Naphan Benchasattabuse, in a faculty publication list."""
    html = (
        "<html><body><p>Compromise and challenges of distillation, Joshua Carlo A. Casapao, "
        "Ananda G. Maity, Naphan Benchasattabuse, Michal Hajdusek | IEEE Network, 2026</p>"
        "</body></html>"
    )
    fetch_results = make_fetch_map("iitgoa.ac.in", {"desktop": html})
    signal = keywords.evaluate(fetch_results)
    assert signal.fired is False


# S3 outbound --------------------------------------------------------------


def test_outbound_fires_when_external_link_diverges():
    base = "<html><body><p>Home page</p></body></html>"
    spam = '<html><body><p>Home page</p><a href="http://sattaplay247.xyz/join">Join</a></body></html>'
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": base, "mobile_serp": spam})
    signal = outbound.evaluate(fetch_results)
    assert signal.fired is True


def test_outbound_does_not_fire_when_links_match_across_profiles():
    html = '<html><body><a href="https://www.aicte-india.org/">AICTE</a></body></html>'
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": html})
    signal = outbound.evaluate(fetch_results)
    assert signal.fired is False


def test_outbound_does_not_fire_on_own_site_link_missing_www():
    """Regression: a link to the bare apex from a www seed domain is the site's own link."""
    html = '<html><body><a href="https://iiits.ac.in/about">About</a></body></html>'
    fetch_results = make_fetch_map("www.iiits.ac.in", {"desktop": html})
    signal = outbound.evaluate(fetch_results)
    assert signal.fired is False


# S4 title -------------------------------------------------------------


def test_title_fires_when_titles_diverge():
    spam = "<html><head><title>Satta King Result Today</title></head><body>x</body></html>"
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": CLEAN_HTML, "mobile_serp": spam})
    signal = title.evaluate(fetch_results)
    assert signal.fired is True


def test_title_does_not_fire_when_titles_match():
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": CLEAN_HTML})
    signal = title.evaluate(fetch_results)
    assert signal.fired is False


# S5 hidden --------------------------------------------------------------


def test_hidden_fires_on_offscreen_keyword_text():
    html = (
        '<html><body><p>Welcome</p>'
        '<div style="position:absolute;left:-9999px">satta matka teen patti online rummy</div>'
        "</body></html>"
    )
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": html})
    signal = hidden.evaluate(fetch_results)
    assert signal.fired is True


def test_hidden_does_not_fire_on_visible_clean_text():
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": CLEAN_HTML})
    signal = hidden.evaluate(fetch_results)
    assert signal.fired is False


def test_hidden_does_not_fire_on_hidden_text_without_keywords():
    html = '<html><body><div style="display:none">just a hidden coupon code</div></body></html>'
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": html})
    signal = hidden.evaluate(fetch_results)
    assert signal.fired is False


# S6 similarity --------------------------------------------------------


def test_similarity_fires_when_googlebot_text_is_very_different():
    desktop_html = "<html><body>" + " ".join(f"word{i}" for i in range(60)) + "</body></html>"
    googlebot_html = "<html><body>" + " ".join(f"spam{i}" for i in range(60)) + "</body></html>"
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": desktop_html, "googlebot": googlebot_html})
    signal = similarity.evaluate(fetch_results)
    assert signal.fired is True


def test_similarity_does_not_fire_when_googlebot_text_matches_desktop():
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": CLEAN_HTML})
    signal = similarity.evaluate(fetch_results)
    assert signal.fired is False


# S7 injected_script -----------------------------------------------------


def test_injected_script_fires_on_untrusted_host():
    html = '<html><head><script src="http://trackpixel247.ru/track.js"></script></head><body>x</body></html>'
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": html})
    signal = injected_script.evaluate(fetch_results)
    assert signal.fired is True


def test_injected_script_does_not_fire_on_allowlisted_cdn():
    html = '<html><head><script src="https://cdnjs.cloudflare.com/jquery.min.js"></script></head><body>x</body></html>'
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": html})
    signal = injected_script.evaluate(fetch_results)
    assert signal.fired is False


def test_injected_script_does_not_fire_on_own_domain_script():
    html = '<html><head><script src="https://gpranipur.ac.in/assets/app.js"></script></head><body>x</body></html>'
    fetch_results = make_fetch_map("gpranipur.ac.in", {"desktop": html})
    signal = injected_script.evaluate(fetch_results)
    assert signal.fired is False
