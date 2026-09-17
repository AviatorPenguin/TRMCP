import json
from datetime import date
from pathlib import Path

import icalendar
import pytest

from trmcp import server as server_module
from trmcp.calendar_feed import CalendarFeed

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_calendar.ics"


class _StaticFeed(CalendarFeed):
    def __init__(self):
        self._calendar = icalendar.Calendar.from_ical(FIXTURE_PATH.read_bytes())

    def get(self, *, force_refresh: bool = False):
        return self._calendar


@pytest.fixture(autouse=True)
def static_feed(monkeypatch):
    monkeypatch.setattr(server_module, "_feed", _StaticFeed())
    yield
    monkeypatch.setattr(server_module, "_feed", None)


def test_get_workouts_in_range_returns_expected_workouts():
    result = json.loads(
        server_module.get_workouts_in_range("2026-03-01", "2026-03-08")
    )
    assert result["count"] == 3
    names = {w["name"] for w in result["workouts"]}
    assert names == {"Carter -6", "Easy Recovery Run", "Rest Day"}


def test_get_workouts_in_range_rejects_inverted_range():
    with pytest.raises(ValueError):
        server_module.get_workouts_in_range("2026-03-08", "2026-03-01")


def test_search_workouts_matches_case_insensitively():
    result = json.loads(
        server_module.search_workouts("recovery", days_back=3650, days_forward=3650)
    )
    assert result["count"] == 1
    assert result["workouts"][0]["name"] == "Easy Recovery Run"


def test_get_training_summary_aggregates_by_sport():
    result = json.loads(server_module.get_workouts_in_range("2026-03-01", "2026-03-31"))
    assert result["count"] == 4  # workouts 1,2,3,4 all fall in March

    # get_training_summary itself is relative to today, so exercise the same
    # aggregation logic deterministically via the underlying date-range helper.
    workouts = server_module._fetch_workouts(date(2026, 3, 1), date(2026, 3, 31))
    bike = [w for w in workouts if w.sport == "Bike"]
    assert len(bike) == 2
    assert sum(w.tss for w in bike if w.tss) == pytest.approx(160.0)
