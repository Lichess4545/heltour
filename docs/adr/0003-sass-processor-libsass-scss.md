# 0003 - django-sass-processor + libsass for SCSS, drop Ruby sass

## Status

Accepted

## Context

heltour compiled SCSS via `django-static-precompiler`, which (per its own template tags,
formerly `{% load compile_static %}` / `{{ ... |compile_if_debug }}`) shells out to an
external `sass` binary at request- or build-time. litour's infrastructure — the target of
this port — carries a vestigial Ruby `sass` gem install in its image even though its own
settings use a Python compiler; that Ruby toolchain is pure dead weight to carry into a new
Docker image and devenv shell.

## Decision

Switch to `django-sass-processor` + `libsass` (a Python C-extension binding, no Ruby
runtime). `sass_processor` was added to `INSTALLED_APPS` with `SASS_PROCESSOR_*` settings and
a `sass_processor.finders.CssFinder` `STATICFILES_FINDERS` entry (`heltour/settings.py`);
templates were switched from `{% load ... compile_static %}` /
`{% static "...scss"|compile_if_debug %}` to `{% load ... sass_tags %}` /
`{% sass_src "...scss" %}` (`heltour/tournament/templates/empty_base.html`,
`.../tournament/admin/change_form_with_comments.html`); the now-dead `compile_if_debug`
filter was removed from `heltour/tournament/templatetags/tournament_extras.py`. Compilation
runs via `manage.py compilescss` (`sass_processor.management.commands.compilescss`), invoked
at Docker build time in `docker/Dockerfile.base` and as an `invoke compilescss` task
(`tasks.py`). No Ruby is installed anywhere — not in `docker/Dockerfile.base`, not in
`devenv.nix` (`languages.ruby` was dropped outright, along with litour's `GEM_HOME`/
`gem install sass` `enterShell` block) — including litour's own vestigial Ruby install, which
was not carried forward.

## Consequences

- One fewer language runtime in every image and every dev shell.
- SCSS compiles as a plain Python dependency (`libsass`), no subprocess-to-`sass`-binary
  indirection.
- `sass_processor.management.commands.compilescss` unconditionally imports `django-compressor`
  internals even though `compressor` is never added to `INSTALLED_APPS` — see ADR 0012 for
  that follow-on dependency requirement, discovered only once the Docker build was actually
  run.
- Any future SCSS feature that depends on a Ruby-sass-only construct is out of reach without
  reintroducing the Ruby toolchain this decision removed.
