# 0015 - Staging deploy stack, auto-deployed on push; production stays manual

## Status

Accepted

## Context

ADR 0007 ported exactly one deploy target (`deploy/prod/`) because heltour had exactly one
stack at the time; its Consequences note "there is no staging stack to accidentally deploy to
or let drift out of sync with prod" — true then, no longer the goal. Dr. Dub decided heltour
needs a staging environment, and that staging and production should not share a trigger: every
push to `master` should reach staging without a human in the loop, while production continues
to require an explicit, manual trigger. `.github/workflows/deploy.yml` previously had no `push`
trigger at all (`workflow_call` + `workflow_dispatch` only) — the single `deploy` job's
`if: github.ref == 'refs/heads/master'` gate only ever mattered for dispatches run against a
non-master ref, since nothing pushed to it.

heltour's own `heltour/settings.py:51` reads `STAGING = env("HELTOUR_ENV") == "stage"` — the
literal string `"stage"`, not `"staging"` — discovered while wiring `deploy/staging/stack.env`;
using the more obvious `"staging"` would have silently left `settings.STAGING` `False` in the
one environment that flag exists for.

## Decision

Add `deploy/staging/` (`compose.yml`, `stack.env`), service-for-service identical to
`deploy/prod/` — same images (`ghcr.io/lichess4545/heltour-*:latest`), same `media_data`
node-pinned placement (`node.labels.heltour.media == true`, ADR 0002), same `migrate`
`restart_policy: on-failure`, same shared external `caddy` network and baked-in
`docker/Caddyfile` (ADR 0011 — staging's route set is identical to prod's, so the "revisit if a
genuine staging stack needs different routing" trigger in ADR 0011 does not fire). It differs
only in: fully staging-scoped secret names (`heltour_staging_db_url`,
`heltour_staging_secret_key`, `heltour_staging_lichess_api_token`,
`heltour_staging_email_host_user`, `heltour_staging_email_host_password` — all five scoped,
unlike prod's partially-scoped `heltour_app_secret_key`/`heltour_email_host_*`) and
`stack.env`'s `HELTOUR_ENV=stage`, `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` pointed at
`staging.lichess4545.com`/`staging.lichess4545.tv` (recovered from the pre-port
`heltour/settings_staging.py`, `git show ffe0c585:heltour/settings_staging.py`). Volume/network
names inside both compose files stay unprefixed (`media_data`, `heltour`, etc.); the `prod_`/
`staging_` prefix comes from the compose project name (directory-derived) or Swarm stack name
at deploy time, not from the file — verified via `docker compose -f deploy/staging/compose.yml
--env-file deploy/staging/stack.env config`, which resolves to `staging_media_data`,
`staging_heltour` (overlay), etc.

`.github/workflows/deploy.yml` gains a `push: branches: [master]` trigger and splits the
single `deploy` job into `deploy-staging` (`if: github.ref == 'refs/heads/master' &&
github.event_name == 'push'`) and `deploy-production` (`if: github.ref == 'refs/heads/master'
&& github.event_name != 'push'`) — the `!= 'push'` guard is what keeps production from
auto-deploying now that a `push` trigger exists at all. Both jobs use the same per-service
webhook-curl matrix as before; `deploy-staging` reads `HELTOUR_DEPLOY_STAGING_<SERVICE>`
secrets, `deploy-production` keeps `HELTOUR_DEPLOY_PRODUCTION_<SERVICE>`.

## Consequences

- Every push to `master` redeploys staging automatically, with no separate approval step —
  a broken `master` reaches staging immediately, by design; production is unaffected.
- Production deploys remain exactly as manual as before this change (`workflow_dispatch`, or a
  future `workflow_call`) — `deploy-production`'s added `event_name != 'push'` guard is the only
  behavioral change to that job, and it only matters because `push` is now a workflow trigger.
- Amends ADR 0007's consequence "there is no staging stack to accidentally deploy to or let
  drift out of sync with prod" — one now exists, kept in sync by construction (both compose
  files are hand-mirrored; a change to one that isn't ported to the other is a review gap, not
  caught by tooling).
- `HELTOUR_DEPLOY_STAGING_<SERVICE>` (5 secrets) and all five `heltour_staging_*` Swarm secrets
  are new ops-provisioning work, same as ADR 0007 left `HELTOUR_DEPLOY_PRODUCTION_<SERVICE>` and
  `heltour_prod_*` as manual ops steps outside this change's scope. DNS for
  `staging.lichess4545.com`/`.tv` and confirming they're pointed at the same swarm as the
  `caddy` external network are also ops steps.
- Staging and production share the same Swarm `heltour.media`-labeled node and the same `caddy`
  ingress network — there is no isolation between them at the infrastructure level beyond
  separate secrets/volumes/overlay networks. If staging traffic or a staging incident should
  not be able to affect prod's shared node, that is a reason to revisit this, not a gap in it.
