"""Permission predicates for the round-management domain.

Today the only gated capability is "edit a pairing", which the legacy
Django views check with ``user.has_perm("tournament.change_pairing", league)``
(see `heltour/tournament/views.py:721,723`). We expose it here behind a
constructor-injected callable so tests can swap in a stub instead of
provisioning a Django guardian permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from heltour.api.shared.permissions import PermissionContext

# Signature: (user, league) -> bool. Default implementation hits Django.
HasPermFn = Callable[[object | None, object], bool]


def _default_has_perm(user: object | None, league: object) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return bool(user.has_perm("tournament.change_pairing", league))


@dataclass(frozen=True)
class ChangePairingPermission:
    """Instance-level permission: can the viewer edit a pairing in this league?

    The DI seam is the ``has_perm_fn`` constructor argument — production
    uses the real Django check; tests pass a fake. Keeping it a dataclass
    rather than a Protocol implementation means we don't need a registry
    to look it up.
    """

    type_name: str = "tournament.Pairing"
    has_perm_fn: HasPermFn = _default_has_perm

    def can_write(self, ctx: PermissionContext, league: object) -> bool:
        return self.has_perm_fn(ctx.user, league)

    def can_read(self, ctx: PermissionContext, league: object) -> bool:
        # Pairings are public reads today (anonymous viewers can see the
        # round). Kept here so a future change to "staff-only events" is
        # a single edit rather than chasing a bool through the codebase.
        return True


# Convenience for the legacy call site that takes (user, league) and
# returns bool — kept until the signal layer migrates to PermissionContext.
def can_change_pairing_sync(user, league) -> bool:
    return _default_has_perm(user, league)
