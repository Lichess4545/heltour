# Local testing and production deploy prerequisites

Rationale for these decisions lives in `docs/adr/`.

## 1. Local development (devenv)

`devenv up -d` brings up `postgres`, `redis`, `mailpit`, and the `django`/`apiworker`/`celery` processes on dynamically-allocated ports — each shifts to the next free port if its default is already taken by another project's devenv (`docs/adr/0014-devenv-computed-service-urls-single-source-of-truth.md`). `devenv processes down` tears it down.

**Tests:** `invoke test` runs `manage.py test --settings=heltour.test_settings`. `.github/workflows/test.yml` runs the same suite against live `postgres`/`redis` containers on every push to `master` and every PR.

**Demo data:** `invoke seed` runs `manage.py seed_test_data`, seeding three demo leagues (team, LoneWolf-style, Chess960-rated) for manual testing. `invoke seed --flush` recreates them.

**Known caveat:** a *separate* `devenv shell` invocation evaluates ports independently of an already-running `devenv up`, and isn't guaranteed to agree with it if a port had to shift (observed on devenv 2.1.2 — a fresh `devenv shell` returned a service's unshifted base port while the running `devenv up` had it on the shifted one). Read the port from the running session itself (its process logs, `devenv processes list`, or the `devenv up` banner) rather than trusting a fresh `devenv shell` call. Full detail: `docs/adr/0014-devenv-computed-service-urls-single-source-of-truth.md`.

## 2. Local docker test harness

`docker/compose.test.yml` is the plain `docker compose` (v2, non-Swarm) counterpart to `deploy/prod/compose.yml`: the same locally-built images (`heltour-web`/`heltour-celery`/`heltour-migrate`/`heltour-caddy` from `docker/docker-bake.hcl`), wired the same way (`migrate` gates `web`/`celery`, `web` and `caddy` share the media volume), using `docker/compose.test.env` for dummy, test-only settings — never real secrets.

- `invoke docker-test-up` builds the images (`docker buildx bake -f docker/docker-bake.hcl production`; pass `--no-build` to skip the rebuild on a re-run) and brings up the stack at **http://localhost:8090**. Postgres/redis aren't published to the host, so they never collide with a devenv session's own.
- `invoke docker-test-seed` (`--flush` to recreate) runs `seed_test_data` inside the `web` container — the same command as `invoke seed` above, just containerized.
- `invoke docker-test-down` stops the stack and removes its volumes; the next `docker-test-up` starts from an empty database.

This exercises the same images `docker-build.yml` pushes to `ghcr.io`, wired the way `deploy/prod/compose.yml` wires them — it catches image- and wiring-level breakage before a real deploy. It does not exercise Swarm-specific behavior (placement constraints, the `heltour.media` node label, external secrets/networks); that needs a real Swarm.

## 3. Before a production deploy

Full rationale: `docs/adr/0007-deploy-wiring-workflow-and-swarm-stack.md`.

**Deploy-mechanism assumption:** every service in `deploy/prod/compose.yml` gets `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `REDIS_URL`/`BROKER_URL`, `EMAIL_HOST*`, and `HELTOUR_ENV` via `env_file: "stack.env"`. Portainer resolves `env_file:` when deploying a stack; the raw `docker stack deploy -c` CLI has historically ignored it. If the tool driving a real deploy drops it, every service still boots, but with `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` empty (Django 400s every request) and `HELTOUR_ENV` falling back to `settings.py`'s `"dev"` default instead of `"prod"`. Confirm whichever tool triggers the deploy (Portainer, a CI runner, a manual op) actually resolves `env_file:` — or inline `stack.env`'s values into each service's `environment:` block as a fallback.

None of the following is checked by `docker compose -f deploy/prod/compose.yml config`. Confirm each before the first real deploy:

- Swarm secrets, created out-of-band on the manager (`docker secret create`): `heltour_prod_db_url`, `heltour_app_secret_key`, `heltour_prod_lichess_api_token`, `heltour_email_host_user`, `heltour_email_host_password`.
- **Slack + Google Sheets secrets are hard prerequisites, not deferrable integrations.** `heltour/tournament/slackapi.py`'s `_get_slack_token()` opens `settings.SLACK_API_TOKEN_FILE_PATH` unconditionally — left unwired (default `""`), it raises `FileNotFoundError` the first time any Slack-backed code path runs. `heltour/tournament/spreadsheet.py`'s `_open_doc()` has the same hard dependency on `GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH`. heltour production uses both Slack/chesster and Sheets (unlike litour) — despite the `TODO(ops)` comment at the bottom of `deploy/prod/compose.yml` flagging them as unwired, both must be wired (secret + matching `*_FILE_PATH` env var, following the `LICHESS_API_TOKEN_FILE_PATH` pattern) before cutover.
- The `caddy` network — external, front-facing, created outside this stack.
- The `heltour.media` node label, set on exactly one Swarm node: `docker node update --label-add heltour.media=true <node>`. `web` and `caddy` are pinned to it via `deploy.placement.constraints` (they share the media volume — `docs/adr/0002-media-named-volume-shared-web-caddy.md`) and both must land on the same node.
- One `HELTOUR_DEPLOY_PRODUCTION_<SERVICE>` GitHub repo secret per service (`apiworker`, `caddy`, `celery`, `migrate`, `web`) — `deploy.yml` POSTs to the URL each holds; a missing one fails that service's step outright. The workflow doesn't build or push anything itself; it assumes `docker-build.yml` already pushed the image and the listener at that URL pulls and redeploys.
- `EMAIL_HOST`/`EMAIL_PORT` in `stack.env`, verified against heltour's actual mail relay — currently an unverified placeholder carried from litour's `stack.env` (AWS SES `eu-west-3`).
- FCM secrets remain **not yet wired** in this stack (same `TODO(ops)` comment) — a known gap, not an oversight here.
