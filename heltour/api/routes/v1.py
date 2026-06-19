"""Compatibility shim — round / match endpoints moved to
``heltour.api.round_management.routes`` and the current-round endpoint
moved to ``heltour.api.event_setup.routes``.

Re-exports the sync helpers under their old names so the test suite at
``heltour/api/tests/test_v1.py`` keeps working until tests migrate to
the per-domain test packages.
"""

from heltour.api.event_setup.service import (  # noqa: F401
    current_round_sync as _current_round_sync,
)
from heltour.api.round_management.service import (  # noqa: F401
    round_matches_by_id_sync as _round_matches_by_id_sync,
    round_matches_by_slug_sync as _round_matches_by_slug_sync,
    set_match_result_sync as _set_match_result_sync,
)
