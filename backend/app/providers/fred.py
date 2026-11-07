"""Economic data and release dates from FRED, and FOMC meeting dates from the Federal Reserve."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Protocol

import httpx

FRED_BASE = "https://api.stlouisfed.org/fred"
FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
MONTHS = {
    name: index
    for index, name in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1
    )
}


class FredNotConfiguredError(RuntimeError):
    pass


class FredProtocol(Protocol):
    def observations(self, series_id: str, start: date) -> list[tuple[str, float]]: ...

    def release_dates(self, release_id: int, start: date) -> list[str]: ...


class FredClient:
    def __init__(self, api_key: str | None, client: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=20, headers={"User-Agent": "Investment Tracker (local)"})

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise FredNotConfiguredError("Add a free FRED API key to .env as FRED_API_KEY to load macro data")
        try:
            response = self.client.get(
                f"{FRED_BASE}/{path}", params={**params, "api_key": self.api_key, "file_type": "json"}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            # The request URL carries the API key, so it never goes into the message.
            raise RuntimeError(f"FRED returned HTTP {exc.response.status_code}") from None
        except httpx.HTTPError as exc:
            raise RuntimeError(f"FRED could not be reached ({type(exc).__name__})") from None

    def observations(self, series_id: str, start: date) -> list[tuple[str, float]]:
        """Dated values oldest first. FRED marks missing days with "."; those are dropped."""
        payload = self._get(
            "series/observations", {"series_id": series_id, "observation_start": start.isoformat()}
        )
        return [
            (row["date"], float(row["value"]))
            for row in payload.get("observations", [])
            if row.get("value") not in (None, "", ".")
        ]

    def release_dates(self, release_id: int, start: date) -> list[str]:
        """Scheduled dates for a release, including future ones that have no data yet."""
        payload = self._get(
            "release/dates",
            {
                "release_id": release_id,
                "realtime_start": start.isoformat(),
                "include_release_dates_with_no_data": "true",
                "sort_order": "asc",
                "limit": 20,
            },
        )
        return [row["date"] for row in payload.get("release_dates", []) if row["date"] >= start.isoformat()]


_YEAR_HEADING = re.compile(r"(\d{4}) FOMC Meetings")
_MEETING = re.compile(
    r'fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)<', re.DOTALL
)


def parse_fomc_calendar(page: str) -> list[dict[str, Any]]:
    """Scheduled FOMC meetings from the Fed's calendar page, as start/end dates.

    A trailing * marks meetings with a Summary of Economic Projections. Rows that aren't a plain
    day range (notation votes, unscheduled calls) are skipped.
    """
    headings = list(_YEAR_HEADING.finditer(page))
    meetings: list[dict[str, Any]] = []
    for index, heading in enumerate(headings):
        year = int(heading.group(1))
        stop = headings[index + 1].start() if index + 1 < len(headings) else len(page)
        section = page[heading.end() : stop]
        for month_text, day_text in _MEETING.findall(section):
            months = [MONTHS.get(part.strip()[:3].lower()) for part in month_text.split("/")]
            days = re.fullmatch(r"\s*(\d{1,2})(?:-(\d{1,2}))?(\*?)\s*", day_text)
            if None in months or not days:
                continue
            first_day = int(days.group(1))
            last_day = int(days.group(2) or first_day)
            start_month, end_month = months[0], months[-1]
            end_year = year + 1 if end_month < start_month else year
            try:
                start = date(year, start_month, first_day)
                end = date(end_year, end_month, last_day)
            except ValueError:
                continue
            meetings.append(
                {"start": start.isoformat(), "end": end.isoformat(), "projections": bool(days.group(3))}
            )
    return sorted(meetings, key=lambda row: row["start"])


class FedCalendarClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Investment Tracker; local)"},
        )

    def fomc_meetings(self) -> list[dict[str, Any]]:
        response = self.client.get(FOMC_CALENDAR_URL)
        response.raise_for_status()
        return parse_fomc_calendar(response.text)
