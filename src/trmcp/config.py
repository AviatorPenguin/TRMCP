"""Configuration for the TRMCP server, sourced from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

CALENDAR_URL_ENV = "TRAINERROAD_CALENDAR_URL"
CACHE_TTL_ENV = "TRMCP_CACHE_TTL_SECONDS"
DEFAULT_CACHE_TTL_SECONDS = 300


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    calendar_url: str
    cache_ttl_seconds: int


def _normalize_calendar_url(raw_url: str) -> str:
    """Turn a TrainerRoad "webcal://" subscription link into a fetchable https:// URL.

    TrainerRoad's calendar-sync page (https://www.trainerroad.com/profile/calendar-sync)
    hands out a link starting with ``webcal://``, which calendar apps resolve to
    ``https://`` themselves. Plain HTTP clients don't know that scheme, so we do the
    same translation here.
    """
    url = raw_url.strip()
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://") :]
    return url


def load_config() -> Config:
    raw_url = os.environ.get(CALENDAR_URL_ENV)
    if not raw_url:
        raise ConfigError(
            f"{CALENDAR_URL_ENV} is not set. Get your private calendar URL from "
            "https://www.trainerroad.com/profile/calendar-sync and set it as an "
            f"environment variable, e.g. {CALENDAR_URL_ENV}=webcal://api.trainerroad.com/..."
        )

    calendar_url = _normalize_calendar_url(raw_url)
    if not calendar_url.startswith("https://") and not calendar_url.startswith("http://"):
        raise ConfigError(
            f"{CALENDAR_URL_ENV} must be an http(s):// or webcal:// URL, got: {raw_url!r}"
        )

    ttl_raw = os.environ.get(CACHE_TTL_ENV, str(DEFAULT_CACHE_TTL_SECONDS))
    try:
        cache_ttl_seconds = int(ttl_raw)
    except ValueError as exc:
        raise ConfigError(f"{CACHE_TTL_ENV} must be an integer number of seconds") from exc

    return Config(calendar_url=calendar_url, cache_ttl_seconds=cache_ttl_seconds)
