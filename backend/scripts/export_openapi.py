"""Write `docs/openapi.json` from the live application.

The frontend generates its TypeScript types from this file, which makes it a build input
rather than documentation. Generating it from the app - never editing it by hand - is what
keeps the two in step: a route whose response shape changed cannot have a stale schema
committed alongside it.

    python scripts/export_openapi.py [--check]

`--check` regenerates and fails if the committed file differs, which is how CI catches a
schema that was changed without being exported.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.api.app import create_app

TARGET = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


def schema() -> str:
    # sort_keys so the file is stable: without it an unrelated route addition reorders
    # unrelated keys and the diff stops being readable.
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed file differs")
    args = parser.parse_args()

    generated = schema()

    if args.check:
        if not TARGET.exists():
            print(f"{TARGET} is missing; run: python scripts/export_openapi.py")
            return 1
        if TARGET.read_text(encoding="utf-8") != generated:
            print(f"{TARGET} is out of date; run: python scripts/export_openapi.py")
            return 1
        print(f"{TARGET.name} is up to date")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(generated, encoding="utf-8")
    paths = len(json.loads(generated)["paths"])
    print(f"wrote {TARGET} ({paths} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
