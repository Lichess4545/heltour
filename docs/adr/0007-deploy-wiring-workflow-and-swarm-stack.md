# 0007 - Deploy wiring: webhook workflow + one reference Swarm stack

## Status

Accepted

## Context

heltour needed CI to build/push its new Docker images and a way to trigger a production
rollout, plus a real compose/stack file to deploy them. litour has `docker-build.yml`
(buildx bake, per-target GHA cache scopes, push to ghcr on master, verify on every event),
`deploy.yml` (webhook/secrets-driven rollout, a service matrix, a `staging`/`production`
environment choice), and five deploy stacks (`litour-prod`, `kzctc-prod`, `kzctc-staging`,
`fidewom-prod`, `wucc-prod`) — only one of which (`litour-prod`) has any heltour analog; the
rest are event-specific litour deployments with no heltour equivalent to adapt.

## Decision

Port `docker-build.yml` near-verbatim (`.github/workflows/docker-build.yml`) — it references
`docker/docker-bake.hcl`'s `default` group by name rather than a hardcoded target list, so no
separate pruning was needed once the bake file itself was pruned. Add a new `test.yml`
(neither repo had one): Python 3.11 + poetry, `postgres:18-alpine` + `redis:7-alpine` service
containers matching `.env.example`'s credentials, running
`manage.py test --settings=heltour.test_settings` on every push/PR. Port `deploy.yml`
(`.github/workflows/deploy.yml`) with its service matrix pruned to heltour's five services
(`apiworker`, `caddy`, `celery`, `migrate`, `web` — no `watcher`) and the `staging`/
`production` environment choice dropped entirely, since heltour has exactly one stack.
Port exactly one reference stack, `deploy/prod/compose.yml` (from litour's
`deploy/litour-prod/compose.yml`), pruned to heltour's services (no `api`/`ui`/`watcher`), with
`SECRET_KEY_FILE` added to every Django-importing service (`web`, `apiworker`, `celery`,
`migrate` — litour's own stack omits this because litour's `SECRET_KEY` has a fallback
default; heltour's does not, see ADR 0008) and the ADR 0002 media volume/placement wiring. The
other four litour stacks (`kzctc-*`, `fidewom-prod`, `litour-staging`, `wucc-prod`) were not
ported. `.travis.yml` was deleted, superseded by `test.yml` + `docker-build.yml`.

## Consequences

- CI builds and verifies every push/PR; only `master` pushes images to ghcr.
- Exactly one deploy target exists in the repo (`deploy/prod/`) — there is no staging stack to
  accidentally deploy to or let drift out of sync with prod.
- `deploy.yml` is decoupled from `docker-build.yml` (matches litour: no automatic
  build-then-deploy chain) — a deploy still requires a separate manual/webhook trigger.
- Slack/Google Sheets/FCM secrets that heltour's production likely needs (unlike litour, whose
  fork doesn't use them) are not wired into `deploy/prod/compose.yml` — litour has no
  reference for their secret names/values, so this was left as a flagged gap rather than
  invented. `EMAIL_HOST`/`EMAIL_PORT` in `deploy/prod/stack.env` are also unverified
  placeholders carried from litour's own stack.env.
- `deploy.yml`'s webhook secrets (`HELTOUR_DEPLOY_PRODUCTION_*`) don't exist yet in this
  repo's GitHub secrets — provisioning them is a manual ops step outside this port's scope.
