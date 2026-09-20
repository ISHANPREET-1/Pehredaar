"""S6. Fires when normalised text similarity between the googlebot and desktop profiles falls below
threshold, measured as Jaccard similarity over token 5 grams. Compares normalize.py's extracted
text, never raw HTML, so it must never fire on layout differences alone.
"""

from pehredaar.config import settings
from pehredaar.models import FetchResult, Signal
from pehredaar.normalize import normalize_html_to_text

NAME = "S6_googlebot_desktop_similarity"
WEIGHT = 1.75
_GRAM_SIZE = 5


def _five_grams(text: str) -> set[tuple[str, ...]]:
    tokens = text.split()
    if len(tokens) < _GRAM_SIZE:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i : i + _GRAM_SIZE]) for i in range(len(tokens) - _GRAM_SIZE + 1)}


def _jaccard(a: set, b: set) -> float:
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def evaluate(fetch_results: dict[str, FetchResult]) -> Signal:
    desktop = fetch_results.get("desktop")
    googlebot = fetch_results.get("googlebot")
    if not desktop or not googlebot or desktop.html is None or googlebot.html is None:
        return Signal(
            name=NAME,
            fired=False,
            weight=WEIGHT,
            evidence={"skipped": "missing desktop or googlebot fetch"},
        )

    desktop_grams = _five_grams(normalize_html_to_text(desktop.html))
    googlebot_grams = _five_grams(normalize_html_to_text(googlebot.html))
    similarity = _jaccard(desktop_grams, googlebot_grams)
    fired = similarity < settings.similarity_jaccard_threshold
    evidence = {"jaccard_similarity": round(similarity, 4), "threshold": settings.similarity_jaccard_threshold}
    return Signal(name=NAME, fired=fired, weight=WEIGHT, evidence=evidence)
