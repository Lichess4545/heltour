# 0013 - Vendor javafo.jar into thirdparty/

## Status

Accepted

## Context

`heltour/tournament/pairinggen.py`'s `JavafoInstance` calls the `JAVAFO_COMMAND` setting
(default `java -jar ./thirdparty/javafo.jar`, `heltour/settings.py:36`) to run Swiss pairing
generation. heltour had no `thirdparty/javafo.jar` anywhere in its git history — the README
only documented it as an optional manual download. litour tracks the identical jar in git at
the same relative path. Without it, the pairing-generation path is unreachable, and
`docker/Dockerfile.web`'s `web-verify` stage (which sanity-checks the jar via
`java -jar /app/thirdparty/javafo.jar` and greps its banner) has nothing to check.

## Decision

Copy `thirdparty/javafo.jar` from litour byte-for-byte (`sha256sum` verified identical:
`6d1eef8f...`) into heltour's `thirdparty/javafo.jar`, as a vendored infrastructure binary —
not application code, not regenerated or rebuilt.

## Consequences

- `web-verify`'s javafo check (`docker/Dockerfile.web`/`docker-bake.hcl`'s `javafo-verify`
  target) actually runs and passes (`JaVaFo (rrweb.org/javafo) - Rel. 2.2 (Build 3223)`),
  rather than being a no-op against a missing file.
- The pairing-generation path is functional at runtime in every environment (devenv, Docker)
  without a manual post-clone download step.
- The jar is binary content in git history now, not a documented external download — future
  JaVaFo version bumps must replace this file deliberately (and re-verify the sha) rather than
  relying on the README's old "download it yourself" instructions, which still describe the
  now-superseded manual path for anyone not using the vendored copy.
- Corrected: the "functional in every environment" claim above was false for the `heltour-celery`
  container until a follow-up fix. Pairing generation runs as an `@app.task` (`pairinggen.py`),
  which executes inside `celery`, not `web` — but the `openjdk-17-jre-headless` install lived
  only in `docker/Dockerfile.web`, so `heltour-celery` had no `java` and the task would fail at
  runtime the first time a round was paired. Fixed by moving the `openjdk-17-jre-headless`
  install into `docker/Dockerfile.base` (inherited by every image built from it, `web` and
  `celery` alike) and removing the now-duplicate install from `docker/Dockerfile.web`.
  `docker-bake.hcl` gained a matching `celery-javafo-verify` target (`Dockerfile.celery`'s new
  `celery-verify` stage) so a missing `java`/jar in the celery image fails the build the same
  way `javafo-verify` does for web.
