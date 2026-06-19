from django.db import close_old_connections
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class DjangoConnectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        close_old_connections()
        try:
            return await call_next(request)
        finally:
            close_old_connections()


def close_db_connections() -> None:
    close_old_connections()
