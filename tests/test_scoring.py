"""Tests for pehredaar.scoring: the weighted sum, every band boundary, and the hard rule that a
compromised verdict needs at least two independent signals firing.
"""

import pytest

from pehredaar.config import settings
from pehredaar.models import Band, Signal
from pehredaar.scoring import band_for_score, decide, score_signals


def _signal(name: str, fired: bool, weight: float) -> Signal:
    return Signal(name=name, fired=fired, weight=weight)


def test_score_signals_is_the_weighted_share_of_fired_signals():
    signals = [_signal("a", True, 1.0), _signal("b", False, 1.0), _signal("c", True, 2.0)]
    assert score_signals(signals) == pytest.approx(75.0)


def test_score_signals_is_zero_with_no_signals():
    assert score_signals([]) == 0.0


@pytest.mark.parametrize(
    "score,expected_band",
    [
        (0, Band.CLEAN),
        (settings.suspicious_threshold - 1, Band.CLEAN),
        (settings.suspicious_threshold, Band.SUSPICIOUS),
        (settings.likely_compromised_threshold - 1, Band.SUSPICIOUS),
        (settings.likely_compromised_threshold, Band.LIKELY_COMPROMISED),
        (settings.compromised_threshold - 1, Band.LIKELY_COMPROMISED),
        (settings.compromised_threshold, Band.COMPROMISED),
        (100, Band.COMPROMISED),
    ],
)
def test_band_for_score_boundaries(score, expected_band):
    assert band_for_score(score) == expected_band


def test_decide_enforces_hard_rule_downgrading_single_signal_compromise():
    signals = [_signal("S2_keywords", True, 100.0)]
    score, band = decide(signals)
    assert score == 100.0
    assert band == Band.LIKELY_COMPROMISED


def test_decide_allows_compromised_with_two_independent_signals():
    signals = [_signal("S2_keywords", True, 50.0), _signal("S5_hidden_text", True, 50.0)]
    score, band = decide(signals)
    assert score == 100.0
    assert band == Band.COMPROMISED
