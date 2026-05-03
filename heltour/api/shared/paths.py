"""Reusable FastAPI path-parameter validators.

The slug pattern matches Django's SlugField charset; constraining path
params to it rejects NUL bytes and other oddities at the FastAPI layer
with a 422 instead of letting them reach Postgres (which raises on NUL
and surfaces as a 500).
"""

from typing import Annotated

from fastapi import Path

SLUG_PATTERN = r"^[-a-zA-Z0-9_]+$"
SlugPath = Annotated[str, Path(pattern=SLUG_PATTERN, max_length=64)]
