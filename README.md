# trmcp — TrainerRoad training plan MCP server

An [MCP](https://modelcontextprotocol.io) server that lets Claude read your TrainerRoad
training plan: upcoming workouts, planned duration/TSS/intensity, and simple training-load
summaries.

It works by reading your **TrainerRoad calendar export feed** — the same private `.ics`
subscription link TrainerRoad officially provides for syncing your plan to Google
Calendar/Outlook/etc. There's no password stored anywhere and no scraping of undocumented
endpoints: it's a read-only, officially-supported export.

## 1. Get your TrainerRoad calendar URL

1. Log in at [trainerroad.com](https://www.trainerroad.com) and go to
   **https://www.trainerroad.com/profile/calendar-sync**.
2. Copy your calendar subscription URL. It looks like
   `webcal://api.trainerroad.com/api/calendar/....ics`.
3. Keep it secret — anyone with the URL can see your training calendar.

## 2. Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone <this repo>
cd trmcp
uv sync
```

## 3. Configure in Claude

Set the calendar URL as an environment variable and point Claude at the server. For
Claude Desktop / Claude Code, add to your MCP config (e.g. `claude_desktop_config.json`
or `.mcp.json`):

```json
{
  "mcpServers": {
    "trainerroad": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/trmcp", "run", "trmcp"],
      "env": {
        "TRAINERROAD_CALENDAR_URL": "webcal://api.trainerroad.com/api/calendar/....ics"
      }
    }
  }
}
```

Or run it directly for local testing:

```bash
TRAINERROAD_CALENDAR_URL="webcal://api.trainerroad.com/api/calendar/....ics" uv run trmcp
```

### Configuration

| Env var                      | Required | Default | Description                                                        |
|-------------------------------|----------|---------|----------------------------------------------------------------------|
| `TRAINERROAD_CALENDAR_URL`   | yes      | —       | Your private calendar-export URL (`webcal://` or `https://`).       |
| `TRMCP_CACHE_TTL_SECONDS`    | no       | `300`   | How long fetched calendar data is cached in memory before refetching.|

## Tools

- **list_workouts(days_back=7, days_forward=28)** — workouts in a rolling window around today.
- **get_workouts_in_range(start_date, end_date)** — workouts in an explicit `YYYY-MM-DD` range.
- **get_next_workout()** — the next upcoming workout.
- **search_workouts(query, days_back=30, days_forward=90)** — search by name/sport/notes text.
- **get_training_summary(days_back=7, days_forward=28)** — workout count, total planned
  minutes/TSS, broken down by sport.
- **refresh_calendar()** — bypass the cache and re-fetch immediately.

Each workout includes whatever the calendar feed makes available: name, date/time, sport
(best-effort guess), duration, TSS, intensity factor, distance, and the raw notes text —
some structured fields (TSS, IF, duration) are parsed out of free-text descriptions on a
best-effort basis and may be `null` if they can't be confidently parsed; the raw `notes`
field is always included so nothing is lost.

## Development

```bash
uv sync --group dev
uv run pytest
```

## Limitations

- This reads your **planned calendar**, not TrainerRoad's Adaptive Training internals —
  it won't tell you *why* a workout was picked, only what's scheduled.
- Structured metrics (TSS, IF, duration, distance) are parsed from the feed's free-text
  description with regexes since TrainerRoad doesn't publish a schema for it. If parsing
  ever seems wrong for your account, the full raw text is still returned in `notes`.
