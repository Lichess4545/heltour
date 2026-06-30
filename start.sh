#!/bin/bash
set -euo pipefail

# --- preflight: we need uv, and a Python 3.12 interpreter it can find ---------
# psycopg2-binary 2.9.9 and pillow 10.3.0 only ship wheels through cp312, and
# fabric3 1.14 is py2-era; on 3.13+/system 3.14 the install tries to compile and
# fails. We pin to a uv-managed 3.12 so nothing has to compile.
if ! command -v uv >/dev/null 2>&1; then
    echo "error: 'uv' is not installed. Install it (e.g. 'sudo pacman -S uv' or" >&2
    echo "       'curl -LsSf https://astral.sh/uv/install.sh | sh'), then re-run." >&2
    exit 1
fi

PYTHON="$(uv python find 3.12 2>/dev/null || true)"
if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
    echo "error: no Python 3.12 interpreter found. Install one with:" >&2
    echo "       uv python install 3.12" >&2
    exit 1
fi

# --- build the venv on that interpreter ---------------------------------------
virtualenv env --prompt="(heltour):" --python="$PYTHON"
source env/bin/activate
pip install poetry
poetry install

# fabric3 1.14 has a py2-era `from collections import Mapping`, removed in
# Python 3.10+. Rewrite it to its modern location. The loop guards against the
# glob matching nothing (so sed never gets a literal `*` path), and the anchored
# pattern makes re-runs a no-op once it's already been rewritten.
for f in env/lib/python3.*/site-packages/fabric/main.py; do
    [ -f "$f" ] && sed -i 's/^from collections import Mapping$/from collections.abc import Mapping/' "$f"
done

fab update
