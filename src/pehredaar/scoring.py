"""Turns a list of Signal results into a 0 to 100 score and a Band, using the thresholds and the
minimum fired signal count from config.py. Enforces the hard rule that a compromised verdict needs
at least two independent signals.
"""

from pehredaar.config import settings
from pehredaar.models import Band, Signal


def score_signals(signals: list[Signal]) -> float:
    """Weighted sum of fired signals, normalised to 0 to 100 against the sum of every weight."""
    total_weight = sum(signal.weight for signal in signals)
    if total_weight <= 0:
        return 0.0
    fired_weight = sum(signal.weight for signal in signals if signal.fired)
    return round(100 * fired_weight / total_weight, 2)


def band_for_score(score: float) -> Band:
    """Map a 0 to 100 score onto a band using the thresholds in config.py, ignoring the hard rule."""
    if score >= settings.compromised_threshold:
        return Band.COMPROMISED
    if score >= settings.likely_compromised_threshold:
        return Band.LIKELY_COMPROMISED
    if score >= settings.suspicious_threshold:
        return Band.SUSPICIOUS
    return Band.CLEAN


def decide(signals: list[Signal]) -> tuple[float, Band]:
    """Score a list of signals and decide the band, enforcing the two signal hard rule."""
    score = score_signals(signals)
    band = band_for_score(score)
    fired_count = sum(1 for signal in signals if signal.fired)
    if band == Band.COMPROMISED and fired_count < settings.min_signals_for_compromised:
        band = Band.LIKELY_COMPROMISED
    return score, band
