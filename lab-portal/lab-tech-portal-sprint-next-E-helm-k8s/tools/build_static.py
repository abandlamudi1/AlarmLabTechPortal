"""Build consolidated static assets for deployment.

Generates a combined CSS bundle at static/build/portal.css so nginx or Flask can
serve a single stylesheet in production.
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC_ROOT = ROOT / "static"
BUILD_DIR = STATIC_ROOT / "build"

CSS_SOURCES = [
    STATIC_ROOT / "style.css",
    ROOT / "tools" / "inventory" / "static" / "style.css",
    ROOT / "tools" / "rf_chamber" / "static" / "style.css",
]


def build_css_bundle() -> pathlib.Path:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    bundle_path = BUILD_DIR / "portal.css"
    parts = []
    for css_path in CSS_SOURCES:
        if not css_path.exists():
            continue
        parts.append(f"/* >>> {css_path.relative_to(ROOT)} */\n")
        parts.append(css_path.read_text(encoding="utf-8"))
        parts.append("\n\n")
    bundle_path.write_text("".join(parts), encoding="utf-8")
    return bundle_path


def main() -> None:
    bundle_path = build_css_bundle()
    print(f"Wrote CSS bundle to {bundle_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
