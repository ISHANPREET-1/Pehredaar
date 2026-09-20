"""Builds seeds/domains.csv with columns domain,sector,state,institution_name.

Sources, all cited in README.md, fetched live and never invented:

- Wikipedia "Indian Institutes of Technology" and "National Institutes of
  Technology" (both list tables carry a Website column directly, so no
  second fetch is needed per row).
- Wikipedia "List of central universities in India", "Indian Institutes of
  Information Technology" and "All India Institutes of Medical Sciences"
  (Name and State/UT only; each institution's own Wikipedia article is
  fetched for its infobox Website).
- Wikipedia "States and union territories of India" (the canonical list of
  state and union territory names; each one's own Wikipedia article is
  fetched for its infobox Website, which is the state government portal).

For every candidate: the domain is normalised and validated with the same
normalize_domain used everywhere else in this project, so anything outside
config.py's allowed suffixes is dropped, not massaged into passing. The
domain is then resolved over DNS; anything that does not resolve today is
dropped and counted, the way tiet.ac.in turned out not to resolve during
Phase 2's live scans. Sector is derived from the surviving suffix itself:
.gov.in and .nic.in are gov, .ac.in, .edu.in and .res.in are edu.

If a source page fails to fetch, this script says so and moves on. It does
not fabricate rows for a source it could not reach.

Run as: python -m scripts.build_seed_list, or python scripts/build_seed_list.py
"""

import csv
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pehredaar.fetcher import DNSResolutionError, resolve_host  # noqa: E402
from pehredaar.models import normalize_domain  # noqa: E402

_OUTPUT_PATH = Path(__file__).resolve().parents[1] / "seeds" / "domains.csv"
_WIKIPEDIA_API = "https://en.wikipedia.org/wiki/{title}"
_USER_AGENT = "PehredaarSeedListBuilder/0.1 (hackathon project; contact: ishansahib102004@gmail.com)"
_REQUEST_DELAY_SECONDS = 0.3
_FOOTNOTE_RE = re.compile(r"\[[^\]]*\]")

_GOV_SUFFIXES = (".gov.in", ".nic.in")
_EDU_SUFFIXES = (".ac.in", ".edu.in", ".res.in")


@dataclass
class Candidate:
    institution_name: str
    state: str
    website: str | None
    detail_page_title: str | None = None


def _clean_text(text: str) -> str:
    return _FOOTNOTE_RE.sub("", text).strip()


def _fetch_page(client: httpx.Client, title: str) -> BeautifulSoup | None:
    url = _WIKIPEDIA_API.format(title=title)
    try:
        response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"source unreachable, skipping: {url} ({exc})", file=sys.stderr)
        return None
    time.sleep(_REQUEST_DELAY_SECONDS)
    return BeautifulSoup(response.text, "html.parser")


def _table_grid(table: BeautifulSoup) -> tuple[list[dict[int, "BeautifulSoup"]], list[bool]]:
    """Render every row of a table into a col -> cell dict, honouring rowspan and colspan the way
    a browser would, header rows included. Also reports which original rows were all <th>."""
    trs = table.find_all("tr")
    pending: dict[int, list] = {}  # col -> [remaining_rowspan, cell]
    grid_rows: list[dict[int, "BeautifulSoup"]] = []
    all_th_flags: list[bool] = []
    for tr in trs:
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        all_th_flags.append(all(cell.name == "th" for cell in cells))
        row: dict[int, "BeautifulSoup"] = {}
        col = 0
        cell_iter = iter(cells)
        current = next(cell_iter, None)
        while current is not None or any(pending_col >= col for pending_col in pending):
            carry = pending.get(col)
            if carry and carry[0] > 0:
                row[col] = carry[1]
                carry[0] -= 1
                if carry[0] == 0:
                    del pending[col]
                col += 1
                continue
            if current is None:
                col += 1
                continue
            colspan = int(current.get("colspan", 1) or 1)
            rowspan = int(current.get("rowspan", 1) or 1)
            for offset in range(colspan):
                row[col + offset] = current
                if rowspan > 1:
                    pending[col + offset] = [rowspan - 1, current]
            col += colspan
            current = next(cell_iter, None)
        grid_rows.append(row)
    return grid_rows, all_th_flags


