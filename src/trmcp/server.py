"""MCP server that exposes a TrainerRoad training plan (via calendar export) to Claude."""

from __future__ import annotations

import json
from datetime import date, datetime

from mcp.server.mcpserver import MCPServer

from trmcp.calendar_feed import CalendarFeed, CalendarFetchError
from trmcp.config import ConfigError, load_config
from trmcp.workouts import Workout, default_window, expand_events

mcp = MCPServer(
    "trainerroad",
    instructions=(
        "Provides read-only access to a TrainerRoad athlete's training plan, sourced from "
        "their private TrainerRoad calendar-export feed (get it at "
        "https://www.trainerroad.com/profile/calendar-sync). Dates are ISO 8601 (YYYY-MM-DD). "
        "Use list_workouts for a quick overview, get_workouts_in_range for a specific window, "
        "get_next_workout for 'what's today/next', and get_training_summary for aggregate load."
    ),
)

_feed: CalendarFeed | None = None


def _get_feed() -> CalendarFeed:
    global _feed
    if _feed is None:
        config = load_config()
        _feed = CalendarFeed(config.calendar_url, cache_ttl_seconds=config.cache_ttl_seconds)
    return _feed


def _parse_iso_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date (YYYY-MM-DD), got: {value!r}") from exc


def _fetch_workouts(start: date, end: date, *, force_refresh: bool = False) -> list[Workout]:
    try:
        calendar = _get_feed().get(force_refresh=force_refresh)
    except CalendarFetchError as exc:
        raise RuntimeError(str(exc)) from exc
    return expand_events(calendar, start, end)


@mcp.tool()
def list_workouts(days_back: int = 7, days_forward: int = 28) -> str:
    """List planned (and recently completed) TrainerRoad workouts around today.

    Args:
        days_back: How many days before today to include (default 7).
        days_forward: How many days after today to include (default 28).
    """
    today = date.today()
    start = today - _non_negative(days_back, "days_back")
    end = today + _non_negative(days_forward, "days_forward")
    workouts = _fetch_workouts(start, end)
    return _dump(
        {
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "count": len(workouts),
            "workouts": [w.to_dict() for w in workouts],
        }
    )


@mcp.tool()
def get_workouts_in_range(start_date: str, end_date: str) -> str:
    """Get TrainerRoad workouts scheduled within an explicit date range (inclusive).

    Args:
        start_date: Start of the range, ISO date (YYYY-MM-DD).
        end_date: End of the range, ISO date (YYYY-MM-DD), inclusive.
    """
    start = _parse_iso_date(start_date, "start_date")
    end = _parse_iso_date(end_date, "end_date")
    if end < start:
        raise ValueError("end_date must not be before start_date")
    workouts = _fetch_workouts(start, end + _one_day())
    return _dump(
        {
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "count": len(workouts),
            "workouts": [w.to_dict() for w in workouts],
        }
    )


@mcp.tool()
def get_next_workout() -> str:
    """Get the next upcoming TrainerRoad workout (today or later)."""
    today = date.today()
    start, end = default_window(days_back=0, days_forward=60)
    workouts = _fetch_workouts(start, end)
    upcoming = [w for w in workouts if _workout_date(w) >= today]
    if not upcoming:
        return _dump({"found": False, "message": "No upcoming workouts found in the next 60 days."})
    return _dump({"found": True, "workout": upcoming[0].to_dict()})


@mcp.tool()
def search_workouts(query: str, days_back: int = 30, days_forward: int = 90) -> str:
    """Search workouts by name/sport/notes substring within a date window.

    Args:
        query: Case-insensitive text to search for in the workout name, sport, or notes.
        days_back: How many days before today to include (default 30).
        days_forward: How many days after today to include (default 90).
    """
    if not query.strip():
        raise ValueError("query must not be empty")
    today = date.today()
    start = today - _non_negative(days_back, "days_back")
    end = today + _non_negative(days_forward, "days_forward")
    workouts = _fetch_workouts(start, end)
    needle = query.strip().lower()
    matches = [
        w
        for w in workouts
        if needle in w.name.lower()
        or needle in (w.sport or "").lower()
        or needle in w.notes.lower()
    ]
    return _dump(
        {
            "query": query,
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "count": len(matches),
            "workouts": [w.to_dict() for w in matches],
        }
    )


@mcp.tool()
def get_training_summary(days_back: int = 7, days_forward: int = 28) -> str:
    """Summarize planned training load (workout count, minutes, TSS) by sport, around today.

    Args:
        days_back: How many days before today to include (default 7).
        days_forward: How many days after today to include (default 28).
    """
    today = date.today()
    start = today - _non_negative(days_back, "days_back")
    end = today + _non_negative(days_forward, "days_forward")
    workouts = _fetch_workouts(start, end)

    by_sport: dict[str, dict] = {}
    total_minutes = 0.0
    total_tss = 0.0
    known_minutes = 0
    known_tss = 0
    for w in workouts:
        sport = w.sport or "Unknown"
        bucket = by_sport.setdefault(sport, {"count": 0, "minutes": 0.0, "tss": 0.0})
        bucket["count"] += 1
        if w.duration_minutes is not None:
            bucket["minutes"] += w.duration_minutes
            total_minutes += w.duration_minutes
            known_minutes += 1
        if w.tss is not None:
            bucket["tss"] += w.tss
            total_tss += w.tss
            known_tss += 1

    return _dump(
        {
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "workout_count": len(workouts),
            "total_planned_minutes": round(total_minutes, 1) if known_minutes else None,
            "total_planned_tss": round(total_tss, 1) if known_tss else None,
            "note": (
                "minutes/TSS totals only include workouts where that metric could be "
                "parsed out of the calendar feed; missing figures are omitted, not zero."
            ),
            "by_sport": {
                sport: {
                    "count": v["count"],
                    "minutes": round(v["minutes"], 1),
                    "tss": round(v["tss"], 1),
                }
                for sport, v in by_sport.items()
            },
        }
    )


@mcp.tool()
def refresh_calendar() -> str:
    """Force a re-fetch of the TrainerRoad calendar feed, bypassing the cache."""
    try:
        calendar = _get_feed().get(force_refresh=True)
    except CalendarFetchError as exc:
        raise RuntimeError(str(exc)) from exc
    event_count = sum(1 for c in calendar.walk() if c.name == "VEVENT")
    return _dump({"refreshed": True, "event_count": event_count})


@mcp.resource("trainerroad://calendar/upcoming")
def upcoming_calendar_resource() -> str:
    """The next 28 days of TrainerRoad workouts, as JSON."""
    start, end = default_window(days_back=0, days_forward=28)
    workouts = _fetch_workouts(start, end)
    return _dump([w.to_dict() for w in workouts])


def _workout_date(w: Workout) -> date:
    return w.start.date() if isinstance(w.start, datetime) else w.start


def _non_negative(value: int, field_name: str):
    from datetime import timedelta

    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return timedelta(days=value)


def _one_day():
    from datetime import timedelta

    return timedelta(days=1)


def _dump(payload) -> str:
    return json.dumps(payload, indent=2, default=str)


def main() -> None:
    try:
        load_config()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc
    mcp.run()


if __name__ == "__main__":
    main()
