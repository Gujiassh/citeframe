from __future__ import annotations

import os
import shutil
from pathlib import Path


def find_bash(repository_root: Path) -> str | None:
    """Return a real Bash executable without selecting the Windows WSL launcher stub."""
    candidates: list[Path] = []
    if os.name == "nt":
        candidates.extend(
            (
                repository_root / ".local-runtime/portable-git/bin/bash.exe",
                Path(os.environ.get("ProgramFiles", "C:/Program Files"))
                / "Git/bin/bash.exe",
            )
        )

    discovered = shutil.which("bash")
    if discovered is not None:
        discovered_path = Path(discovered)
        windows_stub = (
            Path(os.environ.get("WINDIR", "C:/Windows")) / "System32/bash.exe"
        )
        if os.name != "nt" or discovered_path.resolve() != windows_stub.resolve():
            candidates.append(discovered_path)

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None
