# 0010 - Fix two latent litour settings bugs rather than port them

## Status

Accepted

## Context

Two bugs in litour's `settings.py` were discovered while porting, both because heltour's own
test suite and application code exercise paths litour's does not:

1. litour sets `CELERY_DEFAULT_QUEUE = env(...)`, but `heltour/celery.py`/litour's
   `celery.py` both load config with `app.config_from_object(..., namespace="CELERY")`,
   which requires the namespaced key `CELERY_TASK_DEFAULT_QUEUE` — Celery's
   `config_from_object` silently ignores the unnamespaced `CELERY_DEFAULT_QUEUE`, so the
   default task queue silently fell back to Celery's own hardcoded `"celery"` queue instead of
   `"heltour-dev"`/`"heltour-{env}"`. Confirmed directly via `app.conf.task_default_queue`.
2. litour's `FileAwareEnv(...)` declares `LICHESS_OAUTH_REDIRECT_SCHEME` default as `"https"`
   (no `://`), but `heltour/tournament/oauth.py` does a literal
   `http_url.replace('http://', settings.LICHESS_OAUTH_REDIRECT_SCHEME)` — the value must
   include `://` or the replacement mangles the URL. Caught via a real test failure
   (`test_oauth_redirect`) on the first run against the ported settings.

## Decision

`heltour/settings.py` sets `CELERY_TASK_DEFAULT_QUEUE = env("CELERY_DEFAULT_QUEUE").format(...)`
(`heltour/settings.py:212-215`) — the Django setting name is namespace-correct while the env
var name (`CELERY_DEFAULT_QUEUE`) is unchanged, so `.env.example` and deploy tooling are
unaffected. `LICHESS_OAUTH_REDIRECT_SCHEME`'s `FileAwareEnv` default was fixed to `"https://"`
(`heltour/settings.py:29`), with `.env.example` set explicitly to `https://` as well.

## Consequences

- Celery tasks actually route to the intended `heltour-{env}` queue instead of Celery's
  default `"celery"` queue — a Task 1 verification step (`app.conf.task_default_queue`)
  confirms this directly.
- `test_oauth_redirect` and the real OAuth login flow produce well-formed redirect URLs.
- Both bugs remain present in litour itself — fixing litour was out of scope for this port;
  this decision only records that heltour's copy diverges from litour's on these two points,
  intentionally.
