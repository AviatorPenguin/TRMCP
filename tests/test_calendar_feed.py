from pathlib import Path

import httpx
import pytest

from trmcp.calendar_feed import CalendarFeed, CalendarFetchError

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_calendar.ics"
FIXTURE_BYTES = FIXTURE_PATH.read_bytes()


class _CountingTransport(httpx.BaseTransport):
    def __init__(self, response_factory):
        self.calls = 0
        self._response_factory = response_factory

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return self._response_factory()


def _patch_get(monkeypatch, transport: _CountingTransport):
    def fake_get(url, **kwargs):
        with httpx.Client(transport=transport) as client:
            return client.get(url)

    monkeypatch.setattr("trmcp.calendar_feed.httpx.get", fake_get)


def test_get_fetches_and_parses(monkeypatch):
    transport = _CountingTransport(lambda: httpx.Response(200, content=FIXTURE_BYTES))
    _patch_get(monkeypatch, transport)

    feed = CalendarFeed("https://example.com/cal.ics", cache_ttl_seconds=300)
    calendar = feed.get()
    event_count = sum(1 for c in calendar.walk() if c.name == "VEVENT")
    assert event_count == 5
    assert transport.calls == 1


def test_get_uses_cache_within_ttl(monkeypatch):
    transport = _CountingTransport(lambda: httpx.Response(200, content=FIXTURE_BYTES))
    _patch_get(monkeypatch, transport)

    feed = CalendarFeed("https://example.com/cal.ics", cache_ttl_seconds=300)
    feed.get()
    feed.get()
    feed.get()
    assert transport.calls == 1


def test_force_refresh_bypasses_cache(monkeypatch):
    transport = _CountingTransport(lambda: httpx.Response(200, content=FIXTURE_BYTES))
    _patch_get(monkeypatch, transport)

    feed = CalendarFeed("https://example.com/cal.ics", cache_ttl_seconds=300)
    feed.get()
    feed.get(force_refresh=True)
    assert transport.calls == 2


def test_http_error_raises_calendar_fetch_error(monkeypatch):
    transport = _CountingTransport(lambda: httpx.Response(404, content=b"not found"))
    _patch_get(monkeypatch, transport)

    feed = CalendarFeed("https://example.com/cal.ics", cache_ttl_seconds=300)
    with pytest.raises(CalendarFetchError):
        feed.get()


def test_invalid_ics_raises_calendar_fetch_error(monkeypatch):
    transport = _CountingTransport(lambda: httpx.Response(200, content=b"not an ics file"))
    _patch_get(monkeypatch, transport)

    feed = CalendarFeed("https://example.com/cal.ics", cache_ttl_seconds=300)
    with pytest.raises(CalendarFetchError):
        feed.get()
