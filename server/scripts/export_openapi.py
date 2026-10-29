"""Export the FastAPI OpenAPI document used to generate the frontend types.

The frontend never talks to Python directly: ``server/openapi.json`` is the
committed contract between the backend DTOs and ``front/src/types/api.generated.ts``.
Run it through ``pnpm generate:api`` from the repository root after changing a
request or response model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = SERVER_ROOT / "src"

# The backend runs with ``src`` on its path (uvicorn --app-dir src).
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Import after the sys.path setup above so the script also works from the
# repository root or from a checkout without an editable install.
from main import app

DEFAULT_OUTPUT = SERVER_ROOT / "openapi.json"


def render_openapi() -> str:
    """Return the application's OpenAPI document as formatted JSON."""
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def export_openapi(output: Path) -> Path:
    """Write the application's OpenAPI document to ``output``."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_openapi(), encoding="utf-8")
    return output


def check_openapi(output: Path) -> bool:
    """Return whether ``output`` matches the current application schema."""
    if not output.exists():
        return False
    return output.read_text(encoding="utf-8") == render_openapi()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the output file is out of date instead of rewriting it",
    )
    args = parser.parse_args()

    if args.check:
        if not check_openapi(args.output):
            print(
                f"{args.output} is out of date. Run `pnpm generate:api`.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        print(f"{args.output} is up to date")
        return

    output = export_openapi(args.output)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
