"""Lazy callable reference resolution.

References are only resolved at execution time (never at construction or
serialization time). Supported forms:

- ``"pkg.mod:function"`` — importable module + dotted attribute path
- ``"./tasks/hello.py:main"`` — path relative to ``project_root`` (default cwd)
- ``"D:/proj/tasks/hello.py:main"`` — absolute path
- ``"__main__:function"`` — same-process lookup (fragile; documented)

Failures raise :class:`RefResolveError` with the list of attempts, so users
can diagnose why a reference did not resolve.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path


class RefResolveError(LookupError):
    """Raised when a string reference cannot be resolved to an object."""

    def __init__(self, ref: str, attempts: list[str]) -> None:
        self.ref = ref
        self.attempts = attempts
        message = f"Could not resolve reference {ref!r}."
        if attempts:
            message += " Attempted: " + "; ".join(attempts)
        super().__init__(message)


def _load_module_file(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def resolve_ref(
    ref: str,
    project_root: str | Path | None = None,
) -> object:
    """Resolve a ``"module:object"`` reference to the target object.

    Args:
        ref: reference string (see module docstring for supported forms).
        project_root: base directory for relative path references.

    Raises:
        RefResolveError: if the reference cannot be resolved.
    """
    if not isinstance(ref, str):
        raise TypeError("References must be strings")
    if ":" not in ref:
        raise RefResolveError(
            ref, ["invalid format: expected 'module:object' (missing ':')"]
        )

    # Windows drive letters (e.g. "D:/path/file.py:func") contain a colon
    # that is part of the path, not the separator; split at the last colon
    # in that case.
    if len(ref) > 2 and ref[0].isalpha() and ref[1] == ":" and ref[2] in "/\\":
        modulename, rest = ref.rsplit(":", 1)
    else:
        modulename, rest = ref.split(":", 1)
    root = Path(project_root) if project_root is not None else Path.cwd()
    attempts: list[str] = []
    module = None

    # 1) Filesystem paths (absolute, ./ or ../ relative, or bare path under root)
    candidates: list[Path] = []
    raw = Path(modulename)
    if raw.is_absolute():
        candidates.append(raw)
    elif modulename.startswith(("./", "../")):
        candidates.append((root / modulename).resolve())
    else:
        candidates.append(root / modulename)
        if not raw.suffix:
            candidates.append(root / f"{modulename}.py")
    for candidate in candidates:
        attempts.append(f"file {candidate}")
        if candidate.is_file():
            module = _load_module_file(candidate.resolve(), candidate.stem)
            break

    # 2) __main__ (same process only)
    if module is None and modulename == "__main__":
        attempts.append("__main__ (same process only)")
        module = sys.modules.get("__main__")

    # 3) Importable module via sys.path
    if module is None:
        attempts.append(f"import {modulename!r} via sys.path")
        try:
            module = importlib.import_module(modulename)
        except ImportError:
            module = None

    if module is None:
        raise RefResolveError(ref, attempts)

    obj = module
    try:
        for name in rest.split("."):
            obj = getattr(obj, name)
    except AttributeError:
        module_name = getattr(module, "__name__", modulename)
        attempts.append(f"attribute {rest!r} on module {module_name!r}")
        raise RefResolveError(ref, attempts)
    return obj
