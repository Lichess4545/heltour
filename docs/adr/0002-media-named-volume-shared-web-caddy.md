# 0002 - Media served via a named volume shared between web and caddy

## Status

Accepted

## Context

heltour's `web` container writes user-uploaded media (`MEDIA_ROOT`, default
`BASE_DIR/media` = `/app/media` inside the container). Caddy serves static/media assets and
reverse-proxies everything else to `web`. The two run as separate containers/services, so
Caddy needs its own view of the same files `web` writes. litour — the infrastructure this
port is based on — never solved this: it has no equivalent shared-media wiring. On a
multi-node Swarm, a plain default-local-driver named volume gives each service its own empty
volume if they land on different nodes, silently losing uploads (caddy would 404 on files
`web` actually wrote).

## Decision

Define one named volume (`media_data`) in `deploy/prod/compose.yml`, mounted at
`/app/media` in `web` (write side) and `/public/media` in `caddy` (read side). `docker/Caddyfile`
serves `/media/*` via `handle_path /media/* { root * /public/media; file_server }`.
`docker/Dockerfile.base` creates `/app/media` and `chown`s it to the non-root `heltour` user
before `USER heltour` (`docker/Dockerfile.base`), so a fresh volume mount inherits writable
ownership instead of coming up root-owned. Because a default local-driver volume has no node
affinity, `deploy/prod/compose.yml` pins both `web` and `caddy` to the same Swarm node via
`deploy.placement.constraints: [node.labels.heltour.media == true]`, with a comment
documenting the operational contract: the operator must label exactly one node
(`docker node update --label-add heltour.media=true <node>`), or swap in a shared-storage
volume driver (nfs/glusterfs/cloud block storage) if `web`/`caddy` need to scale across nodes.

## Consequences

- Media works out of the box on a single-node or single-labeled-node Swarm without inventing
  new infrastructure.
- The node-pin constraint caps `web`/`caddy` scaling to one node until an operator switches to
  a shared-storage volume driver — an explicit, documented tradeoff, not a silent limitation.
- Forgetting to label a node before `docker stack deploy` leaves both services unschedulable
  rather than silently losing uploads — a visible failure over a silent one.
- This is an improvement over litour, which has no reference answer for media at all.
