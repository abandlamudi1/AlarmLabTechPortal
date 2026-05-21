"""CI gate: tool modules must not call init_db/_ensure_db at module level.

This test uses AST inspection so it runs without touching the filesystem
and is not affected by whether other test modules have already imported
the tool modules.
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

TOOL_MODULES = [
    "tools/inventory/inventory_app.py",
    "tools/rf_chamber/rf_chamber_app.py",
    "tools/print_requests/db.py",
    "tools/checkout/db.py",
    "tools/system_locator/db.py",
]

_FORBIDDEN = {"init_db", "_init_db", "_ensure_db", "ensure_db"}


def _module_level_calls(src: str) -> list[tuple[int, str]]:
    """Return (lineno, name) for bare function calls at module top level."""
    tree = ast.parse(src)
    hits = []
    for node in tree.body:
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
            continue
        call = node.value
        if isinstance(call.func, ast.Name):
            name = call.func.id
        elif isinstance(call.func, ast.Attribute):
            name = call.func.attr
        else:
            continue
        if name in _FORBIDDEN:
            hits.append((node.lineno, name))
    return hits


def test_no_module_level_db_init():
    violations = []
    for rel in TOOL_MODULES:
        path = REPO_ROOT / rel
        hits = _module_level_calls(path.read_text())
        for lineno, name in hits:
            violations.append(f"{rel}:{lineno}: bare call to {name}()")

    assert not violations, (
        "Module-level DB init calls found — move them into init_app():\n"
        + "\n".join(violations)
    )
