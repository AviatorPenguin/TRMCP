import pytest

from trmcp.config import ConfigError, load_config


def test_missing_url_raises(monkeypatch):
    monkeypatch.delenv("TRAINERROAD_CALENDAR_URL", raising=False)
    with pytest.raises(ConfigError):
        load_config()


def test_webcal_scheme_normalized_to_https(monkeypatch):
    monkeypatch.setenv("TRAINERROAD_CALENDAR_URL", "webcal://api.trainerroad.com/cal.ics")
    config = load_config()
    assert config.calendar_url == "https://api.trainerroad.com/cal.ics"


def test_https_scheme_left_as_is(monkeypatch):
    monkeypatch.setenv("TRAINERROAD_CALENDAR_URL", "https://api.trainerroad.com/cal.ics")
    config = load_config()
    assert config.calendar_url == "https://api.trainerroad.com/cal.ics"


def test_default_cache_ttl(monkeypatch):
    monkeypatch.setenv("TRAINERROAD_CALENDAR_URL", "https://api.trainerroad.com/cal.ics")
    monkeypatch.delenv("TRMCP_CACHE_TTL_SECONDS", raising=False)
    config = load_config()
    assert config.cache_ttl_seconds == 300


def test_custom_cache_ttl(monkeypatch):
    monkeypatch.setenv("TRAINERROAD_CALENDAR_URL", "https://api.trainerroad.com/cal.ics")
    monkeypatch.setenv("TRMCP_CACHE_TTL_SECONDS", "60")
    config = load_config()
    assert config.cache_ttl_seconds == 60


def test_invalid_cache_ttl_raises(monkeypatch):
    monkeypatch.setenv("TRAINERROAD_CALENDAR_URL", "https://api.trainerroad.com/cal.ics")
    monkeypatch.setenv("TRMCP_CACHE_TTL_SECONDS", "not-a-number")
    with pytest.raises(ConfigError):
        load_config()
