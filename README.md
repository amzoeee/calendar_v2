# Calendar v2

A personal, self-hosted Flask calendar with daily/weekly views, tag-based time tracking, recurring events, and a CLI tool for bulk-importing activity logs.

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set SECRET_KEY in .env — generate one with:
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Running

```bash
./run_local.sh
```

Starts the server and prints your local IP. Access at `http://localhost:5002` (or `http://<your-ip>:5002` from other devices on the same network).

## Features

- **Daily & weekly views** — click any time slot to create an event
- **Recurring events** — edit/delete a single instance or the whole series
- **Tags** — color-coded categories; drag to reorder; stats view shows time breakdown per tag
- **ICS import** — import from Google Calendar or any `.ics` file via Settings
- **Multi-user** — separate accounts with login/registration

## Log Importer (`import_log.py`)

A CLI tool that parses a shorthand activity log and bulk-inserts events into the database.

```
python3 import_log.py [--file <path>] [--date <YYYY-MM-DD>] [--user-id <id>] [--dry-run] [--continue]
```

**Log format** — one activity per line, starting with a time in shorthand followed by the title:

```
900 Sleep
1130 Breakfast
1 Gym
330pm Work
```

Times are resolved chronologically — no need to specify AM/PM unless ambiguous. The script auto-detects the date from Discord-style timestamps in the log, skips lines before the last `---` separator, predicts tags from past events, and avoids creating overlaps with existing events.

| Flag | Description |
|---|---|
| `--file` | Path to log file (defaults to stdin) |
| `--date` | Override the target date (`YYYY-MM-DD`) |
| `--user-id` | User account to insert events for (default: 1) |
| `--dry-run` | Preview without inserting |
| `--continue` | Schedule after the latest existing event on that day |

## Project Structure

```
calendar_v2/
├── app.py           # Flask routes and application logic
├── database.py      # DB schema and operations
├── import_log.py    # CLI log importer
├── run_local.sh     # Startup script
├── utils/
│   └── ics_parser.py
├── templates/       # HTML templates (daily, weekly, stats, settings)
└── static/          # CSS and assets
```

## Stack

Flask · SQLite · Flask-Login · vanilla HTML/CSS/JS
