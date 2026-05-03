"""Four-tier permission scaffolding.

We connect to a websocket on every page, so the browser receives streamed
updates for many object types. The API is the boundary that decides what
the viewer is allowed to see and do. Permissions are checked at four
tiers, in increasing specificity:

  1. endpoint  — can the viewer call this route at all?
  2. type      — for objects of this kind, what can the viewer read/write?
  3. instance  — for *this* particular object, what can the viewer do?
  4. field     — which fields on this instance are visible / editable?

This module gives small protocol-shaped primitives that domain packages
implement. We don't try to build a generic policy engine: each domain
plugs in its own predicates with simple constructors so they're easy to
swap in tests (DI seam = a constructor argument, nothing fancier).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException

from heltour.api.shared.auth import Viewer


@dataclass(frozen=True)
class PermissionContext:
    """Inputs every permission predicate accepts.

    `viewer` is the lightweight, immutable identity record (always
    available, even for anonymous). `user` is the live Django ``User``
    when authenticated; predicates that need ``has_perm`` against a
    league/season instance must use this.
    """

    viewer: Viewer
    user: object | None


class TypePermission(Protocol):
    """What can the viewer do with objects of this type?

    Implementations are constructed once per request (or once globally
    for stateless predicates) and asked yes/no questions about whole
    types — useful when an endpoint wants to decide *whether to even
    query* for a list, before instance-level filtering.
    """

    type_name: str

    def can_read(self, ctx: PermissionContext) -> bool: ...

    def can_write(self, ctx: PermissionContext) -> bool: ...


class InstancePermission(Protocol):
    """Per-instance read/write — for league-scoped permissions where a
    viewer may be staff for one league but not another. Implementations
    receive the concrete ORM instance (or any object the domain prefers
    to pass) and answer per-instance.
    """

    type_name: str

    def can_read(self, ctx: PermissionContext, instance: object) -> bool: ...

    def can_write(self, ctx: PermissionContext, instance: object) -> bool: ...


class FieldPermission(Protocol):
    """Per-field visibility — used to redact specific fields on objects
    the viewer is otherwise allowed to read. Returning ``None`` means
    "all fields visible". Returning a set restricts the projection.

    Domains that want field-level redaction call this *before* building
    the DTO and either drop the field or pass a sentinel.
    """

    type_name: str

    def visible_fields(
        self, ctx: PermissionContext, instance: object
    ) -> set[str] | None: ...

    def editable_fields(
        self, ctx: PermissionContext, instance: object
    ) -> set[str] | None: ...


class EndpointGuard(Protocol):
    """An endpoint-level check. Raises ``HTTPException`` on denial.

    Used as a FastAPI dependency at the route layer. Domains can compose
    several of these — e.g. require auth, then require league staff —
    by sequencing them in the route's ``dependencies=[]`` list.
    """

    def __call__(self, ctx: PermissionContext) -> None: ...


def require_authenticated(ctx: PermissionContext) -> None:
    """Built-in endpoint guard: raise 401 unless the viewer is authenticated."""
    if not ctx.viewer.is_authenticated:
        raise HTTPException(status_code=401, detail="not authenticated")


def deny(detail: str = "forbidden") -> None:
    """Raise 403 with a uniform shape so the frontend can render a
    consistent denial message.
    """
    raise HTTPException(status_code=403, detail=detail)
