# 0001 - Clean-cut env-driven settings

## Status

Accepted

## Context

heltour previously dispatched settings across `settings_default.py`, `settings_staging.py`,
`settings_travis.py`, `settings_testing.py`, machine-named files under `heltour/local/`
(`platform.node()`-keyed), a prod-JSON-override block reading `/etc/heltour/*.json`, and
extra entrypoints (`staging_wsgi.py`, `live_api_wsgi.py`, `staging_api_wsgi.py`,
`manage_staging.py`). Which file loaded depended on hostname or `HELTOUR_ENV`, making the
active configuration hard to predict outside its original deploy box and impossible to run
under Docker/Compose secrets. litour had already solved this with a single django-environ
module; heltour's own app config (installed apps, middleware, feature settings) needed to be
re-derived rather than copied, since litour lacks several apps/behaviors heltour ships
(`ckeditor_uploader`, `heltour.tournament.middlewares.RejectNullMiddleware`).

## Decision

Replace all dispatch layers with a single `heltour/settings.py` built on
`environ.FileAwareEnv` (`heltour/settings.py:16`), which reads `.env` at
`environ.FileAwareEnv.read_env(...)` (`heltour/settings.py:48`), resolves `DATABASE_URL` via
`env.db()`, `REDIS_URL`, and grants every `env(...)` call an implicit `<VAR>_FILE` override
for Docker/Compose secrets (`heltour/settings.py:12-15`) — layered on top of heltour's own
pre-existing `*_FILE_PATH` convention for Slack/Google/Lichess/FCM secrets, which application
code (`slackapi.py`, `spreadsheet.py`) opens directly and is left untouched. `HELTOUR_APP`
switches between the `tournament` (web) and `api_worker` processes; `HELTOUR_VERSION` feeds
`heltour/storage.py`'s `VersionedStaticFilesStorage` for static-asset cache busting.
`heltour/test_settings.py` layers over `settings.py` (`from .settings import *`) with a fixed
test `SECRET_KEY` and `MD5PasswordHasher` for speed. Deleted the four dispatch files, the
entire `heltour/local/` directory (verified not a Django app — no `models.py`/`apps.py`,
never in `INSTALLED_APPS`), the extra wsgi/manage entrypoints, and the `/etc/heltour` JSON
override path. `INSTALLED_APPS`/`MIDDLEWARE`/`TEMPLATES`/feature settings were re-derived
from heltour's old `settings_default.py`, not copied from litour's list.

## Consequences

- One file to read to know the running configuration; `manage.py`/`wsgi.py` now just read
  `HELTOUR_APP`/`HELTOUR_ENV` from the process environment (`heltour/wsgi.py`).
- Configuration is Docker/Compose-secrets-native (`*_FILE` pattern) without extra plumbing.
- Deploying to a new host requires no new settings file or hostname registration — only env
  vars, documented exhaustively in `.env.example`.
- Forecloses the old per-host settings file as an escape hatch: a host-specific override now
  requires either an env var or a code change to `settings.py`, not a new dispatch file.
- See ADR 0008 for the related decision to make `SECRET_KEY`/`DATABASE_URL` fail fast rather
  than fall back to insecure defaults within this same module.
