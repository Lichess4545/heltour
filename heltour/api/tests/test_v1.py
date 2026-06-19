"""Test classes have moved into per-domain test packages:

- ``heltour.api.round_management.tests.test_round_matches`` —
  Round, slug, lone, N+1 tests.
- ``heltour.api.round_management.tests.test_permissions`` —
  ``ChangePairingPermission`` DI-injection tests.
- ``heltour.api.round_management.tests.test_http`` — TestClient-based
  HTTP integration coverage for the v1 routes.
- ``heltour.api.event_setup.tests.test_current_round`` —
  ``current_round_sync`` resolver tests.

Kept as a placeholder so any external runner that points at this path
still imports cleanly.
"""
