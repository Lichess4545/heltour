import json
import os
import sys

# `python scripts/export_openapi.py` puts `scripts/` on sys.path but not the
# project root, so `import heltour` fails. Prepend the parent of this file's
# directory so the script works regardless of cwd.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from heltour.api.main import app  # noqa: E402


def main() -> None:
    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
