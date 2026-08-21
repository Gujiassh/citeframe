from __future__ import annotations

import ast
import hashlib
import re
from collections.abc import Iterable, Iterator
from pathlib import Path

from ai_pdf_worker.r803_evaluation_contract import R803EvaluationError, file_sha256

EVALUATOR_CLOSURE_STRATEGY = "recursive_ast_import_closure"
EVALUATOR_CLOSURE_ROOTS: tuple[str, ...] = (
    "ai_pdf_worker.r803_evaluation_campaign",
)

# Repository-local import roots only. Third-party/stdlib imports are ignored.
_PACKAGE_SOURCE_ROOTS: dict[str, str] = {
    "ai_pdf_worker": "apps/worker/src",
    "ai_pdf_api": "apps/api/src",
    "citeframe_contracts": "packages/backend-contracts/src",
    "citeframe_persistence": "packages/backend-persistence/src",
}

_SAFE_RELATIVE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def module_file_sha256(repo_root: Path, relative: str) -> str:
    path = repo_root / relative
    if not path.is_file():
        raise R803EvaluationError(f"missing_closure_module:{relative}")
    return file_sha256(path)


def scorer_implementation_sha256(repo_root: Path) -> str:
    return module_file_sha256(
        repo_root,
        "apps/worker/src/ai_pdf_worker/r803_evaluation_scorer_v2.py",
    )


def _is_type_checking_test(test: ast.AST) -> bool:
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _walk_runtime_nodes(node: ast.AST) -> Iterator[ast.AST]:
    """Walk AST nodes, skipping only the body of `if TYPE_CHECKING` blocks."""
    yield node
    if isinstance(node, ast.If) and _is_type_checking_test(node.test):
        for child in node.orelse:
            yield from _walk_runtime_nodes(child)
        return
    for child in ast.iter_child_nodes(node):
        yield from _walk_runtime_nodes(child)


def _source_root_for_top_level(repo_root: Path, top_level: str) -> Path | None:
    relative = _PACKAGE_SOURCE_ROOTS.get(top_level)
    if relative is None:
        return None
    return (repo_root / relative).resolve()


def _module_candidates(repo_root: Path, module_name: str) -> list[Path]:
    top = module_name.split(".", 1)[0]
    source_root = _source_root_for_top_level(repo_root, top)
    if source_root is None:
        return []
    parts = module_name.split(".")
    base = source_root.joinpath(*parts)
    return [base.with_suffix(".py"), base / "__init__.py"]


def _resolve_module_path(repo_root: Path, module_name: str) -> Path | None:
    """Resolve a local module to a concrete file or namespace-package directory.

    Returns:
    - module .py file
    - package __init__.py
    - namespace package directory (no __init__.py) when that directory exists
    Raises missing_closure_module when no local module/package exists.
    """
    top = module_name.split(".", 1)[0]
    if top not in _PACKAGE_SOURCE_ROOTS:
        return None
    for candidate in _module_candidates(repo_root, module_name):
        if candidate.is_file() and not candidate.is_symlink():
            return candidate.resolve()
    # Namespace packages are valid ImportFrom bases (e.g. ai_pdf_api.core).
    source_root = _source_root_for_top_level(repo_root, top)
    if source_root is None:
        return None
    namespace_dir = source_root.joinpath(*module_name.split("."))
    if namespace_dir.is_dir() and not namespace_dir.is_symlink():
        return namespace_dir.resolve()
    raise R803EvaluationError(f"missing_closure_module:{module_name}")


