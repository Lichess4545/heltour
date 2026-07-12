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

## 4. Before a staging deploy

`deploy/staging/compose.yml` mirrors `deploy/prod/compose.yml` service-for-service (`docs/adr/0015-staging-stack-and-deploy-trigger-policy.md`) — everything in §3 above applies, staging-scoped, plus:

- Swarm secrets, distinct from prod's: `heltour_staging_db_url`, `heltour_staging_secret_key`, `heltour_staging_lichess_api_token`, `heltour_staging_email_host_user`, `heltour_staging_email_host_password` — fully env-scoped, unlike prod's `heltour_app_secret_key`/`heltour_email_host_*`, which aren't.
- `HELTOUR_ENV=stage` in `deploy/staging/stack.env` — not `staging`. `heltour/settings.py`'s `STAGING` flag checks the literal string `"stage"`; anything else silently leaves it `False`.
- DNS for `staging.lichess4545.com`/`staging.lichess4545.tv` pointed at the same swarm the `caddy` external network fronts — staging reuses that network and the baked-in `docker/Caddyfile` (ADR 0011), no separate Caddyfile or edge config exists in this repo.
- The `heltour.media` node label — staging reuses the same labeled node as prod (`deploy/staging/compose.yml`'s `web`/`caddy` placement constraint is identical); no second label to provision.
- One `HELTOUR_DEPLOY_STAGING_<SERVICE>` GitHub repo secret per service, mirroring `HELTOUR_DEPLOY_PRODUCTION_<SERVICE>` — fires automatically on every push to `master`; production stays `workflow_dispatch`-only.

## 5. Testing the staging deploy

`deploy/staging/compose.local-test.yml` overlays `deploy/staging/compose.yml` unchanged onto a local single-node Swarm — unlike §2's plain-`docker-compose` harness, this exercises the actual Swarm stack: its `*_FILE` secret wiring, the external `caddy` network, the `heltour.media` placement constraint, and `stack.env`. The overlay adds only what §4 says staging assumes exists already: a local `postgres` service (standing in for the external DB) and a host-published port for `caddy` — **http://localhost:8091** (no DNS/TLS needed; `docker/Caddyfile` has no host-based routing).

- `invoke staging-test-up` initializes a local Swarm if none is active (an already-active Swarm is reused, never re-initialized), builds the five `docker/docker-bake.hcl production` images tagged as `ghcr.io/lichess4545/heltour-*:latest` so `docker stack deploy --resolve-image=never` runs them without a registry pull, creates the five `heltour_staging_*` secrets from dummy local values, creates the external `caddy` network, labels the local node `heltour.media=true`, and deploys stack `staging` from both compose files.
- `invoke staging-test-seed` (`--flush` to recreate) execs `seed_test_data` into the running `staging_web` task's container.
- `invoke staging-test-down` removes the stack, the five secrets, the `caddy` network, and the node label, and leaves Swarm mode only if `staging-test-up` initialized it — tracked in a gitignored `.staging-test-harness-state.json` so a Swarm already in use for something else is never torn down.

This proves the stack converges on the real placement constraint and secret wiring, and that `migrate`'s `restart_policy` correctly retries until its (local) database is reachable — confirmed by the `STAGING ENVIRONMENT` banner, which Django only renders once `HELTOUR_ENV=stage` has actually resolved through `stack.env`. It does not exercise real DNS/TLS, a registry pull, or the `deploy.yml` GitHub webhook path.

## 6. CI via Dagger

All three GitHub Actions workflows (`test.yml`, `docker-build.yml`, `deploy.yml`) are thin: checkout, install Nix + devenv (`.github/actions/setup-devenv`), then a single `devenv shell -- dagger call --mod=.dagger <function>`. Every pipeline decision — the Django suite run, the image graph, the publish tag, the deploy webhooks — lives in the Dagger module at `.dagger/src/index.ts`, not in YAML.

The Dagger CLI is not installed separately: `devenv.nix` pulls `dagger` from the `dagger/nix` flake pinned in `devenv.yaml`/`devenv.lock`, at the version matching `dagger.json`'s `engineVersion`. `devenv shell` — the same command a developer runs locally — is CI's only source for the CLI, so local and CI always run the identical build. Run the same functions CI runs, from inside `devenv shell` (or prefixed with `devenv shell --`):

- `dagger call test --source=.` — spins up Postgres 18 and Redis 7 as Dagger services and runs `manage.py test --settings=heltour.test_settings`, mirroring `test.yml`.
- `dagger call build --source=. --github-short-sha=$(git rev-parse --short HEAD)` — builds `docker/Dockerfile.base` once, derives the `web`/`api-worker`/`celery`/`migrate`/`caddy` images from it, and runs both verification checks: the Django suite inside the image (mirroring `docker/Dockerfile.web-verify`) and the vendored `javafo.jar` smoke test on the `web` and `celery` images (mirroring the `web-verify`/`celery-verify` Dockerfile stages).
- `dagger call publish --source=. --ref=refs/heads/master --event-name=push --registry-username=<user> --registry-password=env://GITHUB_TOKEN --github-sha=$(git rev-parse HEAD)` — runs `build`, then pushes all six images to `ghcr.io/lichess4545/heltour-*`. Needs a token with `packages:write` on the repo.
- `dagger call deploy --environment=staging --service=web --url=env://DEPLOY_URL` — POSTs to a single service's deploy webhook (`DEPLOY_URL` in the environment), mirroring one matrix leg of `deploy.yml`'s `deploy-staging`/`deploy-production` jobs.

`dagger functions` lists the full set, including the per-image functions (`base`, `web`, `apiWorker`, `celery`, `migrate`, `caddy`) usable standalone, e.g. `dagger call web --source=. terminal` to shell into a built web image.

**Caching.** Within one `dagger call` invocation — and across invocations that share the same local Dagger engine, which is what happens across the sequential steps of a single GitHub Actions job — layer caching is automatic: BuildKit content-addresses every operation, so `build` and `publish` never redo work `test` (or an earlier step) already did. This is why `docker/Dockerfile.base`'s `poetry install` and `compilescss`/`collectstatic` steps only run once even though `build`, `publish`, and every derived-image function all depend on `base`.

That within-run cache does not survive an ephemeral GitHub-hosted runner between separate workflow runs — the runner, and the Dagger engine container on it, are thrown away afterward. `test.yml` and `docker-build.yml` close that gap with `.github/actions/dagger-engine-cache`, without any external service:

- It restores a [GitHub Actions cache](https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows) of `/tmp/dagger-engine-cache` — a plain host directory, keyed on `runner.os` + a hash of `dagger.json` (so it resets automatically if `engineVersion` changes) — then starts the Dagger engine itself as an explicit `docker run --privileged` container, bind-mounting that directory at `/var/lib/dagger`, the engine's BuildKit state path. It points `dagger call` at that container via [`_EXPERIMENTAL_DAGGER_RUNNER_HOST=container://dagger-engine-heltour`](https://docs.dagger.io/reference/configuration/custom-runner/) instead of letting the CLI auto-provision (and instantly discard) its own. `.github/actions/dagger-engine-cache-stop` stops the container and `chown`s the directory back to the runner user (relies on the passwordless `sudo` GitHub-hosted runners ship with) so the cache's post-job save step, registered when the restore step ran, can actually read and archive it — run with `if: always()` so a build/test failure still saves whatever cache exists.
- **Graceful degradation:** every step that isn't the `dagger call` itself is written to fail soft. A cache miss (first run, or a `dagger.json` change) just means `/tmp/dagger-engine-cache` starts empty — `docker run` still succeeds, the engine starts cold. If the `docker run` itself fails for any reason, the action skips exporting `_EXPERIMENTAL_DAGGER_RUNNER_HOST` entirely and logs a `::warning::`; `dagger call` then falls back to its own normal auto-provisioned, uncached engine, exactly like before this existed. Nothing about this can hang or hard-fail the job on a cache problem.
- **Confirmed locally** (not from real CI): bind-mounting `/var/lib/dagger` and reconnecting via `_EXPERIMENTAL_DAGGER_RUNNER_HOST` genuinely persists and reuses cache — a `dagger call test` cold run took 2m51s; a second run against a brand-new container reusing the same directory (simulating a fresh runner) took 1m41s and Dagger's own progress output marked the cached step `CACHED`. That's a same-machine simulation of two containers sharing a directory, not two real GitHub Actions runs — actual hit rate (network/runner-provisioning overhead, real GHA cache upload/download time, concurrent-job contention) is unverified until this has run in CI twice.
- **Limits, honestly:** GitHub Actions caches are capped at 10GB per repository (LRU-evicted) with a 7-day access-based retention. Because a cache entry can't be overwritten, each run saves under a fresh key (`...-${{ github.run_id }}`) and restores from the most recent match via `restore-keys` — so every run uploads a fresh multi-hundred-MB-to-low-GB snapshot of the whole engine state rather than an incremental diff; heavy concurrent CI traffic will evict older entries faster than a single cloud-backed cache would, and there's no cross-fork sharing (a fork PR gets its own cache scope, same as any other GitHub Actions cache — never a hard failure, just a cold run). `_EXPERIMENTAL_DAGGER_RUNNER_HOST` is explicitly marked experimental by Dagger and could change across engine versions. Compared to [Dagger Cloud](https://docs.dagger.io/) (a hosted, always-warm, fully shared cache across every run and fork) or a self-hosted persistent-engine runner (no ephemeral-runner problem at all, but real infrastructure to run), this is the free, zero-ops option — deliberately chosen here — with a real but bounded ceiling.

The old buildx-bake registry cache (`docker-bake.hcl`'s `cache_to`/`cache_from` writing `heltour-*:buildcache` tags to `ghcr.io`) is superseded by this and no longer runs from CI — `docker-bake.hcl` remains as the local-only build path for §2–5 above, untouched.
