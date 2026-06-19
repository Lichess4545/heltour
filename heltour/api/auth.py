"""Compatibility shim — auth has moved to ``heltour.api.shared.auth``.

The single domain-specific permission predicate that used to live here
(``can_change_pairing_sync``) now lives in
``heltour.api.round_management.permissions`` so each domain owns its
own permissions. Re-exported here only to keep external imports
working while callers migrate.
"""

from heltour.api.round_management.permissions import (  # noqa: F401
    can_change_pairing_sync,
)
from heltour.api.shared.auth import (  # noqa: F401
    Viewer,
    get_viewer,
    get_viewer_and_user,
)
