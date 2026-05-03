# Litour (formerly heltour)

League management software for chess leagues on Lichess, now branded as lots.lichess.ca.

# Quick Start

## Prerequisites

- [devenv](https://devenv.sh) 2.x (provides Postgres, Redis, Mailpit, Python, Ruby — no Docker required for dev)
- invoke

## Development Setup

```bash
# 1. Copy the development environment file
cp .env.dev .env

# 2. Enter the devenv development shell (installs Python deps automatically)
devenv shell

# 3. Start all services and processes (postgres, redis, mailpit, django, apiworker, celery)
devenv up

# In another shell (also inside `devenv shell`):

# 4. Run database migrations
invoke migrate

# 5. Create a superuser account
invoke createsuperuser
```

The site will be available at <http://localhost:8000>

### What `devenv up` runs

Services:

- **PostgreSQL 15** on `localhost:5432` (db `heltour`, user `heltour`, password `heltour_dev_password`)
- **Redis** on `localhost:6379`
- **Mailpit** — SMTP on `1025`, web UI at <http://localhost:8025>

Processes:

- **django** — `invoke runserver` (port 8000)
- **apiworker** — `invoke runapiworker` (port 8880)
- **celery** — `invoke celery`
- **watch-games** — `invoke watch-games`

Stop everything with `Ctrl-C` in the `devenv up` window. Service data persists under `.devenv/state/` between runs.

## Common Development Commands

```bash
# Process orchestration
devenv up             # Start postgres, redis, mailpit, django, apiworker, celery

# Django commands (inside `devenv shell`)
invoke migrate        # Run database migrations
invoke makemigrations # Create new migrations
invoke shell          # Django shell
invoke test           # Run tests
invoke collectstatic  # Collect static files
invoke compilescss    # Compile SCSS files
invoke seed-minimal   # Fill the database with some simulated values

# Dependencies
invoke update         # Update all dependencies via Poetry
```

## Configuration

All configuration is done through environment variables. The `.env.dev` file contains defaults for local development.

Key settings:

- Database: PostgreSQL on localhost:5432
- Redis: localhost:6379
- Email: Mailpit on localhost:1025 (SMTP) / 8025 (Web UI)
- Static files: SCSS compilation via Ruby sass gem (auto-installed in devenv shell)

## Development Tips

- The devenv shell automatically installs all required tools including Python 3.11, Poetry, Ruby, and sass
- Virtual environment is created automatically when entering the devenv shell (via `languages.python.poetry`)
- Ensure that your editor has an [EditorConfig plugin](https://editorconfig.org/#download) enabled
- JaVaFo pairing tool is included in `thirdparty/javafo.jar`

## Stopping Services

`Ctrl-C` in the `devenv up` window stops everything. Service state (Postgres data, Redis AOF, Mailpit storage) lives in `.devenv/state/` and persists between runs. Delete that directory to start from scratch.

## Historical Note

This project was previously known as heltour and served lichess4545. It has been rebranded to support lots.lichess.ca (Lichess Online Tournament System).

.
