"""Tests for pehredaar.normalize: proves the ephemeral noise a real fetch picks up (timestamps,
tokens, hit counters, comments, whitespace, attribute order) does not survive normalisation.
"""

from pathlib import Path

from pehredaar.normalize import normalize_html_to_text

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_dynamic_noise_fixtures_normalize_identically():
    fixture_dir = _FIXTURES_DIR / "dynamic_noise"
    normalized = {
        profile: normalize_html_to_text((fixture_dir / f"{profile}.html").read_text())
        for profile in ("desktop", "mobile", "mobile_serp", "googlebot")
    }
    distinct = set(normalized.values())
    assert len(distinct) == 1, normalized


def test_dynamic_noise_text_still_contains_real_content():
    fixture_dir = _FIXTURES_DIR / "dynamic_noise"
    text = normalize_html_to_text((fixture_dir / "desktop.html").read_text())
    assert "government polytechnic college" in text
    assert "48213" not in text
    assert "9f86d081884c7d659a2feaa0c55ad015" not in text
    assert "09:12" not in text


def test_whitespace_and_attribute_order_do_not_matter():
    first = "<html><body><p class=\"a\" id=\"b\">Hello   World</p></body></html>"
    second = "<html>\n<body>\n<p id=\"b\" class=\"a\">\n  Hello\nWorld\n</p>\n</body>\n</html>\n"
    assert normalize_html_to_text(first) == normalize_html_to_text(second)


def test_comments_and_script_and_style_are_stripped():
    html = """
    <html><body>
    <!-- build id abcdefabcdefabcdef -->
    <style>.x { color: red; }</style>
    <p>Real content</p>
    <script>var secret = "should not appear";</script>
    </body></html>
    """
    text = normalize_html_to_text(html)
    assert text == "real content"
