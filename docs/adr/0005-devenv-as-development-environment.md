# 0005 - devenv as the development environment

## Status

Accepted

## Context

heltour's prior `devenv.nix` was minimal and undocumented as a real workflow; the fabric/
`start.sh` path (deleted per ADR 0004) was the actual dev bootstrap. litour already has a
mature devenv setup (`devenv.nix`, `devenv.yaml`, `tasks.py` as an invoke-based dev driver)
covering Python + Postgres + Redis + mail capture + native library paths + a pinned JRE for
JaVaFo — but it also carries frontend (bun/Next.js `ui`), a FastAPI `api/` app, an
`api-client`/`api-schema` bundling pipeline, and Ruby (for sass, superseded per ADR 0003),
none of which exist in heltour.

## Decision

Port litour's `devenv.nix`/`devenv.yaml`/`tasks.py` pruned to heltour's actual surface: Python
3.11 + poetry auto-setup, `postgresql_18`, `redis`, `mailpit`, `dotenv.enable`, the
`nativeLibs`/`LD_LIBRARY_PATH`/`LIBRARY_PATH` block (needed by heltour's own
`psycopg2-binary`/`pillow` pins), the JaVaFo JRE pin (`env.JAVAFO_COMMAND` resolved through
`pkgs.jre21_minimal`), and three `processes`: `django`, `apiworker`, `celery`. Dropped:
`bun`/`nodejs_20`, `languages.ruby` and its `gem install sass` block, `caddy`/`watchexec`
(only used by the dropped frontend processes), and the `runapi`/`ui`/`api-client-iife-watch`/
`api-schema-watch`/`watch-games` processes (no FastAPI app, no Next.js UI, no `watch_games`
management command in heltour). `tasks.py` keeps `runserver`/`runapiworker`/`celery`/
`migrate`/`makemigrations`/`test`/`collectstatic`/`compilescss`/`createsuperuser`/
`docker_bake`/`reset_db`/`restore_db`; drops `tokentest`/`whoami` (call
`lichessapi.test_oauth_token`/`test_whoami`, which don't exist in heltour),
`runapi`/`openapi`/`fuzz`/`build_api_client`/`run_ui` (FastAPI/Next.js), `watch_games`, the
`seed*` tasks (depend on management commands heltour doesn't have), and `preflight`
(FastAPI/bun/Next.js CI steps).

Postgres initialization deviates from litour: litour uses
`initialDatabases = [{ name = "heltour"; }]` plus a `GRANT ALL PRIVILEGES ON DATABASE ... TO`
a non-owner role — on Postgres 15+ that no longer grants `CREATE` on the `public` schema
(ownership moved to `pg_database_owner`), so `manage.py migrate` fails with
`permission denied for schema public`. heltour's `devenv.nix` instead uses a
`CREATE USER ... SUPERUSER; CREATE DATABASE ... OWNER ...` pattern, verified end-to-end
(migrations + full 129-test suite green against `postgresql_18`).

## Consequences

- `devenv up` alone brings up every service the Django test suite and both worker processes
  need (Postgres, Redis, mailpit) — no external services to hand-provision.
- Dev DB creds (`heltour_lichess4545`/`heltour_dev_password`) are pinned in `devenv.nix` and
  must stay in lockstep with `.env.example`'s `DATABASE_URL` (ADR 0001); a mismatch breaks
  `devenv up` silently rather than at a well-defined seam.
- The `SUPERUSER`/`OWNER` Postgres pattern is broader-privileged than litour's `GRANT`
  approach — acceptable for a local dev database, not something to port as-is to a
  production Postgres instance.
- `thirdparty/javafo.jar` is not sourced by devenv itself (see ADR 0013) — `JAVAFO_COMMAND`
  resolves through a pinned JRE regardless of whether the jar is present.
- Frontend/FastAPI/Ruby developer workflows litour supports (bun, Next.js hot reload, FastAPI
  autoreload, `seed_database`) have no heltour equivalent and were not ported — adding any of
  those features later requires reintroducing the relevant devenv pieces, not just app code.