def _wikitable_rows(soup: BeautifulSoup, table_index: int) -> list[dict[str, "BeautifulSoup"]]:
    """Parse one wikitable into a list of {header_name: cell} dicts, matched by header text.

    Renders the whole table, header rows included, through the same rowspan/colspan aware grid so
    a two row grouped header (like NIRF Rank splitting into Engineering and Overall) resolves to
    the right leaf columns, and a data row that shares a rowspanned State cell with the row above
    it still gets that state.
    """
    tables = soup.find_all("table", class_="wikitable")
    if table_index >= len(tables):
        return []
    grid_rows, all_th_flags = _table_grid(tables[table_index])
    if not grid_rows:
        return []

    header_row_count = 0
    for is_header in all_th_flags:
        if not is_header:
            break
        header_row_count += 1
    header_row_count = max(header_row_count, 1)

    header_grid_row = grid_rows[header_row_count - 1]
    num_cols = max(header_grid_row.keys(), default=-1) + 1
    header_texts = [header_grid_row[c].get_text(strip=True) if c in header_grid_row else "" for c in range(num_cols)]

    parsed = []
    for row in grid_rows[header_row_count:]:
        parsed.append({header_texts[c]: cell for c, cell in row.items() if c < num_cols and header_texts[c]})
    return parsed


def _infobox_website(soup: BeautifulSoup) -> str | None:
    infobox = soup.find("table", class_="infobox")
    if not infobox:
        return None
    for row in infobox.find_all("tr"):
        header = row.find("th")
        if not header or "website" not in header.get_text(strip=True).lower():
            continue
        link = row.find("a", href=True)
        if link:
            return link["href"]
    return None


def _wiki_title_from_href(href: str) -> str | None:
    """Extract the article title from a Wikipedia link, whether it is root relative or absolute."""
    marker = "/wiki/"
    index = href.find(marker)
    if index == -1:
        return None
    title = href[index + len(marker) :]
    if ":" in title:  # Special:, Category:, File: and similar are not articles
        return None
    return title


def _collect_from_table_with_website(
    client: httpx.Client,
    page_title: str,
    table_index: int,
    name_header: str,
    state_header: str,
    source_label: str,
) -> list[Candidate]:
    """For a list table that already has a Website column, read name, state and website straight
    out of the same row. No second fetch needed."""
    soup = _fetch_page(client, page_title)
    if soup is None:
        return []
    candidates = []
    for row in _wikitable_rows(soup, table_index=table_index):
        name_cell, state_cell, website_cell = row.get(name_header), row.get(state_header), row.get("Website")
        if name_cell is None or state_cell is None or website_cell is None:
            continue
        link = website_cell.find("a", href=True)
        website = link["href"] if link else _clean_text(website_cell.get_text())
        candidates.append(
            Candidate(
                institution_name=_clean_text(name_cell.get_text()),
                state=_clean_text(state_cell.get_text()),
                website=website,
            )
        )
    print(f"{source_label}: {len(candidates)} rows with a website")
    return candidates


def collect_iits(client: httpx.Client) -> list[Candidate]:
    return _collect_from_table_with_website(
        client,
        page_title="Indian_Institutes_of_Technology",
        table_index=0,
        name_header="Name",
        state_header="State/UT",
        source_label="Indian Institutes of Technology",
    )


def collect_nits(client: httpx.Client) -> list[Candidate]:
    return _collect_from_table_with_website(
        client,
        page_title="National_Institutes_of_Technology",
        table_index=1,
        name_header="Name",
        state_header="State/UT",
        source_label="National Institutes of Technology",
    )


def _collect_via_detail_pages(
    client: httpx.Client,
    page_title: str,
    table_index: int,
    name_header: str,
    state_header: str,
    source_label: str,
) -> list[Candidate]:
    """For a list table with Name and State but no Website, resolve each row's own Wikipedia
    article and read its infobox Website field, one extra polite fetch per row."""
    soup = _fetch_page(client, page_title)
    if soup is None:
        return []
    candidates = []
    for row in _wikitable_rows(soup, table_index=table_index):
        name_cell, state_cell = row.get(name_header), row.get(state_header)
        if name_cell is None or state_cell is None:
            continue
        link = name_cell.find("a", href=True)
        title = _wiki_title_from_href(link["href"]) if link else None
        candidates.append(
            Candidate(
                institution_name=_clean_text(name_cell.get_text()),
                state=_clean_text(state_cell.get_text()),
                website=None,
                detail_page_title=title,
            )
        )
    resolved = 0
    for candidate in candidates:
        if not candidate.detail_page_title:
            continue
        detail_soup = _fetch_page(client, candidate.detail_page_title)
        if detail_soup is None:
            continue
        candidate.website = _infobox_website(detail_soup)
        if candidate.website:
            resolved += 1
    print(f"{source_label}: {len(candidates)} rows, {resolved} had an infobox website")
    return candidates


