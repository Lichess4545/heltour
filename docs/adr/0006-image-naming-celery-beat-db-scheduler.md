# 0006 - ghcr.io image naming and django-celery-beat/-results DB scheduler

## Status

Accepted

## Context

heltour needed a container image naming scheme and a way to run scheduled Celery tasks
(`CELERYBEAT_SCHEDULE`, e.g. `run_scheduled_events`) in Docker/Swarm, where a separate
long-lived beat container is one more moving part to deploy, monitor, and keep in sync with
the worker's task registry. litour's convention (`litour-*` image basenames under
`ghcr.io/lichess4545`, `django_celery_beat`'s `DatabaseScheduler`, `django_celery_results`
with a `django-db` backend, `celery worker -B` running beat embedded in the worker process)
was available to adapt.

## Decision

Image basenames become `heltour-*` under the same registry prefix,
`ghcr.io/lichess4545/heltour-*`, resolved by `docker/docker-bake.hcl`'s `tag()`/`REGISTRY`
mechanism (ported verbatim from litour) and consumed by `.github/workflows/docker-build.yml`.
Both `django_celery_beat` and `django_celery_results` were added to `INSTALLED_APPS`
(`heltour/settings.py`); `CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"`
and `CELERY_RESULT_BACKEND = "django-db"` were set on the celery app
(`heltour/celery.py`, `namespace="CELERY"`). `docker/Dockerfile.celery` runs
`celery worker -B` (embedded beat, no separate beat container/target in
`docker/docker-bake.hcl` or `deploy/prod/compose.yml`). `CELERY_BEAT_SCHEDULE` entries were
pruned to tasks that actually exist in heltour's `tasks.py` (litour's
`validate_pending_registrations`/`update-fide-ratings` entries reference tasks heltour
doesn't have and were dropped; litour's `celery-backend-cleanup` entry, a built-in Celery
task pairing with the new `django-db` results backend, was kept). heltour's own
`CELERYBEAT_SCHEDULE` (no-underscore-prefix, pre-namespacing name) attribute, read directly by
`heltour/tournament/tasks.py`, was preserved as an alias pointing at the same dict object as
`CELERY_BEAT_SCHEDULE`.

## Consequences

- One image tag prefix (`ghcr.io/lichess4545/heltour-*`) across CI build, push, and every
  compose/stack file — no separate naming convention to keep in sync.
- Beat schedule state (`django_celery_beat`'s DB-backed periodic tasks) survives container
  restarts and is inspectable/editable from the Django admin, unlike a file-based schedule.
- Running beat embedded in the worker (`-B`) means beat dies and restarts with the worker;
  acceptable at heltour's scale, but it forecloses running multiple worker replicas without
  first splitting beat back out (embedded beat must run exactly once cluster-wide).
- See ADR 0010 for a related, distinct bug found in the same settings area: the correct
  namespaced key is `CELERY_TASK_DEFAULT_QUEUE`, not litour's `CELERY_DEFAULT_QUEUE`.
