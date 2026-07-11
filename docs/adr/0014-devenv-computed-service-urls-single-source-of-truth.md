# 0014 - devenv-computed DATABASE_URL/REDIS_URL as the single source of truth

## Status

Accepted

## Context

`devenv.nix`'s `services.postgres`/`services.redis`/`services.mailpit` each pick a base port
(5432/6379/mailpit's 8025+1025) but fall back to the next free port when the base is already
bound — e.g. by another project's devenv, or a leftover heltour instance. `dotenv.enable = true`
loaded a separate, independently hardcoded `DATABASE_URL`/`REDIS_URL`/`BROKER_URL`/`EMAIL_HOST`/
`EMAIL_PORT` from `.env` (`postgresql://...@localhost:5432/...`, `redis://localhost:6379/1`,
etc.), consumed by `heltour/settings.py` via `django-environ`. When postgres/redis/mailpit
shifted off their base port, the `django`/`apiworker`/`celery` `processes` still launched with
the stale `.env` values and failed with "connection refused" — exactly the risk ADR 0005 flagged
("Dev DB creds ... must stay in lockstep with `.env.example`'s `DATABASE_URL`; a mismatch breaks
`devenv up` silently rather than at a well-defined seam"), now generalized from creds to ports.

Verified against devenv 2.1.2's actual module source (`services/postgres.nix`,
`services/redis.nix`, `services/mailpit.nix`, `processes.nix`, `integrations/dotenv.nix`):

- `services.postgres`/`redis`/`mailpit` each declare `processes.<name>.ports.<port>.allocate =
  <base>`; devenv's native process manager probes from `<base>` upward for a free port and
  exposes the result as `config.processes.<name>.ports.<port>.value`. `services.postgres` also
  re-exports its resolved port as `config.env.PGPORT` for its own init scripts.
- `dotenv.enable`'s parsed `.env` values are injected into `config.env` via `lib.mkDefault` —
  the lowest priority. Any plain `env.<VAR> = ...;` set elsewhere in `devenv.nix` wins over
  whatever `.env` contains, without needing `.env` to agree or even define the key.
- `processes.<name>.after = [ "devenv:processes:postgres" ]` (default `@ready` suffix) is the
  native-manager readiness-dependency mechanism — the process-compose-only `depends_on` doesn't
  apply here since this project uses the native manager (the devenv 2.1.2 default).

Live-tested on this machine (`devenv up`, `devenv shell`, actual `ss`/`/proc/<pid>/environ`
inspection): with another project's devenv already holding redis's default port, heltour's own
redis correctly shifted to 6380 and `celery`'s "Connected to redis://127.0.0.1:6380/1" plus
`apiworker`'s live env confirmed the shift propagated. Artificially occupying 5432 with a
throwaway listener before `devenv up` reproduced the exact reported failure mode; postgres
shifted to 5433, and `apiworker`/`celery`'s actual runtime env (read from `/proc/<pid>/environ`,
not re-derived) carried `DATABASE_URL=...@127.0.0.1:5433/...`, confirmed connectable via a
direct `psql` call using that exact string.

## Decision

