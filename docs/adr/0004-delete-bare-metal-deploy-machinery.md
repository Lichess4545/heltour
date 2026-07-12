# 0004 - Delete bare-metal deploy machinery

## Status

Accepted

## Context

heltour carried a fabric-based bare-metal deploy path: `fabfile.py` + `strabulous.py`
(fabric helpers), `start.sh` (bootstrap: `uv`/`virtualenv`/`poetry install`/`fab update`),
`ubuntu-deps.sh` (apt-get installer for `python3.6`/`postgresql`/`mercurial` on the deploy
box), and `sysadmin/` — 21 files of systemd units, nginx vhost confs, and
`run-heltour-*`/`migrate-*`/`invalidate-*`/`update-requirements-*` shell scripts, all
hardcoded to a single fabric-deployed box layout
(`/home/lichess4545/web/www.lichess4545.com/...`). `sysadmin/backup.py`/`backup.sh` were
part of that same coupling: a crontab-driven rotation scheme referencing the fabric-deployed
`current/sysadmin/backup.py` path. None of this is reachable once devenv (dev) and the Docker
images + `deploy/prod/` Swarm stack (prod) exist. Separately, root-level `backup.sh`/
`restore.sh` are plain `pg_dump`/`psql`-restore convenience scripts against a local Postgres,
with no fabric or deploy-path coupling.

## Decision

Delete `fabfile.py`, `strabulous.py` (confirmed via grep: imported nowhere but each other),
`start.sh`, `ubuntu-deps.sh`, and the entire `sysadmin/` directory, including
`sysadmin/backup.py`/`sysadmin/backup.sh`. Keep root `backup.sh` and `restore.sh` as-is — they
are standalone operator tooling, not deploy machinery. Git history retains every deleted file
if it's ever needed for reference. README.md's `requirements`/`install` sections (which
described `fabfile`/`fab`/`virtualenv`/`./start.sh`) were rewritten to describe devenv +
poetry + invoke; a new `deployment` section points at `docker buildx bake`, `.github/workflows/`,
and `deploy/prod/`. A full grep sweep (`fabfile|strabulous|start\.sh|ubuntu-deps|sysadmin|...`)
across all tracked files confirmed no dangling references remain.

## Consequences

- No code path in the repo still assumes a single hand-provisioned Ubuntu box.
- Anyone deploying heltour today has exactly one documented path (devenv for dev, Docker/Swarm
  for prod) instead of two competing ones.
- The fabric-era deploy knowledge (exact systemd unit shapes, nginx vhost details) is only
  recoverable from git history, not from a live file in the tree — an explicit tradeoff in
  favor of not maintaining dead machinery.
- `backup.sh`/`restore.sh` remaining at the root is a deliberate carve-out, not an oversight:
  they were individually inspected and found decoupled from the deleted deploy path.
