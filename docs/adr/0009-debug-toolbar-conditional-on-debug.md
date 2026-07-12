# 0009 - debug_toolbar conditional on DEBUG

## Status

Accepted

## Context

Old heltour installed and enabled `django-debug-toolbar` unconditionally (app + middleware
always present), regardless of `DEBUG`. That means every request — including in a
misconfigured production deploy — paid the toolbar's overhead and exposed its introspection
surface.

## Decision

`heltour/settings.py` only appends `"debug_toolbar"` to `INSTALLED_APPS` and inserts
`debug_toolbar.middleware.DebugToolbarMiddleware` at the front of `MIDDLEWARE` when
`DEBUG` is true (`heltour/settings.py:90-91`, `:109-110`).

## Consequences

- A production deploy (`DEBUG=False`, the `settings.py` default) never loads the toolbar app
  or middleware — no accidental introspection surface, no per-request overhead.
- Local/dev runs (`DEBUG=True` in `.env`) get the toolbar exactly as before.
- Anyone needing the toolbar against `DEBUG=False` data (e.g. debugging a "prod-like"
  scenario) must temporarily flip `DEBUG`, which now also changes SCSS output style and other
  `DEBUG`-gated behavior (ADR 0003) — a deliberate coupling, not a limitation specific to this
  decision.
