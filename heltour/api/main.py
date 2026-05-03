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

from heltour.api.middleware import DjangoConnectionMiddleware
from heltour.api.routes import health, matches, v1

app = FastAPI(title="Litour API", version="1")

app.add_middleware(DjangoConnectionMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(matches.router)
app.include_router(v1.router, prefix="/v1")


@app.get("/docs", include_in_schema=False)
def scalar_docs():
    return get_scalar_api_reference(openapi_url=app.openapi_url, title=app.title)
