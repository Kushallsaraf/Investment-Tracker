"""Ticker headlines from free RSS feeds (Yahoo Finance and Nasdaq)."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ElementTree
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol
from urllib.parse import quote

import httpx

SUMMARY_LIMIT = 280
FEEDS: tuple[tuple[str, str], ...] = (
    ("Yahoo Finance", "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"),
    ("Nasdaq", "https://www.nasdaq.com/feed/rssoutbound?symbol={symbol}"),
)
_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_STYLE = re.compile(r"@media|\{[^}]*\}")


class NewsProvider(Protocol):
    def headlines(self, symbol: str) -> dict[str, Any]: ...


def _clean(text: str | None) -> str:
    plain = _TAGS.sub(" ", html.unescape(text or ""))
    return _SPACE.sub(" ", plain).strip()


def _summary(text: str | None) -> str | None:
    """A short plain-text summary, or None when the feed sent page markup instead of prose."""
    if text and _STYLE.search(text):
        return None
    cleaned = _clean(text)
    if not cleaned:
        return None
    return cleaned if len(cleaned) <= SUMMARY_LIMIT else f"{cleaned[: SUMMARY_LIMIT - 1].rstrip()}…"


def _published(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat(timespec="seconds")


def parse_feed(xml_text: str, publisher: str) -> list[dict[str, Any]]:
    """Items from an RSS 2.0 document. Malformed items are skipped rather than guessed at."""
    root = ElementTree.fromstring(xml_text)
    items: list[dict[str, Any]] = []
    for item in root.iter("item"):
        title = _clean(item.findtext("title"))
        url = (item.findtext("link") or "").strip()
        published = _published(item.findtext("pubDate"))
        if not title or not url.startswith("https://") or published is None:
            continue
        creator = item.findtext("{http://purl.org/dc/elements/1.1/}creator")
        items.append(
            {
                "title": title,
                "summary": _summary(item.findtext("description")),
                "url": url,
                "published_at": published,
                "publisher": _clean(creator) or publisher,
                "feed": publisher,
            }
        )
    return items


def dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The same story often appears in both feeds; keep the earliest copy of each title."""
    seen: dict[str, dict[str, Any]] = {}
    for item in sorted(items, key=lambda row: row["published_at"]):
        key = re.sub(r"[^a-z0-9]", "", item["title"].lower())
        seen.setdefault(key, item)
    return sorted(seen.values(), key=lambda row: row["published_at"], reverse=True)


class RssNewsProvider:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(
            timeout=12,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Investment Tracker; local research dashboard)"},
        )

    def headlines(self, symbol: str) -> dict[str, Any]:
        """Headlines from every feed that answered, plus the reason any feed failed."""
        provider_symbol = quote(symbol.replace(".", "-"), safe="-")
        items: list[dict[str, Any]] = []
        failures: dict[str, str] = {}
        for publisher, template in FEEDS:
            try:
                response = self.client.get(template.format(symbol=provider_symbol))
                response.raise_for_status()
                items.extend(parse_feed(response.text, publisher))
            except (httpx.HTTPError, ElementTree.ParseError) as exc:
                failures[publisher] = f"{type(exc).__name__}"
        if failures and len(failures) == len(FEEDS):
            raise ConnectionError("No news feed could be reached: " + ", ".join(failures))
        return {
            "items": dedupe(items),
            "failures": failures,
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
