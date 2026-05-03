"""Django session-cookie auth bridge for the FastAPI service.

The Next.js UI and FastAPI both sit behind the same Caddy origin in prod
(`/`-Django, `/v2/api/*`-FastAPI), so the browser sends Django's
``sessionid`` cookie on every API request. This module decodes that
cookie via Django's session framework and resolves the corresponding
``User``. Domain-specific permission predicates live in each domain's
``permissions.py``; this module only handles identity.

The lookup is sync DB work; the FastAPI deps wrap it in ``in_thread``.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.utils import timezone
from fastapi import Request

from heltour.api.deps import in_thread


@dataclass(frozen=True)
class Viewer:
    user_id: int | None
    is_authenticated: bool
    is_staff: bool

    @classmethod
    def anonymous(cls) -> "Viewer":
        return cls(user_id=None, is_authenticated=False, is_staff=False)


def _resolve_viewer_sync(session_key: str | None) -> tuple[Viewer, object | None]:
    """Resolve a Django session cookie to a `(Viewer, User|None)` tuple.

    Returns the User object so callers that need to check league-scoped
    permissions (which run through django-guardian) can do so without a
    second DB hit.
    """
    if not session_key:
        return Viewer.anonymous(), None
    try:
        session = Session.objects.get(
            session_key=session_key, expire_date__gt=timezone.now()
        )
    except Session.DoesNotExist:
        return Viewer.anonymous(), None
    data = session.get_decoded()
    user_id = data.get("_auth_user_id")
    if not user_id:
        return Viewer.anonymous(), None
    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Viewer.anonymous(), None
    if not user.is_active:
        return Viewer.anonymous(), None
    return (
        Viewer(
            user_id=user.pk,
            is_authenticated=True,
            is_staff=bool(user.is_staff),
        ),
        user,
    )


async def get_viewer(request: Request) -> Viewer:
    cookie_name = settings.SESSION_COOKIE_NAME
    session_key = request.cookies.get(cookie_name)
    viewer, _ = await in_thread(_resolve_viewer_sync, session_key)
    return viewer


async def get_viewer_and_user(request: Request) -> tuple[Viewer, object | None]:
    cookie_name = settings.SESSION_COOKIE_NAME
    session_key = request.cookies.get(cookie_name)
    return await in_thread(_resolve_viewer_sync, session_key)
