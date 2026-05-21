"""Export the OpenAPI spec for the /api/v1/ blueprint to docs/api-spec.yaml.

Usage::

    SWAGGER_ENABLED=1 python scripts/export_openapi_spec.py

The script sets SWAGGER_ENABLED so flasgger mounts the spec endpoint even
outside debug mode.  The exported YAML is written to docs/api-spec.yaml
relative to the repo root.

Slice H, Issue #53.
"""
from __future__ import annotations

import json
import os
import sys
import yaml

# Ensure repo root is on the path regardless of where the script is invoked.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Enable Swagger before importing app so flasgger registers correctly.
os.environ.setdefault("SWAGGER_ENABLED", "1")
# Disable Redis/Okta checks that would fail in CI.
os.environ.setdefault("TESTING", "1")

from app import app  # noqa: E402 — must come after env vars are set

_OUT_PATH = os.path.join(_REPO_ROOT, "docs", "api-spec.yaml")


def main() -> None:
    app.config["SWAGGER_ENABLED"] = True
    app.config["TESTING"] = True
    app.config["LOGIN_DISABLED"] = True

    with app.test_client() as client:
        resp = client.get("/api/v1/docs/openapi.json")
        if resp.status_code != 200:
            print(
                f"ERROR: /api/v1/docs/openapi.json returned HTTP {resp.status_code}",
                file=sys.stderr,
            )
            sys.exit(1)
        spec = resp.get_json()

    os.makedirs(os.path.dirname(_OUT_PATH), exist_ok=True)
    with open(_OUT_PATH, "w", encoding="utf-8") as fh:
        yaml.dump(spec, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"OpenAPI spec written to {_OUT_PATH}")


if __name__ == "__main__":
    main()
