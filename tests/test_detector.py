"""End to end tests for pehredaar.detector against the seven required fixture scenarios. The three
false positive fixtures, police_advisory, state_lottery and dynamic_noise, are the real acceptance
test: they must stay clean or a guard is broken, not the fixture.
"""

from pehredaar.cli import load_fixture
from pehredaar.detector import run_detector
from pehredaar.models import Band


def _run(fixture_name: str):
    domain, fetch_results = load_fixture(fixture_name)
    return run_detector(domain, fetch_results)


def test_clean_college_is_clean():
    result = _run("clean_college")
    assert result.band == Band.CLEAN
    assert result.injection_class is None


def test_police_advisory_stays_clean():
    result = _run("police_advisory")
    assert result.band == Band.CLEAN, result.model_dump(mode="json")


def test_state_lottery_stays_clean():
    result = _run("state_lottery")
    assert result.band == Band.CLEAN, result.model_dump(mode="json")


def test_dynamic_noise_stays_clean():
    result = _run("dynamic_noise")
    assert result.band == Band.CLEAN, result.model_dump(mode="json")


def test_cloaked_gambling_is_detected_as_class_a():
    result = _run("cloaked_gambling")
    assert result.band != Band.CLEAN
    assert result.injection_class == "A"


def test_cloaked_googlebot_is_detected_as_class_a():
    result = _run("cloaked_googlebot")
    assert result.band != Band.CLEAN
    assert result.injection_class == "A"


def test_doorway_persistent_is_detected_as_class_b():
    result = _run("doorway_persistent")
    assert result.band != Band.CLEAN
    assert result.injection_class == "B"
