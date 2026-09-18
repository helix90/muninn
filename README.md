# Muninn — Agent-Based Automation Platform

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-1037%20passing-brightgreen.svg)](tests/)

Muninn is a self-hosted automation platform built with Flask and PostgreSQL. Inspired by [Huginn](https://github.com/huginn/huginn), it lets you build pipelines of single-responsibility **agents** that watch for events, transform data, and take actions — all wired together into scenarios you can export, share, and import.

Named after one of Odin's ravens, Muninn ("memory") keeps watch so you don't have to.

---

## Features

- **33 built-in agent types** — sources, transforms, and actions covering RSS, HTTP, email, IMAP, MQTT, S3, Dropbox, Slack, Telegram, Discord, Jabber, webhooks, and more
- **Scenario editor** — visual pipeline canvas for connecting agents; export/import scenarios as portable JSON
- **Credential vault** — encrypted credential storage with `{{credential:name}}` templating in agent configs; importable/exportable
- **REST API** — full CRUD for agents, events, and scenarios behind Bearer token auth (`/api/v1/`)
- **Pipeline trace** — every event propagation gets a UUID so you can follow data through the full agent chain
- **Template library** — 8 bundled ready-to-import scenario templates from beginner to advanced
- **Health dashboard** — per-agent health tracking, consecutive failure counts, and email alerting (`/health/`)
- **Manual test mode** — run any agent ephemerally against a custom payload before enabling it in production
- **Human-readable scheduler** — dropdown picker for common schedules ("Daily at 7 AM") alongside full cron expression support
- **Huginn migration tool** — `tools/huginn_import.py` converts a Huginn scenario export to Muninn format, translating Liquid templates to Jinja2 and mapping agent types automatically
- **APScheduler integration** — agents run on their own cron schedules with no external job queue needed
- **Dark mode** — full light/dark theme support throughout the UI

---

## Agent Types

### Source Agents
Fetch data from external sources on a schedule.

| Agent | Description |
|-------|-------------|
| `rss_agent` | Monitor RSS/Atom feeds |
| `web_fetch_agent` | Fetch web pages via HTTP GET |
| `api_call_agent` | Call any REST API (GET/POST/PUT/PATCH/DELETE); supports `{{credential:name}}` in URLs and headers |
| `webhook_agent` | Receive inbound HTTP webhooks |
| `imap_agent` | Monitor email inboxes via IMAP |
| `mqtt_subscriber_agent` | Subscribe to MQTT topics |
| `s3_bucket_monitor_agent` | Watch an AWS S3 bucket for new or changed files |
| `scheduler_agent` | Emit time-based trigger events |
| `jabber_listener_agent` | Receive incoming XMPP/Jabber messages |
| `datastore_read_agent` | Read key-value data from the shared DataStore |
| `dropbox_read_agent` | Monitor a Dropbox folder for new or modified files |

### Transform Agents
Receive events from upstream agents, reshape the data, and pass results downstream.

| Agent | Description |
|-------|-------------|
| `filter_agent` | Keep only events that match configurable rules (contains, regex, equals, exists, …) |
| `template_agent` | Reshape event payloads using Jinja2 templates |
| `jsonpath_agent` | Extract fields using JSONPath expressions |
| `html_parser_agent` | Extract data from HTML via CSS selectors |
| `csv_parser_agent` | Parse CSV content into structured events |
| `deduplication_agent` | Drop events already seen within a rolling time window |
| `aggregation_agent` | Batch events into time- or count-based windows |
| `router_agent` | Tag events with a route name for conditional branching |
| `delay_agent` | Buffer events and release them after a fixed delay |
| `datastore_write_agent` | Persist key-value data to the shared DataStore |
| `frequency_tracker_agent` | Track how often topics appear over a rolling window |
| `topic_extract_agent` | Extract naive topic terms from event text fields |
| `hype_term_agent` | Score term novelty against a noise-reference feed |
| `signal_score_agent` | Aggregate per-term scores into a composite signal |

### Action Agents
Consume events and perform terminal actions (no output events).

| Agent | Description |
|-------|-------------|
| `email_agent` | Send emails via SMTP |
| `http_post_agent` | Send HTTP POST/PUT/PATCH requests |
| `slack_agent` | Post messages to Slack via Incoming Webhooks |
| `telegram_agent` | Send messages to Telegram chats via Bot API |
| `discord_webhook_agent` | Post messages to Discord channels via webhooks |
| `jabber_agent` | Send XMPP/Jabber messages |
| `mqtt_publisher_agent` | Publish events to MQTT topics |
| `dropbox_write_agent` | Upload event content as a file to Dropbox |

---

## Quick Start

### Using Docker (Recommended)

```bash
git clone https://github.com/helix90/muninn.git
cd muninn
cp .env.example .env          # edit SECRET_KEY at minimum
docker compose -f docker/docker-compose.yml up -d
```

The app is available at `http://localhost:5000`. The first user you register becomes the admin.

### Local Development

```bash
git clone https://github.com/helix90/muninn.git
cd muninn

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
pip install -r requirements-dev.txt

# Create databases
createdb muninn_dev
createdb muninn_test

cp .env.example .env          # edit DATABASE_URL, SECRET_KEY, SMTP_* as needed
flask db upgrade             # run all migrations
flask run
```

---

## Configuration

All configuration is via environment variables (`.env` file loaded automatically by `python-dotenv`).

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session signing key — **change this in production** | `dev-secret-key-change-in-production` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://muninn:muninn_pass@localhost:5432/muninn_dev` |
| `TEST_DATABASE_URL` | Test database | `postgresql://muninn:muninn_pass@localhost:5432/muninn_test` |
| `FLASK_ENV` | `development` / `production` | `development` |
| `FLASK_DEBUG` | Debug mode (disables scheduler guard) | `True` |
| `FLASK_HOST` | Bind address | `0.0.0.0` |
| `FLASK_PORT` | Port | `5000` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `SMTP_SERVER` | SMTP hostname (required for email agents) | — |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USE_TLS` | Use STARTTLS | `True` |
| `SMTP_USERNAME` | SMTP login | — |
| `SMTP_PASSWORD` | SMTP password | — |
| `SMTP_FROM_EMAIL` | Sender address | falls back to `SMTP_USERNAME` |

### Email Setup (Gmail)

1. Enable 2-Factor Authentication on your Gmail account
2. Generate an App Password at <https://myaccount.google.com/apppasswords>
3. Set in `.env`:

```bash
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=True
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=your-16-char-app-password
```

---

## Scenarios

Scenarios group agents into named pipelines and let you visualise the event flow in the canvas editor.

**Export** any scenario as a self-contained JSON file: `Scenarios → ⋮ → Export`. The file includes all agents, links, config, and schedule — but never credential values (those stay in the vault).

**Import** on any Muninn instance: `Scenarios → Import Scenario`. Agents are created owned by the importing user; any missing credential names are flagged as warnings.

**Ready-made examples** are in the [`examples/`](examples/) directory:

| File | Description |
|------|-------------|
| `pirate_weather_report.json` | Daily forecast from Pirate Weather — high/low, precipitation, moon phase, sunrise/sunset |
| `airnow_aqi_report.json` | Daily AQI report from AirNow — overall AQI, per-pollutant breakdown, health guidance |
| `dropbox_inbox_watcher.json` | Email notification for every new file uploaded to a watched Dropbox folder |
| `dropbox_rss_archive.json` | Save each new RSS article as a plain-text file in Dropbox, deduplicated over 30 days |

**Converted Huginn scenarios** are in [`examples/huginn/`](examples/huginn/) — 19 real-world scenarios translated from Huginn to Muninn format, importable directly via Scenarios → Import Scenario:

| File | Huginn scenario | Agents |
|------|----------------|--------|
| `RSS_to_Jabber.json` | RSS to Jabber | 8 |
| `airwall-things.json` | Airwall Things | 29 |
| `article-grabber.json` | Article Grabber | 4 |
| `bbc-news.json` | BBC News | 7 |
| `blog-post-agents.json` | Blog Post Agents (weather-based) | 6 |
| `default-scenario.json` | Default Scenario (weather + XKCD digest) | 13 |
| `e-mail-testing.json` | E-mail Testing | 4 |
| `email-checker.json` | Email Checker | 2 |
| `hacking-things.json` | Hacking Things (security news feeds) | 13 |
| `key-value-testing.json` | Key Value Testing | 6 |
| `mqtt-testing.json` | MQTT Testing | 3 |
| `new-script-extender.json` | New Script Extender | 4 |
| `news-sources.json` | News Sources | 8 |
| `newspaper-layout.json` | Newspaper Layout | 13 |
| `research-testing.json` | Research Testing (IP monitoring) | 7 |
| `rube-goldberg.json` | Rube Goldberg | 4 |
| `washington-quakes.json` | Washington Quakes | 4 |
| `weather-on-demand.json` | Weather on Demand | 1 |
| `weather.json` | Weather (full pipeline) | 12 |

---

## Importing from Huginn

If you're migrating from [Huginn](https://github.com/huginn/huginn), use the included conversion tool to translate a Huginn scenario export into a Muninn-importable JSON file and push it directly via the REST API.

```bash
python tools/huginn_import.py my_huginn_export.json \
    --api-url http://localhost:5000 \
    --api-token YOUR_API_TOKEN

# Preview what will be imported without writing anything
python tools/huginn_import.py my_huginn_export.json \
    --api-url http://localhost:5000 \
    --api-token YOUR_API_TOKEN \
    --dry-run --verbose

# Save the translated JSON without importing (for review or manual import)
python tools/huginn_import.py my_huginn_export.json \
    --api-url http://localhost:5000 \
    --api-token YOUR_API_TOKEN \
    --output translated.json
```

Export your scenario from Huginn via `Scenarios → Export`. The tool handles Huginn's Liquid template syntax (converting it to Jinja2), schedule strings (`every_1h` → `0 * * * *`), and Huginn's agent propagation graph.

**Agent mapping coverage:**

| Huginn agent | Muninn equivalent | Fidelity |
|---|---|---|
| RssAgent | `rss_agent` | Full |
| WebhookAgent | `webhook_agent` | Full |
| PostAgent | `http_post_agent` | Full |
| DeduplicationAgent | `deduplication_agent` | Full |
| DelayAgent | `delay_agent` | Full |
| SlackAgent | `slack_agent` | Full |
| TelegramAgent | `telegram_agent` | Full |
| TriggerAgent | `filter_agent` | Approximated |
| EventFormattingAgent | `template_agent` | Approximated |
| EmailAgent | `email_agent` | Approximated |
| WebsiteAgent | `web_fetch_agent` + `html_parser_agent` | Approximated |
| SchedulerAgent | schedule applied to controlled agents | Absorbed |
| TwitterAgent, JavaScriptAgent, DataOutputAgent, EventDiffAgent | — | Skipped |

Skipped agents are noted in the tool output; the rest of the scenario imports cleanly.

The [`examples/huginn/`](examples/huginn/) directory contains 19 pre-converted scenarios from the `Huginn Scenarios/` source files, ready to import without running the tool yourself.

---

## REST API

The REST API lives at `/api/v1/` and is secured with Bearer tokens.

**Create a token**: Settings → API Tokens → New Token.

```bash
curl -H "Authorization: Bearer <token>" http://localhost:5000/api/v1/agents
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/agents` | List agents |
| `GET` | `/api/v1/agents/<id>` | Get agent |
| `POST` | `/api/v1/agents` | Create agent |
| `PATCH` | `/api/v1/agents/<id>` | Update agent |
| `DELETE` | `/api/v1/agents/<id>` | Delete agent |
| `GET` | `/api/v1/events` | List events |
| `GET` | `/api/v1/events/<id>` | Get event |
| `GET` | `/api/v1/scenarios` | List scenarios |
| `GET` | `/api/v1/scenarios/<id>` | Get scenario |
| `POST` | `/api/v1/scenarios` | Create scenario |
| `PATCH` | `/api/v1/scenarios/<id>` | Update scenario |
| `POST` | `/api/v1/scenarios/import` | Import scenario from JSON |
| `GET` | `/api/v1/tokens` | List API tokens |

---

## Credentials

Credentials are stored encrypted (PBKDF2HMAC + Fernet, per-credential random salt). Reference them in any agent config field with `{{credential:name}}`.

**Example** — API call agent URL:
```
https://api.example.com/data?key={{credential:my_api_key}}
```

Export all credentials (decrypted) for backup or migration via `Credentials → Export`. Import re-encrypts under the local instance's key.

---

## Pipeline Trace

Every event propagation is stamped with a `propagation_id` UUID. Follow an event from source to final action at `/pipeline-runs/`. Useful for debugging pipelines that span multiple agent hops.

---

## Health & Alerting

Each agent tracks its `health_status` (`healthy` / `warning` / `critical`) and consecutive failure count. Configure an alert email on the agent edit page — Muninn emails you if the agent fails repeatedly or stops running within the expected period. Fleet-level overview at `/health/`.

---

## Testing

```bash
# Run the full suite (~1037 tests, ~8–10 minutes)
venv/bin/pytest --tb=line -q

# Run a specific file
venv/bin/pytest tests/test_scenario_export_import.py -v

# With coverage
venv/bin/pytest --cov=app --cov-report=html
```

Tests use a separate `muninn_test` database. Each test truncates tables via `DELETE` (not `TRUNCATE`) — significantly faster on this schema.

---

## Project Structure

```
muninn/
├── app/
│   ├── agents/
│   │   ├── types/              # 33 agent implementations
│   │   ├── base.py             # SourceAgent / TransformAgent / ActionAgent base classes
│   │   ├── registry.py         # Agent type registry
│   │   └── test_runner.py      # Manual test mode (ephemeral, non-persisting)
│   ├── api/                    # REST API blueprint (/api/v1/)
│   ├── auth/                   # Login / registration / password reset
│   ├── credentials/            # Encrypted credential vault
│   ├── events/                 # Event browser
│   ├── health/                 # Health dashboard (/health/)
│   ├── pipeline_runs/          # Pipeline trace by propagation_id
│   ├── scenarios/              # Scenario CRUD, canvas editor, export/import
│   ├── scheduler/              # APScheduler integration
│   ├── services/               # Business logic (agent, event, credential, health, alert)
│   ├── template_library/       # Bundled importable scenario templates
│   ├── utils/                  # Encryption, validators
│   ├── models.py               # SQLAlchemy models
│   └── extensions.py           # db, login_manager, scheduler init
├── migrations/versions/        # 16 Alembic migrations
├── tests/                      # pytest suite (~1037 tests)
├── examples/                   # Ready-to-import scenario JSON files
├── docker/                     # Dockerfile + docker-compose.yml
├── config.py                   # Development / Testing / Production configs
└── requirements.txt
```

### Database Models

| Model | Purpose |
|-------|---------|
| `User` | Authentication and resource ownership |
| `Job` | Agent definition (type, config, schedule) |
| `Scenario` | Named group of agents |
| `AgentLink` | Directed edge between agents |
| `Event` | Data payload flowing between agents |
| `AgentRun` | Execution record for each agent invocation |
| `AgentMemory` | Persistent key-value state per agent |
| `Credential` | Encrypted named secret |
| `ApiToken` | SHA-256-hashed bearer token |
| `DataStore` | Shared key-value store across agents |
| `DelayedEvent` | Events buffered by the delay agent |
| `AlertLog` | Health alert send history |

---

## Docker

```bash
# Build and start (PostgreSQL included, no Redis required)
docker compose -f docker/docker-compose.yml up -d

# View logs
docker compose -f docker/docker-compose.yml logs -f muninn

# Run migrations after pulling updates
docker compose -f docker/docker-compose.yml exec muninn flask db upgrade

# Stop
docker compose -f docker/docker-compose.yml down
```

The compose file starts two services: `muninn` (Flask app) and `postgres` (PostgreSQL 15). No Redis dependency.

---

## Database Migrations

```bash
# Apply all pending migrations
flask db upgrade

# Create a new migration after changing models.py
flask db revision --autogenerate -m "describe the change"

# Roll back one migration
flask db downgrade
```

---

## License

Copyright 2024–2026 Robert Armstrong

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the full text.

---

## Acknowledgments

- [Huginn](https://github.com/huginn/huginn) — the original inspiration for the agent/scenario model
- Flask, SQLAlchemy, APScheduler, and the broader Python open-source ecosystem