`devenv.nix` now holds the postgres user/password/database name and constructs
`DATABASE_URL`/`REDIS_URL`/`BROKER_URL`/`EMAIL_HOST`/`EMAIL_PORT` in a single `let` block, reading
`config.env.PGPORT` and `config.processes.{redis,mailpit}.ports.*.value` — the same values the
service modules themselves resolved to — rather than restating a port. These are then set as
plain `env.DATABASE_URL`/etc., which beats `.env`'s `mkDefault`-priority values automatically.
`services.postgres.initialScript`'s `CREATE USER`/`CREATE DATABASE` now interpolate the same
`let`-bound user/password/database, so credentials have one textual source too, not two that can
drift. `.env`/`.env.example` drop the dev-path `DATABASE_URL`/`REDIS_URL`/`BROKER_URL`/
`EMAIL_HOST`/`EMAIL_PORT` lines entirely (kept as documented placeholders in `.env.example` for
the non-devenv/container path), so there's no stale value to misread even though it would already
lose to devenv's. `django`/`apiworker`/`celery` gained `after = [ "devenv:processes:postgres"
"devenv:processes:redis" ]`. `enterShell`'s banner prints the resolved values instead of literals.

### Amendment: HTTP ports (django runserver, apiworker) allocated the same way

The same conflict hit the HTTP ports: `django`'s runserver (base 8000) and the `apiworker`
(base 8880) were fixed in `tasks.py`, so `devenv up` alongside another project already on 8000
put `django` into a "port already in use" restart loop. Both process ports now use the identical
allocator: `processes.django.ports.http.allocate = 8000` / `processes.apiworker.ports.http.allocate
= 8880`, with the resolved `config.processes.<name>.ports.http.value` fed into the process command
(`invoke runserver --port <value>` / `invoke runapiworker --port <value>` — `tasks.py`'s
`runserver`/`runapiworker` gained a `port` argument defaulting to the old fixed value, so behaviour
outside devenv is unchanged). The two settings that carry an HTTP port are derived from the same
resolved values in the `let` block and set as plain `env.*`: `API_WORKER_HOST` (from the apiworker
port, so `django`/`celery` still reach the apiworker after it shifts — `lichessapi.py` builds every
apiworker URL from `settings.API_WORKER_HOST`) and `CSRF_TRUSTED_ORIGINS` (from the django port, so
the browser origin still validates on a shifted port). `heltour/tournament/tests/test_lichessapi.py`
previously asserted literal `http://localhost:8880/...` URLs; those assertions now build the
expected URL from `settings.API_WORKER_HOST`, so the test follows the same single source instead of
breaking when the port shifts. `.env`/`.env.example` drop the dev-path `API_WORKER_HOST` /
`CSRF_TRUSTED_ORIGINS` lines (kept as documented placeholders in `.env.example` for the
non-devenv/container path), same treatment as the DB/broker URLs above.

## Consequences

- Running heltour's devenv alongside another project's no longer breaks the app processes: the
  actually-bound postgres/redis/mailpit *and* django/apiworker ports reach the dependent processes
  and settings for any single `devenv up` invocation, live-verified under naturally-occurring
  conflicts (redis) and artificially forced ones (postgres and django's 8000, each matching a
  reported failure mode).
- Known gap, not fixed by this change and not fixable from `devenv.nix` alone: a *separate*
  `devenv shell` invocation evaluates `config.processes.<name>.ports.<port>.value` independently
  of an already-running `devenv up` and is not guaranteed to reflect the port that run's services
  actually bound to if one had to shift (observed directly on devenv 2.1.2 — a fresh `devenv
  shell` returned redis's unshifted base port while a concurrently-running `devenv up`'s redis was
  genuinely on the shifted one). One-off commands (`invoke migrate`/`invoke test`/`manage.py
  shell`) run this way inherit whatever that fresh invocation resolved, which can disagree with
  the live services. `docs/testing-the-infrastructure.md` now calls this out with a
  read-the-actual-port-first workaround; fixing it for real is upstream devenv's problem (or would
  require heltour's own port-discovery glue, out of scope here).
- Dev Postgres/Redis credentials and the database name exist as literal strings in exactly one
  place (`devenv.nix`'s `let` block) instead of two (`devenv.nix` init script + `.env`).
- `.env.example` no longer doubles as accurate dev-port documentation for `DATABASE_URL`/
  `REDIS_URL`/`BROKER_URL`/`EMAIL_HOST`/`EMAIL_PORT` — its placeholder values there now document
  the URL *shape* for the non-devenv (container/prod) path only; a reader relying on it for the
  actual local dev port needs `devenv shell`'s banner or `printenv`, not this file.
