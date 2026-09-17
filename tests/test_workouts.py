from datetime import date
from pathlib import Path

import icalendar
import pytest

from trmcp.workouts import expand_events, parse_event

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_calendar.ics"


@pytest.fixture
def calendar() -> icalendar.Calendar:
    return icalendar.Calendar.from_ical(FIXTURE_PATH.read_bytes())


def test_expand_events_filters_to_window(calendar):
    workouts = expand_events(calendar, date(2026, 3, 1), date(2026, 3, 8))
    uids = [w.uid for w in workouts]
    assert uids == [
        "workout-1@trainerroad.com",
        "workout-2@trainerroad.com",
        "workout-3@trainerroad.com",
    ]


def test_expand_events_excludes_out_of_range(calendar):
    workouts = expand_events(calendar, date(2026, 3, 1), date(2026, 3, 8))
    uids = {w.uid for w in workouts}
    assert "workout-4@trainerroad.com" not in uids
    assert "workout-5@trainerroad.com" not in uids


def test_expand_events_sorted_by_start(calendar):
    workouts = expand_events(calendar, date(2026, 3, 1), date(2026, 3, 31))
    starts = [w.start for w in workouts]
    assert starts == sorted(starts, key=str)


def test_parses_duration_tss_if_from_hhmmss_description(calendar):
    event = next(c for c in calendar.walk() if c.get("uid") == "workout-1@trainerroad.com")
    workout = parse_event(event)
    assert workout.name == "Carter -6"
    assert workout.sport == "Bike"
    assert workout.duration_minutes == 60.0
    assert workout.tss == 65.0
    assert workout.intensity_factor == 0.83


def test_parses_duration_from_hour_minute_text(calendar):
    event = next(c for c in calendar.walk() if c.get("uid") == "workout-4@trainerroad.com")
    workout = parse_event(event)
    assert workout.duration_minutes == 90.0
    assert workout.tss == 95.0


def test_falls_back_to_dtstart_dtend_diff_when_no_explicit_duration_text(calendar):
    event = next(c for c in calendar.walk() if c.get("uid") == "workout-2@trainerroad.com")
    workout = parse_event(event)
    assert workout.sport == "Run"
    # DTSTART/DTEND span 30 minutes even though the description doesn't say "Duration:"
    assert workout.duration_minutes == 30.0
    assert workout.distance == (5.0, "km")


def test_all_day_event_has_no_time_component(calendar):
    event = next(c for c in calendar.walk() if c.get("uid") == "workout-3@trainerroad.com")
    workout = parse_event(event)
    assert workout.all_day is True
    assert workout.start == date(2026, 3, 7)
    assert workout.duration_minutes is None
    assert workout.tss is None


def test_workout_with_no_parseable_metrics_keeps_raw_notes(calendar):
    event = next(c for c in calendar.walk() if c.get("uid") == "workout-3@trainerroad.com")
    workout = parse_event(event)
    assert workout.notes == "No structured workout scheduled."


def test_to_dict_is_json_serializable(calendar):
    import json

    workouts = expand_events(calendar, date(2026, 3, 1), date(2026, 3, 8))
    json.dumps([w.to_dict() for w in workouts])
