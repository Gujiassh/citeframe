from __future__ import annotations

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _environment(path: Path) -> dict[str, str]:
    environment: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        environment[key] = value
    return environment


def test_web_local_environment_template_covers_bff_auth_boundary() -> None:
    template = REPOSITORY_ROOT / "apps/web/.env.example"

    assert template.is_file()
    assert {
        "AI_PDF_API_BASE_URL",
        "AI_PDF_API_INTERNAL_TOKEN",
        "AI_PDF_SESSION_SECRET",
    } <= _environment(template).keys()


def test_local_profiles_can_start_authenticated_web_flow() -> None:
    web_environment = _environment(REPOSITORY_ROOT / "apps/web/.env.example")

    for profile_name in ("preview", "accept"):
        profile_environment = _environment(
            REPOSITORY_ROOT / f"infra/env/{profile_name}.env.example"
        )
        assert "AI_PDF_API_INTERNAL_TOKEN" in profile_environment
        assert (
            profile_environment["AI_PDF_API_INTERNAL_TOKEN"]
            == web_environment["AI_PDF_API_INTERNAL_TOKEN"]
        )

    preview_environment = _environment(
        REPOSITORY_ROOT / "infra/env/preview.env.example"
    )
    accept_environment = _environment(REPOSITORY_ROOT / "infra/env/accept.env.example")
    assert "AI_PDF_SESSION_SECRET" not in preview_environment
    assert "AI_PDF_SESSION_SECRET" in accept_environment


def test_windows_native_worker_command_targets_executable_module() -> None:
    guide = (
        REPOSITORY_ROOT / "docs/architecture/windows-local-development.md"
    ).read_text(encoding="utf-8")

    assert "python -m ai_pdf_worker.main" in guide
    assert re.search(r"python -m ai_pdf_worker(?:\s|$)", guide) is None
    assert (REPOSITORY_ROOT / "apps/worker/src/ai_pdf_worker/main.py").is_file()


def test_windows_native_guide_uses_the_downloaded_minio_binary_and_loads_preview() -> (
    None
):
    guide = (
        REPOSITORY_ROOT / "docs/architecture/windows-local-development.md"
    ).read_text(encoding="utf-8")

    assert "$runtime/downloads/minio.exe" in guide
    assert "$runtime/minio/minio.exe" not in guide
    assert "$env:MINIO_ENDPOINT" not in guide
    assert "Resolve-Path infra/env/preview.local.env" in guide
    assert 'Set-Item "Env:$k" $v' in guide
    assert "start Web in one terminal without importing the backend profile" in guide
