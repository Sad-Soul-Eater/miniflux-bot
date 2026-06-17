# miniflux-bot

[![CI](https://github.com/Sad-Soul-Eater/miniflux-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Sad-Soul-Eater/miniflux-bot/actions/workflows/ci.yml)

A small Telegram bot that watches your [Miniflux](https://miniflux.app/) feeds and pushes each new unread entry to a Telegram chat. Every message comes with inline buttons so you can triage entries - mark them read/unread or delete them - straight from Telegram, with the action reflected back in Miniflux.

## How it works

The bot runs two cooperating async tasks:

- **Miniflux poller** - every `MINIFLUX_POLL_INTERVAL` seconds it asks Miniflux for the latest unread entry. If anything new has appeared since the last enqueued entry, it fetches all unread entries since that point and queues them for delivery.
- **Telegram notifier** - drains the queue and sends one message per entry. The message shows the feed title and a link to the article, plus **Read** and **Delete** action buttons. Tapping a button calls back into Miniflux (`mark_read` / `mark_unread`) and updates the message in place.

Delivery is at-least-once and ordered by entry ID. The highest successfully-delivered entry ID is persisted as `processed_id`, so the bot resumes where it left off after a restart instead of replaying old entries.

Transient failures (Telegram rate limits, network/server errors) re-queue the entry with backoff - honoring Telegram's `retry_after` when provided, otherwise exponential backoff capped at 300s. Non-transient errors drop the entry and log it.

## Requirements

- Python **3.14+**
- A running Miniflux instance and an [API key](https://miniflux.app/docs/api.html#authentication)
- A Telegram bot token (from [@BotFather](https://t.me/BotFather)) and the target chat ID

## Configuration

Configuration is read from environment variables (a local `.env` file is loaded automatically). Copy `.env.example` to `.env` and fill it in:

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `MINIFLUX_URL` | yes | - | Base URL of your Miniflux instance |
| `MINIFLUX_API_KEY` | yes | - | Miniflux API key |
| `TELEGRAM_BOT_TOKEN` | yes | - | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | yes | - | Chat ID to deliver entries to |
| `MINIFLUX_STORE_BACKEND` | yes | - | State backend: `memory` or `sqlite` |
| `MINIFLUX_POLL_INTERVAL` | no | `60` | Seconds between Miniflux polls |
| `MINIFLUX_SQLITE_STORE_PATH` | only if `sqlite` | - | Directory for the SQLite file (`bot.sqlite` is created inside it) |

### State backends

- `memory` - an in-memory SQLite database. State is lost on restart, so the bot will re-deliver unread entries on the next run. Fine for testing.
- `sqlite` - a persistent SQLite database at `<MINIFLUX_SQLITE_STORE_PATH>/bot.sqlite`. Use this in production and mount the directory as a volume so progress survives restarts.

## Running

### With uv (local)

```bash
uv sync
uv run python -m miniflux_bot
```

### With Docker

Pre-built images are published to the GitHub Container Registry on each release:

```bash
docker run --rm --env-file .env \
  -e MINIFLUX_STORE_BACKEND=sqlite \
  -e MINIFLUX_SQLITE_STORE_PATH=/data \
  -v "$(pwd)/data:/data" \
  ghcr.io/sad-soul-eater/miniflux-bot:latest
```

Image tags track the release version - `:1.2.3`, `:1.2`, and `:latest`. To build the image yourself instead:

```bash
docker build -t miniflux-bot .
docker run --rm --env-file .env \
  -e MINIFLUX_STORE_BACKEND=sqlite \
  -e MINIFLUX_SQLITE_STORE_PATH=/data \
  -v "$(pwd)/data:/data" \
  miniflux-bot
```

The container runs `python -m miniflux_bot`. Mount a volume at the path given by `MINIFLUX_SQLITE_STORE_PATH` to persist state.

## Project layout

| File | Responsibility |
| --- | --- |
| `__main__.py` | Wires up config, state store, gateway, and bots; runs them in a task group |
| `bot.py` | `MinifluxBot` - poll loop, delivery queue, retry/backoff |
| `telegram.py` | `TelegramBot` - sends messages, handles inline button callbacks |
| `gateway.py` | `MinifluxGateway` - async wrapper over the Miniflux client |
| `state.py` | `StateStore` / `SqliteStateStore` - persists `processed_id` |
| `notifier.py` | `Notifier` interface and transient-failure exception |
| `models.py` | `Entry` domain model |
| `config.py` | Environment variable helpers |

## Development

Install everything (including the `dev` group) and run the same checks CI does:

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pyrefly check
```

CI runs lint, an import smoke test, and a Docker build on every push and pull request. Dependencies are pinned and kept up to date by Renovate.

## Releases

The package version is derived from git tags by [hatch-vcs](https://github.com/ofek/hatch-vcs) - there is no version field to bump by hand. To cut a release:

```bash
git tag v1.2.3
git push origin v1.2.3
```

The release workflow builds the image, pushes it to GHCR tagged `1.2.3` / `1.2` / `latest`, and publishes a GitHub Release with auto-generated notes. Between tags, builds report a development version such as `1.2.3.dev4+g<sha>`.

## Tech stack

[aiogram](https://docs.aiogram.dev/) for Telegram, the official [miniflux](https://pypi.org/project/miniflux/) client for the feed reader, and [python-dotenv](https://pypi.org/project/python-dotenv/) for local configuration.
