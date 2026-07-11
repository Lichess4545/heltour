# 0011 - Baked docker/Caddyfile is the single source of truth

## Status

Accepted

## Context

litour's `Dockerfile.caddy` bakes no Caddyfile into the image at all — it only
`COPY --from=builder /app/static /public/static`; the actual Caddyfile is supplied per-stack
via a `./conf:/etc/caddy` bind mount in each of litour's deploy stacks
(`litour-prod`, `kzctc-prod`, `kzctc-staging`, `fidewom-prod`, `wucc-prod`). That pattern
exists because those stacks serve genuinely different route sets (`/v2/api/*` → FastAPI,
`/v2/*` → Next.js UI, varying by which sibling services exist in each stack). heltour has no
FastAPI/Next.js split and only one deploy stack (`deploy/prod/`, ADR 0007) — its routing shape
(`/static/*`, `/media/*`, everything else → `web:8000`) is identical across every environment
it will ever run.

## Decision

`docker/Dockerfile.caddy` bakes `docker/Caddyfile` directly into the `heltour-caddy` image
(`COPY docker/Caddyfile /etc/caddy/Caddyfile`). `deploy/prod/compose.yml`'s `caddy` service has
no `./conf` bind mount for Caddyfile content — only `caddy_data`/`caddy_config` (Caddy's own
runtime state) and the ADR 0002 `media_data` volume.

## Consequences

- Exactly one copy of the Caddyfile exists in the repo (`docker/Caddyfile`); there is no
  second, deploy-stack-local copy that can textually drift from the image's baked-in version.
- Changing routing requires rebuilding the `heltour-caddy` image — there is no way to hot-swap
  routing via a bind-mount without reintroducing litour's pattern.
- If heltour ever needs environment-specific routing (e.g. a genuine staging stack with a
  different route set), that is the trigger to revisit this decision and switch back to a
  bind-mounted Caddyfile per stack — not before.