def _path_to_module_name(repo_root: Path, path: Path) -> str:
    resolved = path.resolve()
    for relative in _PACKAGE_SOURCE_ROOTS.values():
        base = (repo_root / relative).resolve()
        try:
            rel = resolved.relative_to(base)
        except ValueError:
            continue
        parts = list(rel.parts)
        if not parts:
            raise R803EvaluationError(f"invalid_closure_module_path:{path}")
        if resolved.is_dir():
            # Namespace package directory.
            return ".".join(parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        elif parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        else:
            raise R803EvaluationError(f"invalid_closure_module_path:{path}")
        if not parts:
            raise R803EvaluationError(f"invalid_closure_module_path:{path}")
        return ".".join(parts)
    raise R803EvaluationError(f"closure_path_outside_package_roots:{path}")


def _repo_relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as error:
        raise R803EvaluationError(f"closure_path_outside_repo:{path}") from error


def _relative_import_base(module_name: str, *, is_package: bool, level: int) -> list[str]:
    parts = module_name.split(".")
    if not is_package:
        parts = parts[:-1]
    if level < 1:
        raise R803EvaluationError(f"invalid_relative_import_level:{level}")
    drop = level - 1
    if drop > len(parts):
        raise R803EvaluationError(
            f"relative_import_escapes_package:{module_name}:level={level}"
        )
    if drop:
        parts = parts[: len(parts) - drop]
    return parts


def _parse_module_source(path: Path) -> ast.AST:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as error:
        raise R803EvaluationError(f"closure_module_unreadable:{path}") from error
    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError as error:
        raise R803EvaluationError(f"closure_module_syntax_error:{path}") from error


def _import_targets_from_node(
    *,
    current_module: str,
    is_package: bool,
    node: ast.AST,
) -> list[tuple[str, str]]:
    """Extract import targets with kind preserved.

    Returns (kind, module_name) pairs:
    - required: ast.Import aliases and ImportFrom module bases must resolve
    - optional_attr: ImportFrom imported names may be a submodule or attribute
    """
    targets: list[tuple[str, str]] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name:
                targets.append(("required", alias.name))
        return targets
    if not isinstance(node, ast.ImportFrom):
        return targets

    base_name: str | None = None
    if node.level and node.level > 0:
        base_parts = _relative_import_base(
            current_module,
            is_package=is_package,
            level=node.level,
        )
        if node.module:
            base_parts = [*base_parts, *node.module.split(".")]
        if base_parts:
            base_name = ".".join(base_parts)
    elif node.module:
        base_name = node.module

    if base_name:
        # ImportFrom base is a required local module/package when in-scope.
        targets.append(("required", base_name))
        for alias in node.names:
            if alias.name == "*":
                continue
            targets.append(("optional_attr", f"{base_name}.{alias.name}"))
    return targets


def _is_local_package(module_name: str) -> bool:
    return module_name.split(".", 1)[0] in _PACKAGE_SOURCE_ROOTS


def _resolve_import_target(repo_root: Path, kind: str, module_name: str) -> list[str]:
    """Resolve one import target according to its kind.

    Required targets must exist under repo-local package roots. Optional
    ImportFrom attribute names enqueue a submodule only when that submodule
    actually exists; otherwise they are treated as attributes and ignored.
    """
    if not _is_local_package(module_name):
        return []
    if kind == "required":
        _resolve_module_path(repo_root, module_name)
        return [module_name]
    if kind != "optional_attr":
        raise R803EvaluationError(f"unknown_import_target_kind:{kind}")
    # Optional attribute/submodule: only enqueue when the child module exists.
    try:
        _resolve_module_path(repo_root, module_name)
    except R803EvaluationError as error:
        message = str(error)
        if message.startswith("missing_closure_module:"):
            return []
        raise
    return [module_name]


def _ancestor_package_modules(module_name: str) -> list[str]:
    """Return existing ancestor package names for a fully-qualified module.

    For ``a.b.c.d``, yields ``a``, ``a.b``, ``a.b.c`` in root-to-leaf order.
    """
    parts = module_name.split(".")
    if len(parts) <= 1:
        return []
    return [".".join(parts[:index]) for index in range(1, len(parts))]


def compute_evaluator_closure(
    repo_root: Path,
    *,
    roots: tuple[str, ...] | list[str] | None = None,
) -> dict[str, object]:
    """Deterministic recursive repository-local Python import closure.

    Starts at EVALUATOR_CLOSURE_ROOTS (or explicit roots for isolated tests),
    walks runtime AST imports (including function-local imports), skips only
    `if TYPE_CHECKING` bodies, resolves repository-local `ai_pdf_worker.*`,
    `ai_pdf_api.*`, `citeframe_contracts.*`, and `citeframe_persistence.*` under
    fixed source roots, and fails closed on missing/unreadable/
    syntax-invalid required modules.

    For every resolved module, every existing ancestor package ``__init__.py``
    is also enqueued so package initializer imports are hashed and walked.
    Namespace package directories (no ``__init__.py``) remain unhashed.
    """
    repo_root = repo_root.resolve()
    root_modules = tuple(roots) if roots is not None else EVALUATOR_CLOSURE_ROOTS
    pending: list[str] = list(root_modules)
    seen_modules: set[str] = set()
    module_hashes: dict[str, str] = {}

    while pending:
        module_name = pending.pop(0)
        if module_name in seen_modules:
            continue
        path = _resolve_module_path(repo_root, module_name)
        if path is None:
            continue
        seen_modules.add(module_name)
        # Prefer the resolved module identity from path (package vs module file).
        resolved_name = _path_to_module_name(repo_root, path)
        seen_modules.add(resolved_name)
        # Enqueue existing ancestor package initializers for every resolved module.
        for ancestor in _ancestor_package_modules(resolved_name):
            if ancestor in seen_modules:
                continue
            ancestor_path = _resolve_module_path(repo_root, ancestor)
            if ancestor_path is None:
                continue
            if ancestor_path.is_file() and ancestor_path.name == "__init__.py":
                pending.append(ancestor)
        if path.is_dir():
            # Namespace package: valid required import base, no file to hash/walk.
            continue
        relative = _repo_relative(repo_root, path)
        if relative in module_hashes:
            continue
        module_hashes[relative] = file_sha256(path)
        tree = _parse_module_source(path)
        is_package = path.name == "__init__.py"
        for node in _walk_runtime_nodes(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for kind, imported in _import_targets_from_node(
                current_module=resolved_name,
                is_package=is_package,
                node=node,
            ):
                for target in _resolve_import_target(repo_root, kind, imported):
                    if target not in seen_modules:
                        pending.append(target)

    if not module_hashes:
        raise R803EvaluationError("empty_evaluator_closure")
    material = "\n".join(
        f"{path}:{digest}" for path, digest in sorted(module_hashes.items())
    )
    return {
        "strategy": EVALUATOR_CLOSURE_STRATEGY,
        "roots": list(root_modules),
        "sourceRoots": dict(_PACKAGE_SOURCE_ROOTS),
        "modules": dict(sorted(module_hashes.items())),
        "closureSha256": hashlib.sha256(material.encode("utf-8")).hexdigest(),
    }


def assert_safe_relative_path(name: str) -> None:
    if not name or name.startswith("/") or name.endswith("/"):
        raise R803EvaluationError(f"unsafe_checksum_path:{name}")
    if name == "SHA256SUMS" or name.startswith("SHA256SUMS/"):
        raise R803EvaluationError(f"unsafe_checksum_path:{name}")
    if "\\" in name or "\0" in name:
        raise R803EvaluationError(f"unsafe_checksum_path:{name}")
    if any(part in {"", ".", ".."} for part in name.split("/")):
        raise R803EvaluationError(f"unsafe_checksum_path:{name}")
    if not _SAFE_RELATIVE.match(name):
        raise R803EvaluationError(f"unsafe_checksum_path:{name}")


def _assert_round_root_boundary(root: Path) -> None:
    if root.is_symlink():
        raise R803EvaluationError("round_symlink_forbidden:.")
    if not root.is_dir():
        raise R803EvaluationError("round_directory_missing")


def list_regular_files_relative(
    root: Path,
    *,
    include_checksum_manifest: bool = False,
) -> list[str]:
    _assert_round_root_boundary(root)
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise R803EvaluationError(f"round_symlink_forbidden:{relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise R803EvaluationError(f"round_non_regular_file:{relative}")
        if relative == "SHA256SUMS":
            if include_checksum_manifest:
                found.append(relative)
            continue
        assert_safe_relative_path(relative)
        found.append(relative)
    return found


def write_checksums(output_dir: Path, hashes: dict[str, str]) -> None:
    _assert_round_root_boundary(output_dir)
    if not hashes:
        raise R803EvaluationError("empty_checksum_set")
    names = list(hashes)
    if len(names) != len(set(names)):
        raise R803EvaluationError("duplicate_checksum_name")
    for name in names:
        assert_safe_relative_path(name)
        if name == "SHA256SUMS":
            raise R803EvaluationError("checksums_must_not_list_self")
    # Closure: every regular file except SHA256SUMS must be listed exactly once.
    on_disk = list_regular_files_relative(output_dir)
    expected = sorted(hashes)
    if on_disk != expected:
        missing = sorted(set(expected) - set(on_disk))
        extra = sorted(set(on_disk) - set(expected))
        if missing:
            raise R803EvaluationError(f"checksum_targets_missing_on_disk:{','.join(missing)}")
        if extra:
            raise R803EvaluationError(f"unlisted_round_files:{','.join(extra)}")
        raise R803EvaluationError("checksum_target_set_mismatch")
    for name, digest in hashes.items():
        actual = file_sha256(output_dir / name)
        if actual != digest:
            raise R803EvaluationError(f"checksum_write_drift:{name}")
    checksum = "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items()))
    path = output_dir / "SHA256SUMS"
    with path.open("x", encoding="utf-8") as target:
        target.write(checksum)


def verify_checksums_exact(output_dir: Path) -> dict[str, str]:
    _assert_round_root_boundary(output_dir)
    sums_path = output_dir / "SHA256SUMS"
    if not sums_path.is_file():
        raise R803EvaluationError("missing_round_checksums")
    if sums_path.is_symlink():
        raise R803EvaluationError("round_symlink_forbidden:SHA256SUMS")
    hashes: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2:
            raise R803EvaluationError("malformed_checksum_line")
        digest, name = parts
        if name in hashes:
            raise R803EvaluationError(f"duplicate_checksum_name:{name}")
        assert_safe_relative_path(name)
        path = output_dir / name
        if path.is_symlink():
            raise R803EvaluationError(f"round_symlink_forbidden:{name}")
        if not path.is_file():
            raise R803EvaluationError(f"missing_checksum_target:{name}")
        actual = file_sha256(path)
        if actual != digest:
            raise R803EvaluationError(f"checksum_drift:{name}")
        hashes[name] = digest
    on_disk = list_regular_files_relative(output_dir)
    if sorted(hashes) != on_disk:
        missing = sorted(set(on_disk) - set(hashes))
        extra_listed = sorted(set(hashes) - set(on_disk))
        if missing:
            raise R803EvaluationError(f"unlisted_round_files:{','.join(missing)}")
        if extra_listed:
            raise R803EvaluationError(f"missing_checksum_target:{','.join(extra_listed)}")
        raise R803EvaluationError("checksum_target_set_mismatch")
    return hashes


def sanitize_logical_call_filename(logical_call_key: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", logical_call_key).strip("._-")
    if not cleaned:
        cleaned = "call"
    return cleaned[:120]


def iter_nonempty_round_dirs(campaign_dir: Path, planned_rounds: int) -> Iterable[tuple[int, Path]]:
    for index in range(1, planned_rounds + 1):
        path = campaign_dir / f"round-{index:02d}"
        if path.exists() and any(path.iterdir()):
            yield index, path
