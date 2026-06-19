"""Compatibility shim. Routes have moved into per-domain packages:

- health  -> heltour.api.shared.health
- v1      -> heltour.api.round_management.routes (round / match endpoints)
            and heltour.api.event_setup.routes (current-round endpoint)
- matches -> heltour.api.round_management.ws  (websocket)

Submodules in this package re-export the routers under their old names
so external scripts (e.g. `scripts/export_openapi.py`) continue to
work; the canonical homes are the domain packages.
"""
