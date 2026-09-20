"""Registry of signal modules and small helpers shared between them. Each module's evaluate()
returns a Signal without deciding a verdict; detector.py collects every module's output and hands
the list to scoring.py.
"""

import re
from pathlib import Path

import yaml

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_data_yaml(filename: str) -> dict:
    """Load one file from src/pehredaar/data/ as a plain dict."""
    with (_DATA_DIR / filename).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def defang_host(host: str) -> str:
    """Bracket the dots in a host so it is never a clickable attacker link, per CLAUDE.md section 2."""
    return host.replace(".", "[.]") if host else host


def defang_url(url: str) -> str:
    """Defang a full URL: hxxp scheme, bracketed dots. Never render an attacker URL as a link."""
    defanged = re.sub(r"^http", "hxxp", url, count=1)
    return defanged.replace(".", "[.]")


def strip_www(host: str) -> str:
    """Drop a leading www. label, so www.iiits.ac.in and iiits.ac.in compare as the same host."""
    return host[len("www.") :] if host.startswith("www.") else host


def is_same_site(domain: str, host: str) -> bool:
    """True if host is domain itself, a subdomain of it, or the same site modulo a leading www on
    either side (www.iiits.ac.in and iiits.ac.in are the same site; sattaplay247.xyz is not).
    """
    base_domain = strip_www(domain)
    base_host = strip_www(host)
    return base_host == base_domain or base_host.endswith("." + base_domain)


# Imported after the helpers above, since every signal module imports one or
# more of them back from this same package.
from pehredaar.signals import hidden, injected_script, keywords, outbound, redirect, similarity, title  # noqa: E402

ALL_SIGNALS = (
    redirect.evaluate,
    keywords.evaluate,
    outbound.evaluate,
    title.evaluate,
    hidden.evaluate,
    similarity.evaluate,
    injected_script.evaluate,
)
