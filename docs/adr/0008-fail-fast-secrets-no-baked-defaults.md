# 0008 - Fail-fast SECRET_KEY, no persisted secrets/config in images

## Status

Accepted

## Context

litour's `settings.py` declares `SECRET_KEY=(str, "this-is-only-for-testing")` as a fallback
default — a deployment that forgets to set `SECRET_KEY`/`SECRET_KEY_FILE` boots silently with
a known, checked-into-history value instead of failing. Separately, litour's
`Dockerfile.base` pattern persists its build-time dummy config (`DEBUG`, `SECRET_KEY`,
`DATABASE_URL`, `REDIS_URL`) via `ENV`, which — because `ENV` persists into every downstream
build stage — shipped as baked-in runtime defaults in the resulting `web`/`apiworker`/
`celery`/`migrate` images. A production deploy that omitted an override would silently run
with `DEBUG=True` and a publicly-known `SECRET_KEY`. Both were caught during Task 1/3's build
verification, not designed in from the start.

## Decision

`heltour/settings.py`'s `SECRET_KEY = env("SECRET_KEY")` (`heltour/settings.py:50`) has no
default in the `FileAwareEnv(...)` schema — an unset `SECRET_KEY`/`SECRET_KEY_FILE` raises
`django.core.exceptions.ImproperlyConfigured` at import time. `DATABASE_URL` is equally
fail-fast via `env.db()` (no default). `docker/Dockerfile.base` passes its build-time-only
`SECRET_KEY`/`DATABASE_URL` dummies as an inline shell-variable prefix directly on the
`compilescss`/`collectstatic` `RUN` invocations (`docker/Dockerfile.base`), never via `ENV`,
so they never enter the image's persistent `Config.Env`. `DEBUG` and `REDIS_URL` were dropped
from the build step entirely rather than pinned — both have real, safe defaults in
`settings.py`'s schema (`DEBUG=(bool, False)`, `REDIS_URL=(str, "redis://localhost:6379/1")`),
so the build runs correctly without setting them, and the `DEBUG=False` default is strictly
better for the build (it produces compressed SCSS output rather than debug/sourcemap output,
`heltour/settings.py:186`). `STATIC_ROOT=/app/static` remains a persistent `ENV` — it is real
runtime config the `web` container also needs at boot, not a build-time dummy.

## Consequences

- A container started with no production env override fails immediately at Django setup
  (`ImproperlyConfigured: Set the SECRET_KEY environment variable`), rather than serving
  traffic on a known secret.
- `docker inspect <image> --format '{{json .Config.Env}}'` on any of the four runtime images
  contains no `SECRET_KEY`/`DATABASE_URL`/`DEBUG`/`REDIS_URL` — verified directly, not just
  asserted.
- Every Django-importing service in `deploy/prod/compose.yml` (`web`, `apiworker`, `celery`,
  `migrate`) must wire `SECRET_KEY_FILE` explicitly (ADR 0007) — litour's reference stack
  omits this for `celery`/`migrate` and would crash those containers on boot under heltour's
  stricter settings.
- `docker/Dockerfile.web-verify` (test-only, never deployed) intentionally keeps its own
  explicit `SECRET_KEY=test-secret-key-only-for-testing`/`DEBUG=True` — a deliberate, narrowly
  scoped exception, not a regression of this decision.
