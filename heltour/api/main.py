import logging
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "heltour.settings")
django.setup()

# Django's settings.LOGGING already configured root handlers; just make sure
# our module loggers are at INFO so connect/forward lines come through.
logging.getLogger("heltour.api").setLevel(logging.INFO)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from scalar_fastapi import get_scalar_api_reference

from heltour.api.event_setup import routes as event_setup_routes
from heltour.api.middleware import DjangoConnectionMiddleware
from heltour.api.registration import routes as registration_routes
from heltour.api.roster_formation import routes as roster_formation_routes
from heltour.api.round_management import routes as round_management_routes
from heltour.api.round_management import ws as round_management_ws
from heltour.api.shared import health
from heltour.api.standings import routes as standings_routes

app = FastAPI(title="Litour API", version="1")

app.add_middleware(DjangoConnectionMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Health is unprefixed; everything else lives under /v1.
app.include_router(health.router)

# Round-management WS is unprefixed (matches the existing client URL).
app.include_router(round_management_ws.router)

# Per-domain v1 routers — adding a new chess domain means adding one
# include_router line here, nothing else.
app.include_router(round_management_routes.router, prefix="/v1")
app.include_router(event_setup_routes.router, prefix="/v1")
app.include_router(registration_routes.router, prefix="/v1")
app.include_router(roster_formation_routes.router, prefix="/v1")
app.include_router(standings_routes.router, prefix="/v1")


@app.get("/docs", include_in_schema=False)
def scalar_docs():
    return get_scalar_api_reference(openapi_url=app.openapi_url, title=app.title)
