# Testing the infrastructure

Step-by-step verification of the dev environment, test suite, settings cutover, Docker images, Caddy/media wiring, per-service smoke tests, CI, deploy stack, and a local container test harness. Run sections in order — later sections assume the dev environment from section 1 is up. Rationale for each design decision lives in `docs/adr/`; this runbook only covers verification steps.

## 1. Dev environment

1. Copy the env template:
   ```
   cp .env.example .env
   ```
   `.env` is read from `BASE_DIR/.env` by `heltour/settings.py` (`environ.FileAwareEnv.read_env`) on every process start. It is never committed (`.gitignore`) and never baked into a Docker image (`.dockerignore`). `DATABASE_URL`/`REDIS_URL`/`BROKER_URL`/`EMAIL_HOST`/`EMAIL_PORT` are deliberately absent from `.env.example` for local dev — `devenv.nix` builds and exports them itself (see `docs/adr/`), from whatever port postgres/redis/mailpit actually bound, not a fixed guess. They only need to be set in `.env` when running outside devenv entirely.

2. No `.envrc`/direnv is set up in this repo — there's nothing to `direnv allow`. Enter the environment explicitly with `devenv shell` or bring services up directly with the command below.

3. Bring up services and dev processes:
   ```
   devenv up -d
   ```
   Expect these to reach `ready`: `postgres` (Postgres 18), `redis`, `mailpit`, `django` (`invoke runserver`), `apiworker` (`invoke runapiworker`), `celery` (`invoke celery`). Check status:
   ```
   devenv processes list
   ```
   All five networked ports — `postgres`/`redis`/`mailpit` and now `django`/`apiworker` too — are devenv-allocated: each has a base (5432/6379/8025+1025/8000/8880) and shifts to the next free port when its base is already taken (e.g. by another project's devenv). The dependent config follows the shift: `DATABASE_URL`/`REDIS_URL`/`BROKER_URL` for the DB/broker, `API_WORKER_HOST` for the apiworker (so django/celery still reach it), and `CSRF_TRUSTED_ORIGINS` for django (so the browser origin still validates). `devenv shell`'s banner prints whatever each actually bound to for this invocation. A `django` "port already in use" restart loop now only happens if 8000 *and* every port devenv probed above it are taken — rare.

4. Confirm each service is actually healthy, not just "ready". Get the ports this invocation actually resolved first:
   ```
   devenv shell -- printenv DATABASE_URL REDIS_URL API_WORKER_HOST
   ```
   (or read the `devenv shell` banner, which prints the django URL too). Then, substituting the host/port from that output:
   - Postgres:
     ```
     PGPASSWORD=heltour_dev_password psql -h <host> -p <port> -U heltour_lichess4545 -d heltour_lichess4545 -c "select version();"
     ```
     Expect a `PostgreSQL 18.x` row back.
   - Redis:
     ```
     poetry run python -c "import redis; print(redis.from_url('<REDIS_URL from above>').ping())"
     ```
     Expect `True`.
   - Mailpit: open the UI URL from the `devenv shell` banner (`http://<host>:<port>`, default `8025`) — the Mailpit web UI should load.
   - Django: `curl -sI http://localhost:<django port from banner>/admin/login/` — expect `HTTP/1.1 200 OK` (default port 8000).
   - apiworker: `curl -sI <API_WORKER_HOST from above>/` — expect a response (not connection-refused; default `http://localhost:8880`).
   - Celery: check its process log for `celery@<host> ready.` and a `Connected to redis://...` line matching the `REDIS_URL` above.

   Known caveat: the port substitution above matters because a *separate* `devenv shell` invocation evaluates independently of an already-running `devenv up` — if any service had to shift ports for the running `devenv up`, a fresh `devenv shell` call started afterwards is not guaranteed to resolve the same values (observed on devenv 2.1.2). Read the actual port from a command run against the same `devenv up` session (its process logs, or `devenv processes list` plus `ss -ltnp`) if in doubt, rather than trusting a brand new shell invocation.

5. Tear down when done:
   ```
   devenv processes down
   ```

## 2. Django test suite

1. Run the full suite:
   ```
   poetry run python manage.py test --settings=heltour.test_settings
   ```
   Expect `Ran 129 tests` and `OK`. Takes roughly 55s. Requires Postgres and Redis up (section 1).

2. System check:
   ```
   poetry run python manage.py check
   ```
   Expect `System check identified no issues (0 silenced).`

3. Migration drift check:
   ```
   poetry run python manage.py makemigrations --check --dry-run
   ```
   Expect `No changes detected`. A non-empty exit here means a model changed without a migration.

4. Same suite via the invoke wrapper, to confirm `tasks.py` itself is wired correctly:
   ```
   poetry run invoke test
   ```
   Expect the same `129 tests ... OK`.

## 3. Settings-cutover checks

Full rationale: `docs/adr/0001-env-driven-settings-cutover.md`, `docs/adr/0008-fail-fast-secrets-no-baked-defaults.md`.

1. **SECRET_KEY fail-fast.** With `.env` present, move it aside and clear the environment, then try to load settings:
   ```
   mv .env .env.bak
   env -i PATH=$PATH HOME=$HOME DJANGO_SETTINGS_MODULE=heltour.settings poetry run python -c "import django; django.setup()"
   ```
   Expect `django.core.exceptions.ImproperlyConfigured: Set the SECRET_KEY environment variable`. Restore afterward:
   ```
   mv .env.bak .env
   ```
   `DATABASE_URL` fails the same way (`env.db()` has no default) — same test, same failure mode.

2. **`.env` handling.** `heltour/settings.py` always reads `os.path.join(BASE_DIR, ".env")` (line 48) regardless of how the process was started. Confirm it's excluded from both git and image builds:
   ```
   grep -n '/\.env$' .gitignore
   grep -n '^\.env' .dockerignore
   ```
   Expect `/.env` in `.gitignore` and `.env` / `.env.*` (with a `!.env.example` negation) in `.dockerignore`.

3. **`*_FILE` / `*_FILE_PATH` secrets pattern.** Two distinct mechanisms coexist:
   - django-environ's own `FileAwareEnv` auto-reads any `<VAR>_FILE` (e.g. `SECRET_KEY_FILE`) and substitutes its contents for `<VAR>` transparently.
   - heltour's own convention, `*_FILE_PATH` (`SLACK_API_TOKEN_FILE_PATH`, `LICHESS_API_TOKEN_FILE_PATH`, `GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH`, `FCM_API_KEY_FILE_PATH`), where the app code (`slackapi.py`, `spreadsheet.py`, `api_worker/views.py`) opens the file at that path directly — this is a path setting, not a django-environ auto-substitution.
   Don't confuse the two when reading `deploy/prod/compose.yml` — `SECRET_KEY_FILE` and `DATABASE_URL_FILE` are the first kind; `LICHESS_API_TOKEN_FILE_PATH` is the second.

4. **HELTOUR_APP switch.** Confirm both values boot without error:
   ```
   HELTOUR_APP=tournament DJANGO_SETTINGS_MODULE=heltour.settings poetry run python -c "import django; django.setup(); print('ok')"
   HELTOUR_APP=api_worker DJANGO_SETTINGS_MODULE=heltour.settings poetry run python -c "import django; django.setup(); print('ok')"
   ```
   Both print `ok`. In `deploy/prod/compose.yml` this is set per-service: `web`/`celery`/`migrate` use the default (`tournament`), `apiworker`'s image bakes `HELTOUR_APP=api_worker` via `Dockerfile.apiworker`'s own `ENV`.

## 4. Docker images

1. Build everything:
   ```
   docker buildx bake -f docker/docker-bake.hcl default
   ```
   The `default` group builds, in dependency order: `base` → `verify` (`web-verify` runs the full 129-test Django suite inside the image, `javafo-verify` runs the vendored `thirdparty/javafo.jar` and checks its banner) → `heltour-caddy`, `heltour-web`, `heltour-api-worker`, `heltour-celery`, `heltour-migrate`. A clean build (no cache) takes roughly a few minutes, dominated by apt/poetry install in `base`; `web-verify` alone adds ~55s for the test run. Expect all targets to report success; `web-verify`'s log should show `Ran 129 tests ... OK`.

2. Run each verify target individually if you want isolated signal:
   ```
   docker buildx bake -f docker/docker-bake.hcl web-verify
   docker buildx bake -f docker/docker-bake.hcl javafo-verify
   ```
   `web-verify` is `cache-only` — it never produces a runnable image, only a pass/fail build. Same for `javafo-verify` (expected output: `JaVaFo (rrweb.org/javafo) - Rel. 2.2 (Build 3223)`).

3. Confirm no baked env leaks into the runtime images:
   ```
   docker inspect heltour-web:latest --format '{{json .Config.Env}}'
   docker inspect heltour-api-worker:latest --format '{{json .Config.Env}}'
   docker inspect heltour-celery:latest --format '{{json .Config.Env}}'
   docker inspect heltour-migrate:latest --format '{{json .Config.Env}}'
   ```
   None should contain `SECRET_KEY`, `DATABASE_URL`, `DEBUG`, or `REDIS_URL` — only things like `STATIC_ROOT`, `DJANGO_SETTINGS_MODULE`/`HELTOUR_APP`/`HELTOUR_VERSION`/`PYTHONUNBUFFERED`, and base-image/poetry vars.

4. Confirm fail-fast without env:
   ```
   docker run --rm heltour-web:latest python -c "import django; django.setup()"
   ```
   Expect exit code 1 and `ImproperlyConfigured: Set the SECRET_KEY environment variable`.

5. Confirm it boots with real env:
   ```
   docker run --rm -e SECRET_KEY=x -e DATABASE_URL=postgresql://u:p@localhost:5432/d heltour-web:latest python -c "import django; django.setup(); print(django.conf.settings.DEBUG)"
   ```
   Expect it to succeed and print `False` (the real production default — `DEBUG` is not baked in and defaults safe).

6. Confirm no `.env` or the legacy `env/` virtualenv reached the image:
   ```
   docker run --rm heltour-base:latest sh -c "test -f /app/.env && echo LEAK || echo clean; test -d /app/env && echo LEAK || echo clean"
   ```
   Expect `clean` twice.

## 5. Caddy, static, and media

Volume contract detail: `docs/adr/0002-media-named-volume-shared-web-caddy.md`, `docs/adr/0011-baked-caddyfile-single-source-of-truth.md`.

1. Validate the baked Caddyfile:
   ```
   docker run --rm heltour-caddy:latest caddy validate --config /etc/caddy/Caddyfile
   ```
   Expect `Valid configuration`.

2. Live-test the routing (the pattern used to verify this originally): run the image standalone, with no `web` backend and no media volume mounted, and probe all three route shapes:
   ```
   docker run -d -p 18080:80 --name caddy-test heltour-caddy:latest
   curl -sI http://localhost:18080/static/admin/css/base.css   # expect 200 — baked in from collectstatic at image build
   curl -sI http://localhost:18080/media/anything.jpg           # expect 404 — route works, file just doesn't exist (no volume mounted)
   curl -sI http://localhost:18080/anything-else                # expect 502 — reverse_proxy to "web" host that doesn't exist standalone
   docker rm -f caddy-test
   ```
   404 on `/media/*` (not an error) and 502 on the catch-all (not a crash) are both the correct standalone result — they resolve to real content/backends once running inside the compose network in section 8.

3. The D2 media contract: `MEDIA_ROOT` resolves to `/app/media` inside `web` (and any other media-writing container); `docker/Caddyfile` serves `/media/*` from `/public/media`. Both paths must be the same named volume (`media_data` in `deploy/prod/compose.yml`) mounted at the two different paths in the two different containers — `web` writes, `caddy` reads. `media_data` is a default local-driver volume with no node affinity, so `deploy/prod/compose.yml` pins both `web` and `caddy` to the same Swarm node via `deploy.placement.constraints: [node.labels.heltour.media == true]`. That label must be set once, out of band, before a real deploy:
   ```
   docker node update --label-add heltour.media=true <node>
   ```
   Skipping this on a multi-node Swarm risks `web` and `caddy` landing on different nodes with two independent empty volumes — uploads silently never appear.

## 6. Per-service smoke tests

1. **web** — gunicorn boots and the admin is reachable:
   ```
   docker run -d --name web-test -e SECRET_KEY=x -e DATABASE_URL=postgresql://u:p@localhost:5432/d -p 18000:8000 heltour-web:latest
   curl -sI http://localhost:18000/admin/login/
   docker logs web-test
   docker rm -f web-test
   ```
   Expect gunicorn worker boot lines in the log and `200 OK` from curl (DB unreachable is fine for a login-page GET — it doesn't query the DB before rendering the form; a full smoke test needs a real DB, see section 1 step 4 for the devenv-based version instead).

2. **apiworker** — confirm `HELTOUR_APP=api_worker` is baked, not left at the default:
   ```
   docker run --rm heltour-api-worker:latest sh -c 'echo $HELTOUR_APP'
   ```
   Expect `api_worker`.

3. **celery** — worker with embedded beat starts, and the beat schedule loads from the DB (`django_celery_beat`, per `docs/adr/0006-image-naming-celery-beat-db-scheduler.md`):
   ```
   docker run --rm heltour-celery:latest celery --help
   ```
   confirms the `celery` binary and the image's Python environment are well-formed (the image has no `ENTRYPOINT`, so `--help` alone would be passed as a bogus CMD override — the `celery` prefix is required). For a live check against devenv's Postgres/Redis, use `devenv up -d` (section 1) and watch the `celery` process log for `celery@<host> ready.` plus a beat-scheduler startup line referencing `DatabaseScheduler`.

4. **migrate** — the `pg_isready` gate and `migrate` run:
   ```
   docker run --rm -e DATABASE_URL=postgresql://heltour_lichess4545:heltour_dev_password@host.docker.internal:5432/heltour_lichess4545 -e SECRET_KEY=x heltour-migrate:latest
   ```
   (requires devenv's Postgres up and reachable from the container — adjust the host for your Docker network). Expect it to wait for `pg_isready`, then apply migrations, then exit 0. Re-running should report no pending migrations.

## 7. CI sanity

`.github/workflows/test.yml`, `docker-build.yml`, `deploy.yml`.

1. Parse all three plus the deploy compose file:
   ```
   python3 -c "
   import yaml
   for f in ['.github/workflows/docker-build.yml','.github/workflows/test.yml','.github/workflows/deploy.yml','deploy/prod/compose.yml']:
       yaml.safe_load(open(f)); print(f, 'OK')
   "
   ```
   Expect `OK` on all four.

2. Lint with actionlint (not preinstalled; fetch via nix if needed):
   ```
   nix run nixpkgs#actionlint -- .github/workflows/test.yml .github/workflows/docker-build.yml .github/workflows/deploy.yml
   ```
   `test.yml` should come back clean. `docker-build.yml`/`deploy.yml` report a handful of `SC2086` (unquoted `$GITHUB_OUTPUT`/`$GITHUB_ENV`) and one `SC2129` — style/info severity, pre-existing in the upstream source these were ported from, not a regression.

3. What each workflow does, on PR vs. master:
   - `test.yml` — runs the full Django suite against live `postgres:18-alpine` + `redis:7-alpine` service containers, on every push to `master` and every PR. No push/tag gating; it's pure verification.
   - `docker-build.yml` — runs `docker buildx bake ... default` (build + verify) on every push, PR, and manual dispatch. Only *pushes* images to `ghcr.io` when the event is `workflow_dispatch` or a push to `master` — PRs build and verify but never push.
   - `deploy.yml` — triggered by `workflow_call` or `workflow_dispatch`, gated by `if: github.ref == 'refs/heads/master'`. Not wired to run automatically after `docker-build.yml` — nothing in this repo currently chains them.

4. What can't be verified without pushing/triggering: actual GitHub Actions execution (no runner available locally — static YAML parse + actionlint is the achievable bar), whether `docker-build.yml` actually pushes to `ghcr.io` (needs real `GITHUB_TOKEN`/registry access), and `deploy.yml`'s webhook calls (needs the `HELTOUR_DEPLOY_PRODUCTION_*` repo secrets, which are ops-managed and don't exist by default).

## 8. Deploy stack sanity (without deploying)

Full rationale: `docs/adr/0007-deploy-wiring-workflow-and-swarm-stack.md`.

1. Resolve the compose file with its env file:
   ```
   docker compose -f deploy/prod/compose.yml --env-file deploy/prod/stack.env config
   ```
   Expect clean resolution, no errors — this only statically resolves the file; it does not require a Swarm or contact any external secret/network. It will *not* fail even if the `external: true` secrets/networks below don't exist yet — that's only checked at real `docker stack deploy` time.

2. **Deploy-mechanism assumption.** Every service in `deploy/prod/compose.yml` uses `env_file: "stack.env"` to supply `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `REDIS_URL`/`BROKER_URL`, `EMAIL_HOST*`, and `HELTOUR_ENV`. Portainer resolves `env_file:` when it deploys a stack. Classic `docker stack deploy -c deploy/prod/compose.yml <stack>` — the raw Swarm CLI — has historically ignored `env_file:` (it's a Compose-file-spec field, not part of the Swarm-native stack format the CLI parses). If the tool driving a real deploy silently drops it, every service still boots, but with `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` empty (Django returns 400 on every request) and `HELTOUR_ENV` falling back to `settings.py`'s schema default of `"dev"` instead of `"prod"`. Before a real deploy, confirm whichever tool triggers it (Portainer, a CI runner, a manual op on the manager) actually resolves `env_file:` — or inline `stack.env`'s values directly into each service's `environment:` block as a fallback.

3. **Before first production deploy — prerequisites checklist.** None of these are checked by `config` (step 1):
   - Swarm secrets, created out-of-band on the manager (`docker secret create`): `heltour_prod_db_url`, `heltour_app_secret_key`, `heltour_prod_lichess_api_token`, `heltour_email_host_user`, `heltour_email_host_password`.
   - **Slack + Google Sheets secrets — hard prerequisites, not deferrable integrations.** `heltour/tournament/slackapi.py`'s `_get_slack_token()` opens `settings.SLACK_API_TOKEN_FILE_PATH` unconditionally (`with open(...)`, no fallback) — left unwired (the schema default is `""`), it raises `FileNotFoundError` the first time any Slack-backed code path runs (chesster commands, league Slack integration). `heltour/tournament/spreadsheet.py`'s `_open_doc()` has the same hard dependency on `GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH` for Sheets. heltour production uses both Slack/chesster and Sheets, unlike litour (whose fork doesn't) — so, despite the `TODO(ops)` comment at the bottom of `deploy/prod/compose.yml` flagging them as unwired, these must be wired (secret + matching `*_FILE_PATH` env var, following the `LICHESS_API_TOKEN_FILE_PATH` pattern) before a real cutover, not just before those features happen to be exercised.
   - The `caddy` network, external, front-facing (created outside this stack).
   - The `heltour.media` node label, set on exactly one Swarm node: `docker node update --label-add heltour.media=true <node>` (section 5.3) — `web` and `caddy` are pinned to it via `deploy.placement.constraints` and both need to land on the same node.
   - `HELTOUR_DEPLOY_PRODUCTION_<SERVICE>` GitHub repo secrets for all five services (`apiworker`, `caddy`, `celery`, `migrate`, `web`) — see item 4 below; a missing one fails that service's webhook step outright.
   - `EMAIL_HOST`/`EMAIL_PORT` in `stack.env`, verified against heltour's actual mail relay — currently an unverified placeholder carried from litour's stack.env (AWS SES `eu-west-3`), per `docs/adr/0007-deploy-wiring-workflow-and-swarm-stack.md`'s Consequences.
   - The `env_file` deploy-mechanism assumption above, confirmed against whichever tool actually triggers the deploy.
   - FCM secrets remain **not yet wired** in this stack (see the same `TODO(ops)` comment) — flagged there as a known gap, not an oversight in this runbook.

4. `deploy.yml`'s webhook contract: one `HELTOUR_DEPLOY_PRODUCTION_<SERVICE>` GitHub repo secret per service (`apiworker`, `caddy`, `celery`, `migrate`, `web`), each holding a URL to an out-of-band listener on the Swarm host. The workflow just does `curl --fail -X POST <url>` per matrix entry — it doesn't build, push, or inspect anything; it assumes the image was already pushed by `docker-build.yml` and the listener itself pulls and redeploys. None of these secrets exist in this repo yet; that's an ops setup step, not something this runbook can verify locally.

## 9. Testing the containers locally

`deploy/prod/compose.yml` is Swarm-flavored — `deploy:` blocks, `external: true` secrets and networks, `ghcr.io` images — and isn't runnable standalone. `docker/compose.test.yml` is the local counterpart: plain `docker compose` (v2, not Swarm), the locally-built images (`heltour-web`/`heltour-celery`/`heltour-migrate`/`heltour-caddy` from `docker/docker-bake.hcl`), and `docker/compose.test.env` for its settings — a committed file of dummy, test-only values (fake `SECRET_KEY`, a throwaway Postgres password), never real secrets.

1. Bring up the stack (builds the images first, then waits for the site to answer):
   ```
   invoke docker-test-up
   ```
   This runs `docker buildx bake -f docker/docker-bake.hcl production` (the five runnable images, skipping the `web-verify`/`javafo-verify` cache-only targets — pass `--no-build` to skip the rebuild on a re-run), then `docker compose -f docker/compose.test.yml -p heltour-test up -d`, then polls `http://localhost:8090/` until it answers `200`/`302`. Site URL: **http://localhost:8090** — chosen to be clearly distinct from devenv's allocated Django port (default 8000, but it shifts) and from any other project's devenv. Postgres and Redis are *not* published to the host at all, so they never collide with a devenv session's own Postgres (default 5432, but it shifts)/Redis (default 6379) — the `migrate`, `web`, and `celery` containers reach them over the compose-internal network as `postgres`/`redis`.

2. Seed the same demo leagues used in devenv, via the identical management command running inside the `web` container:
   ```
   invoke docker-test-seed
   ```
   (`invoke docker-test-seed --flush` to recreate them.) This is literally `docker compose -f docker/compose.test.yml -p heltour-test exec web python manage.py seed_test_data` — the same `seed_test_data` command as `invoke seed` in devenv (section 1), just run inside the container instead of the host. Confirm it worked:
   ```
   curl -s http://localhost:8090/ | grep -o 'Test 4545 Team League\|Test LoneWolf League\|Test Chess960 League'
   ```
   Expect all three league names back. The standings/roster pages return `200` too, e.g. `http://localhost:8090/test-4545/season/test-season-1/standings/`.

3. Tear down (stops and removes the containers *and* the Postgres/media volumes — the next `docker-test-up` starts from an empty database):
   ```
   invoke docker-test-down
   ```

4. What this harness does and doesn't verify: it's the same runnable images `docker-build.yml` pushes to `ghcr.io` (section 4), wired together the way `deploy/prod/compose.yml` wires them (`web`↔`caddy` media volume, `migrate` gating `web`/`celery` via `service_completed_successfully`, Caddy's baked-in `reverse_proxy web:8000`) — so it catches image- and wiring-level breakage before a real deploy. It does *not* exercise the Swarm-specific parts (`deploy:` placement constraints, the `heltour.media` node label, external secrets/networks) — those still need section 8's static checks plus a real Swarm for full confidence.
