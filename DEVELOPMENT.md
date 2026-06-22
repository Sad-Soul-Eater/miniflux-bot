# Development

Internal design, project layout, and maintenance workflow for miniflux-bot. For installation and configuration, see
the [README](README.md).

## How it works

The bot runs two cooperating async tasks:

- **Miniflux poller** - every `MINIFLUX_POLL_INTERVAL` seconds it asks Miniflux for the latest unread entry. If anything
  new has appeared since the last enqueued entry, it fetches all unread entries since that point and queues them for
  delivery.
- **Telegram notifier** - drains the queue and sends one message per entry. The message shows the feed title and a link
  to the article, plus **Read** and **Delete** action buttons. Tapping a button calls back into Miniflux (`mark_read` /
  `mark_unread`) and updates the message in place.

Delivery is at-least-once and ordered by entry ID. The highest successfully-delivered entry ID is persisted as
`processed_id`, so the bot resumes where it left off after a restart instead of replaying old entries.

State lives behind the `StateStore` interface, chosen by `MINIFLUX_STORE_BACKEND`: `SqliteStateStore` (backing both the
`sqlite` file and the in-memory `:memory:` backend) or `PostgresStateStore`. SQLite wraps the synchronous `sqlite3`
driver in `asyncio.to_thread`; Postgres uses psycopg's native async API over a connection pool that health-checks each
checkout, so it transparently reconnects when the database restarts (e.g. during a cluster upgrade).

Transient failures (Telegram rate limits, network/server errors) re-queue the entry with backoff - honoring Telegram's
`retry_after` when provided, otherwise exponential backoff capped at 300s. Non-transient errors drop the entry and log
it.

## Project layout

| File          | Responsibility                                                             |
|---------------|----------------------------------------------------------------------------|
| `__main__.py` | Wires up config, state store, gateway, and bots; runs them in a task group |
| `bot.py`      | `MinifluxBot` - poll loop, delivery queue, retry/backoff                   |
| `telegram.py` | `TelegramBot` - sends messages, handles inline button callbacks            |
| `gateway.py`  | `MinifluxGateway` - async wrapper over the Miniflux client                 |
| `state/`      | `StateStore` ABC + SQLite/Postgres backends - persists `processed_id`      |
| `notifier.py` | `Notifier` interface and transient-failure exception                       |
| `models.py`   | `Entry` domain model                                                       |
| `config.py`   | Environment variable helpers                                               |

## Local development

Install everything (including the `dev` group) and run the same checks CI does:

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pyrefly check
MINIFLUX_SQLITE_STORE_PATH=. uv run python -m miniflux_bot
```

## Continuous integration

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs on every push and pull request:

- **lint** - `ruff check` + `ruff format --check`
- **build** - `uv sync --locked` (fails if `uv.lock` drifts from `pyproject.toml`) and an import smoke test that pulls
  in the whole module graph
- **docker** - a Docker build to catch Dockerfile regressions. On pushes to `main` it also pushes the image to GHCR
  tagged `main` (a rolling latest-commit image) and `sha-<short>`

Dependencies and GitHub Actions are kept current by Renovate ([`renovate.json5`](renovate.json5)); low-risk updates (
patch, digest, lockfile maintenance) automerge once CI is green.

## Releases

The package version is derived from git tags by [hatch-vcs](https://github.com/ofek/hatch-vcs) - there is no version
field to bump by hand. To cut a release:

```bash
git tag v1.2.3
git push origin v1.2.3
```

The release workflow ([`.github/workflows/release.yml`](.github/workflows/release.yml)) builds the image, pushes it to
GHCR tagged `1.2.3` / `1.2` / `latest`, and publishes a GitHub Release with auto-generated notes. Between tags, builds
report a development version such as `1.2.3.dev4+g<sha>`.

Inside the Docker build there is no git history (`.git` is excluded from the build context), so the version is passed in
via the `VERSION` build arg, which sets `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MINIFLUX_BOT`. Non-release builds fall back
to a `0.0.0` default.

## Tech stack

[aiogram](https://docs.aiogram.dev/) for Telegram, the official [miniflux](https://pypi.org/project/miniflux/) client
for the feed reader, [python-dotenv](https://pypi.org/project/python-dotenv/) for local configuration, and
[psycopg](https://www.psycopg.org/psycopg3/) (with its async connection pool) for the Postgres state backend. Managed with
[uv](https://docs.astral.sh/uv/) and built with [hatchling](https://hatch.pypa.io/) + hatch-vcs.