def collect_central_universities(client: httpx.Client) -> list[Candidate]:
    return _collect_via_detail_pages(
        client,
        page_title="List_of_central_universities_in_India",
        table_index=1,
        name_header="University",
        state_header="State",
        source_label="Central universities",
    )


def collect_iiits(client: httpx.Client) -> list[Candidate]:
    return _collect_via_detail_pages(
        client,
        page_title="Indian_Institutes_of_Information_Technology",
        table_index=0,
        name_header="Name",
        state_header="State/UT",
        source_label="Indian Institutes of Information Technology",
    )


def collect_aiims(client: httpx.Client) -> list[Candidate]:
    return _collect_via_detail_pages(
        client,
        page_title="All_India_Institutes_of_Medical_Sciences",
        table_index=0,
        name_header="Name",
        state_header="State/UT",
        source_label="All India Institutes of Medical Sciences",
    )


def collect_state_portals(client: httpx.Client) -> list[Candidate]:
    """Each state and union territory's own Wikipedia infobox Website is its official portal."""
    soup = _fetch_page(client, "States_and_union_territories_of_India")
    if soup is None:
        return []
    candidates = []
    seen_states: set[str] = set()
    for table_index in (0, 1):
        for row in _wikitable_rows(soup, table_index=table_index):
            state_cell = row.get("State") or row.get("State[53]")
            if state_cell is None:
                continue
            link = state_cell.find("a", href=True)
            title = _wiki_title_from_href(link["href"]) if link else None
            name = _clean_text(state_cell.get_text())
            if not title or name in seen_states:
                continue
            seen_states.add(name)
            candidates.append(
                Candidate(institution_name=f"Government of {name}", state=name, website=None, detail_page_title=title)
            )
    resolved = 0
    for candidate in candidates:
        detail_soup = _fetch_page(client, candidate.detail_page_title)
        if detail_soup is None:
            continue
        candidate.website = _infobox_website(detail_soup)
        if candidate.website:
            resolved += 1
    print(f"State and union territory portals: {len(candidates)} rows, {resolved} had an infobox website")
    return candidates


def _sector_for_domain(domain: str) -> str | None:
    if domain.endswith(_GOV_SUFFIXES):
        return "gov"
    if domain.endswith(_EDU_SUFFIXES):
        return "edu"
    return None


def build_rows(candidates: list[Candidate]) -> tuple[list[dict[str, str]], dict[str, int]]:
    stats = {"candidates": len(candidates), "no_website": 0, "invalid_domain": 0, "dns_failed": 0, "duplicate": 0, "kept": 0}
    seen_domains: set[str] = set()
    rows = []
    for candidate in candidates:
        if not candidate.website:
            stats["no_website"] += 1
            continue
        try:
            domain = normalize_domain(candidate.website)
        except ValueError:
            stats["invalid_domain"] += 1
            continue
        if domain in seen_domains:
            stats["duplicate"] += 1
            continue
        try:
            resolve_host(domain)
        except DNSResolutionError:
            stats["dns_failed"] += 1
            print(f"does not resolve, dropping: {domain} ({candidate.institution_name})", file=sys.stderr)
            continue
        sector = _sector_for_domain(domain)
        if sector is None:
            stats["invalid_domain"] += 1
            continue
        seen_domains.add(domain)
        rows.append(
            {
                "domain": domain,
                "sector": sector,
                "state": candidate.state,
                "institution_name": candidate.institution_name,
            }
        )
        stats["kept"] += 1
    return rows, stats


def main() -> int:
    with httpx.Client(timeout=15.0, headers={"User-Agent": _USER_AGENT}, follow_redirects=True) as client:
        candidates: list[Candidate] = []
        candidates += collect_iits(client)
        candidates += collect_nits(client)
        candidates += collect_central_universities(client)
        candidates += collect_state_portals(client)
        candidates += collect_iiits(client)
        candidates += collect_aiims(client)

    rows, stats = build_rows(candidates)
    rows.sort(key=lambda r: (r["sector"], r["state"], r["domain"]))

    with _OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["domain", "sector", "state", "institution_name"])
        writer.writeheader()
        writer.writerows(rows)

    print()
    print(f"candidates collected: {stats['candidates']}")
    print(f"  dropped, no website found: {stats['no_website']}")
    print(f"  dropped, outside allowed suffixes or unparseable: {stats['invalid_domain']}")
    print(f"  dropped, did not resolve over DNS: {stats['dns_failed']}")
    print(f"  dropped, duplicate domain: {stats['duplicate']}")
    print(f"written to {_OUTPUT_PATH}: {stats['kept']} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
