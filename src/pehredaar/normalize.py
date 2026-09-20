"""Strips what legitimately differs between two fetches of the same page, so an honest site does
not look cloaked: timestamps and "last updated" strings, tokens and nonces, hit counters, HTML
comments, and whitespace differences. Extracts visible text so a mobile and a desktop layout of
the same page compare fairly.
"""

import re

from bs4 import BeautifulSoup
from bs4.element import Comment

_DATE_RE = re.compile(
    r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm|ist)?\b", re.IGNORECASE)
_TOKEN_RE = re.compile(r"\b[a-f0-9]{16,}\b", re.IGNORECASE)
_COUNTER_RE = re.compile(r"\bvisitors?\s*:?\s*\d[\d,]*\b", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_html_to_text(html: str) -> str:
    """Turn raw HTML into lowercased, whitespace collapsed visible text with ephemeral noise removed."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda node: isinstance(node, Comment)):
        comment.extract()

    text = soup.get_text(separator=" ").lower()
    text = _DATE_RE.sub(" ", text)
    text = _TIME_RE.sub(" ", text)
    text = _TOKEN_RE.sub(" ", text)
    text = _COUNTER_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()
