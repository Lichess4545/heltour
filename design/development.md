# Development

## Getting started

```bash
# Create your local .env file from the development template
cp .env.dev .env

# Enter the development environment (sets up virtualenv, installs deps)
devenv shell

# Start all services (postgres, redis, mailpit, django, apiworker, celery)
devenv up

# In another shell, also inside `devenv shell`:
invoke migrate
invoke createsuperuser
```

`devenv shell` automatically:

- Sets up the Python 3.11 virtualenv and installs Poetry deps
- Installs Ruby + the sass gem for SCSS
- Configures paths and environment variables

## Common invoke commands

```bash
# Database
invoke createdb
invoke migrate
invoke makemigrations

# Individual processes (when not using `devenv up`)
invoke runserver        # Django on 0.0.0.0:8000
invoke runapiworker     # API worker on port 8880
invoke celery           # Celery worker

# Dependencies
invoke update           # bump all to latest (alias: up)
poetry add <package>    # add new dep

# Tests
invoke test
invoke test -t heltour.tournament.tests.test_models  # specific module

# Static
invoke compilestatic
invoke collectstatic

# Misc
invoke shell            # Django shell
invoke createsuperuser
invoke status           # git status (alias: st)
```

## Environment configuration

All configuration goes through environment variables (django-environ).
Files:

- `.env.dev` — development defaults (PostgreSQL, Redis, Mailpit
  pre-configured)
- `.env.example` — template with every available setting

API keys are read directly from environment variables; settings are
read with sensible defaults so missing values fail loudly.

## External services

- **Lichess API** — OAuth + game data
- **Slack** — notifications
- **Google Sheets** — data export
- **Firebase Cloud Messaging** — push notifications

## Other tools

- **JaVaFo** at `thirdparty/javafo.jar` — sophisticated swiss pairings.
- **Invoke** drives the task automation; see `tasks.py` for the full
  list.
