"""Architecture guard: core/ is hexagonal — stdlib-only, no vendor or delivery imports."""

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_ROOT = REPO_ROOT / "core"

FORBIDDEN_ROOTS = {"providers", "api", "cli", "web", "persistence", "evaluation", "config"}
FORBIDDEN_VENDORS = {
    "anthropic",
    "httpx",
    "fastapi",
    "pydantic",
    "pydantic_settings",
    "typer",
    "rich",
}
PROJECT_PACKAGES = {"core"}
THIRD_PARTY_EXAMPLES = sorted(FORBIDDEN_VENDORS)[:3]


def _iter_core_modules() -> list[Path]:
    if not CORE_ROOT.exists():
        return []
    return sorted(CORE_ROOT.rglob("*.py"))


def _top_level_module(node: ast.AST) -> str | None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            return alias.name.split(".")[0]
    if isinstance(node, ast.ImportFrom):
        if node.level > 0:
            return None  # relative import inside the package itself
        return (node.module or "").split(".")[0]
    return None


def _imported_top_level_modules(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        module = _top_level_module(node)
        if module is not None:
            found.add(module)
    return found


def test_core_tree_exists() -> None:
    assert CORE_ROOT.is_dir(), "core/ package must exist"
    assert list(_iter_core_modules()), "core/ contains no modules"


def test_core_imports_are_resolvable_and_inward_only() -> None:
    offenders: list[str] = []
    for path in _iter_core_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imported_top_level_modules(tree):
            if module in FORBIDDEN_ROOTS or module in FORBIDDEN_VENDORS:
                offenders.append(f"{path.relative_to(REPO_ROOT)} imports '{module}'")
    assert not offenders, (
        "core/ must not import delivery or vendor modules (hexagonal rule); found:\n"
        + "\n".join(offenders)
    )


def test_core_uses_no_third_party_imports() -> None:
    offenders: list[str] = []
    for path in _iter_core_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imported_top_level_modules(tree):
            if module in sys.stdlib_module_names or module in PROJECT_PACKAGES:
                continue
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports third-party '{module}'")
    assert not offenders, (
        "core/ must be stdlib-only; "
        f"e.g. these must move behind ports: {', '.join(THIRD_PARTY_EXAMPLES)}"
    )
