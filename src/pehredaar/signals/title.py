"""S4. Fires when the title or meta description differs materially between profiles."""

from bs4 import BeautifulSoup

from pehredaar.models import FetchResult, Signal

NAME = "S4_title_divergence"
WEIGHT = 0.75


def _title_and_description(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True).lower() if soup.title else ""
    meta = soup.find("meta", attrs={"name": "description"})
    description = meta.get("content", "").strip().lower() if meta else ""
    return title, description


def evaluate(fetch_results: dict[str, FetchResult]) -> Signal:
    by_profile: dict[str, dict[str, str]] = {}
    for profile_key, result in fetch_results.items():
        if result.error is not None or result.html is None:
            continue
        title, description = _title_and_description(result.html)
        by_profile[profile_key] = {"title": title, "description": description}

    titles = {v["title"] for v in by_profile.values()}
    descriptions = {v["description"] for v in by_profile.values()}
    fired = len(titles) > 1 or len(descriptions) > 1
    return Signal(name=NAME, fired=fired, weight=WEIGHT, evidence={"title_and_description_by_profile": by_profile})
