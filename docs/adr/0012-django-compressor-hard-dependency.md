# 0012 - django-compressor as a hard dependency, not an installed app

## Status

Accepted

## Context

`sass_processor.management.commands.compilescss` (the command ADR 0003 adopted for SCSS
compilation) unconditionally imports `from compressor.exceptions import ...` and
`compressor.offline.django.DjangoParser` at module load — regardless of whether the
`compressor` Django app is enabled. `INSTALLED_APPS` deliberately does not include
`"compressor"` (heltour has no other use for django-compressor's own asset pipeline). This
was missed during the settings cutover and only surfaced when `docker/Dockerfile.base`'s
`compilescss` build step actually ran and failed with `ModuleNotFoundError: No module named
'compressor'`.

## Decision

Add `django-compressor` to `pyproject.toml` as a plain dependency and regenerate
`poetry.lock`, without adding `"compressor"` to `INSTALLED_APPS`. Verified locally
(`poetry run python manage.py compilescss` → `Successfully compiled 2 referred SASS/SCSS
files`) before re-running the Docker build, which then passed.

## Consequences

- `compilescss` (used by `docker/Dockerfile.base`'s build step and the `invoke compilescss`
  task in `tasks.py`) works.
- A reader of `INSTALLED_APPS` alone would not learn that `django-compressor` is present in
  the dependency graph — this ADR is the record of why it's in `pyproject.toml` despite that.
- If `sass_processor` ever changes its internal dependency on `compressor`, this constraint
  should be re-verified rather than assumed to still hold.
