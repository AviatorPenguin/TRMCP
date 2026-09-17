"""Fetches and caches the raw TrainerRoad calendar (.ics) feed."""

from __future__ import annotations

import time

import httpx
import icalendar

USER_AGENT = "trmcp/0.1 (+https://github.com; TrainerRoad calendar reader for Claude)"


class CalendarFetchError(RuntimeError):
    """Raised when the calendar feed can't be fetched or isn't valid iCalendar data."""


class CalendarFeed:
    """Fetches a TrainerRoad calendar-export URL and caches the parsed result briefly.

    TrainerRoad's calendar export is meant for calendar apps that poll infrequently,
    so we cache the parsed calendar in memory for `cache_ttl_seconds` to avoid hammering
    the feed on every tool call.
    """

    def __init__(self, url: str, cache_ttl_seconds: int = 300, timeout_seconds: float = 15.0):
        self._url = url
        self._cache_ttl_seconds = cache_ttl_seconds
        self._timeout_seconds = timeout_seconds
        self._cached_calendar: icalendar.Calendar | None = None
        self._cached_at: float = 0.0

    def get(self, *, force_refresh: bool = False) -> icalendar.Calendar:
        now = time.monotonic()
        is_stale = (now - self._cached_at) >= self._cache_ttl_seconds
        if self._cached_calendar is None or force_refresh or is_stale:
            self._cached_calendar = self._fetch()
            self._cached_at = now
        return self._cached_calendar

    def _fetch(self) -> icalendar.Calendar:
        try:
            response = httpx.get(
                self._url,
                headers={"User-Agent": USER_AGENT, "Accept": "text/calendar, */*"},
                timeout=self._timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise CalendarFetchError(
                f"TrainerRoad calendar feed returned HTTP {exc.response.status_code}. "
                "Double-check TRAINERROAD_CALENDAR_URL is still valid at "
                "https://www.trainerroad.com/profile/calendar-sync."
            ) from exc
        except httpx.HTTPError as exc:
            raise CalendarFetchError(f"Could not reach the TrainerRoad calendar feed: {exc}") from exc

        try:
            return icalendar.Calendar.from_ical(response.content)
        except ValueError as exc:
            raise CalendarFetchError(
                "TrainerRoad calendar feed did not return valid iCalendar data. "
                "The subscription URL may have been revoked or regenerated."
            ) from exc
