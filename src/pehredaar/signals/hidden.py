"""S5. Fires on keyword bearing text hidden with display:none, visibility:hidden, font-size:0,
text-indent:-9999px, or positioning far off screen.
"""

import re

from bs4 import BeautifulSoup

from pehredaar.models import FetchResult, Signal
from pehredaar.signals import load_data_yaml

NAME = "S5_hidden_text"
WEIGHT = 2.5

_KEYWORDS_DATA = load_data_yaml("keywords.yaml")
_ALL_KEYWORDS = [k.lower() for k in _KEYWORDS_DATA.get("gambling", []) + _KEYWORDS_DATA.get("pharma", [])]

_HIDDEN_STYLE_RE = re.compile(
    r"display\s*:\s*none"
    r"|visibility\s*:\s*hidden"
    r"|font-size\s*:\s*0(?:px)?\b"
    r"|text-indent\s*:\s*-\d{3,}px",
    re.IGNORECASE,
)
_OFFSCREEN_POSITION_RE = re.compile(
    r"position\s*:\s*(?:absolute|fixed).{0,80}?(?:left|top)\s*:\s*-\d{3,}px",
    re.IGNORECASE | re.DOTALL,
)


def _is_hidden(style: str) -> bool:
    return bool(_HIDDEN_STYLE_RE.search(style) or _OFFSCREEN_POSITION_RE.search(style))


def evaluate(fetch_results: dict[str, FetchResult]) -> Signal:
    hits_by_profile: dict[str, list[dict]] = {}
    for profile_key, result in fetch_results.items():
        if result.error is not None or result.html is None:
            continue
        soup = BeautifulSoup(result.html, "html.parser")
        hits = []
        for element in soup.find_all(style=True):
            if not _is_hidden(element.get("style", "")):
                continue
            text = element.get_text(separator=" ", strip=True).lower()
            matched = [keyword for keyword in _ALL_KEYWORDS if keyword in text]
            if matched:
                hits.append({"tag": element.name, "keywords": matched})
        if hits:
            hits_by_profile[profile_key] = hits

    fired = len(hits_by_profile) > 0
    return Signal(name=NAME, fired=fired, weight=WEIGHT, evidence={"hits_by_profile": hits_by_profile})
