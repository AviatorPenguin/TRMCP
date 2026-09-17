"""Turns raw iCalendar VEVENTs from the TrainerRoad feed into structured workouts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import icalendar
import recurring_ical_events

# Best-effort patterns for the structured metrics TrainerRoad (and similar tools like
# TrainingPeaks) tend to embed as plain text in an event's DESCRIPTION. The feed's exact
# wording isn't publicly documented, so these are deliberately loose and every field is
# optional -- `notes` always carries the untouched original text as a fallback.
_DURATION_HHMMSS_RE = re.compile(r"\b(\d{1,2}):(\d{2}):(\d{2})\b")
_DURATION_HM_RE = re.compile(r"\b(\d{1,3})\s*h(?:r|rs|our|ours)?\s*(\d{1,2})?\s*m(?:in|ins)?\b", re.I)
_DURATION_MIN_ONLY_RE = re.compile(r"\bDuration\s*:?\s*(\d{1,4})\s*(?:min|minutes)\b", re.I)
_TSS_RE = re.compile(r"\bTSS\s*:?\s*(\d+(?:\.\d+)?)", re.I)
_IF_RE = re.compile(r"\bIF\s*:?\s*(\d\.\d+)", re.I)
_DISTANCE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(km|mi|miles)\b", re.I)

_SPORT_KEYWORDS = (
    ("run", "Run"),
    ("swim", "Swim"),
    ("strength", "Strength"),
    ("yoga", "Yoga"),
    ("walk", "Walk"),
    ("brick", "Brick"),
    ("bike", "Bike"),
    ("ride", "Bike"),
    ("cycling", "Bike"),
)


@dataclass
class Workout:
    uid: str
    name: str
    start: datetime | date
    end: datetime | date | None
    all_day: bool
    sport: str | None
    duration_minutes: float | None
    tss: float | None
    intensity_factor: float | None
    distance: tuple[float, str] | None
    notes: str
    raw_categories: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "name": self.name,
            "date": self.start.date().isoformat() if isinstance(self.start, datetime) else self.start.isoformat(),
            "start": self.start.isoformat() if isinstance(self.start, datetime) else None,
            "end": self.end.isoformat() if isinstance(self.end, datetime) else None,
            "all_day": self.all_day,
            "sport": self.sport,
            "duration_minutes": self.duration_minutes,
            "tss": self.tss,
            "intensity_factor": self.intensity_factor,
            "distance": (
                {"value": self.distance[0], "unit": self.distance[1]} if self.distance else None
            ),
            "notes": self.notes,
        }


def _coerce_start(value) -> datetime | date:
    dt = value.dt
    return dt


def _guess_sport(summary: str, categories: list[str]) -> str | None:
    haystack = " ".join([summary, *categories]).lower()
    for keyword, label in _SPORT_KEYWORDS:
        if keyword in haystack:
            return label
    return None


def _parse_duration_minutes(text: str, start, end) -> float | None:
    if isinstance(start, datetime) and isinstance(end, datetime) and end > start:
        return round((end - start).total_seconds() / 60, 1)

    match = _DURATION_HHMMSS_RE.search(text)
    if match:
        hours, minutes, seconds = (int(g) for g in match.groups())
        return round(hours * 60 + minutes + seconds / 60, 1)

    match = _DURATION_HM_RE.search(text)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2)) if match.group(2) else 0
        return float(hours * 60 + minutes)

    match = _DURATION_MIN_ONLY_RE.search(text)
    if match:
        return float(match.group(1))

    return None


def _parse_distance(text: str) -> tuple[float, str] | None:
    match = _DISTANCE_RE.search(text)
    if not match:
        return None
    value, unit = match.groups()
    return float(value), unit.lower()


def parse_event(component: icalendar.Event) -> Workout:
    summary = str(component.get("summary", "")).strip() or "Untitled workout"
    description = str(component.get("description", "")).strip()
    categories_prop = component.get("categories")
    if categories_prop is None:
        categories: list[str] = []
    elif isinstance(categories_prop, list):
        categories = [str(c) for cats in categories_prop for c in getattr(cats, "cats", [cats])]
    else:
        categories = [str(c) for c in getattr(categories_prop, "cats", [categories_prop])]

    start = _coerce_start(component["dtstart"])
    end = _coerce_start(component["dtend"]) if component.get("dtend") is not None else None
    all_day = not isinstance(start, datetime)

    combined_text = f"{summary}\n{description}"

    uid = str(component.get("uid", "")) or f"{summary}-{start}"

    return Workout(
        uid=uid,
        name=summary,
        start=start,
        end=end,
        all_day=all_day,
        sport=_guess_sport(summary, categories),
        duration_minutes=_parse_duration_minutes(combined_text, start, end),
        tss=float(m.group(1)) if (m := _TSS_RE.search(combined_text)) else None,
        intensity_factor=float(m.group(1)) if (m := _IF_RE.search(combined_text)) else None,
        distance=_parse_distance(combined_text),
        notes=description,
        raw_categories=categories,
    )


def expand_events(calendar: icalendar.Calendar, start: date, end: date) -> list[Workout]:
    """Expand (including recurring) events overlapping [start, end) into Workouts, sorted by start."""
    occurrences = recurring_ical_events.of(calendar).between(start, end)
    workouts = [parse_event(occ) for occ in occurrences]
    workouts.sort(key=lambda w: (w.start.isoformat() if isinstance(w.start, datetime) else f"{w.start}T00:00:00"))
    return workouts


def default_window(days_back: int = 7, days_forward: int = 28) -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=days_back), today + timedelta(days=days_forward)
