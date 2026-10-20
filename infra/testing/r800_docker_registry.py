"""Fixed Redis registry-origin alias for the immutable historical R800 checkout."""
from __future__ import annotations

import re
from pathlib import Path

REDIS_DIGEST = "sha256:d3be87a1060455213a204d2b0a7f04d45d19a16a98e85b3c37b7c33b5f0c489e"
HISTORICAL_REDIS_IMAGE = "public.ecr.aws/docker/library/redis:7.4.9@" + REDIS_DIGEST
OFFICIAL_REDIS_IMAGE = "docker.io/library/redis:7.4.9@" + REDIS_DIGEST


def historical_redis_source(deploy: str) -> str:
    matches = re.findall(r"^  redis:\n    image: ([^\n]+)$", deploy, re.MULTILINE)
    if matches != [HISTORICAL_REDIS_IMAGE]:
        raise ValueError("Historical Redis source must retain the exact ECR tag and digest")
    return matches[0]


def redis_alias_provenance(source_image: str, inspection: dict) -> dict:
    if source_image != HISTORICAL_REDIS_IMAGE:
        raise ValueError("Unexpected historical Redis source")
    digests = inspection.get("RepoDigests")
    expected = {"redis@" + REDIS_DIGEST, "docker.io/library/redis@" + REDIS_DIGEST}
    if (not isinstance(digests, list) or not all(isinstance(item, str) for item in digests)
            or not expected.intersection(digests)):
        raise ValueError("Pulled official Redis RepoDigest does not match the historical pin")
    image_id = inspection.get("Id")
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("Missing pulled Redis image identity")
    return {"sourceImage": source_image, "aliasImage": OFFICIAL_REDIS_IMAGE,
            "manifestDigest": REDIS_DIGEST, "imageId": image_id, "repoDigests": digests,
            "scope": "CI-only historical registry origin; same immutable Redis manifest"}


def configure_ci_override(source_override: Path, output: Path, compose: list[str],
                          env: dict[str, str], *, redis_origin_alias: bool = False,
                          minio_image: str | None = None) -> None:
    if not redis_origin_alias and minio_image is None:
        return
    text = source_override.read_text()
    if len(re.findall(r"^services:$", text, re.MULTILINE)) != 1:
        raise ValueError("Expected the existing R800 services override")
    additions = []
    if redis_origin_alias:
        additions.append(("redis", OFFICIAL_REDIS_IMAGE))
    if minio_image is not None:
        additions.append(("minio", minio_image))
    for service, image in additions:
        if re.search(r"^  " + service + r":$", text, re.MULTILINE):
            raise ValueError("R800 override already defines " + service)
        text += "\n  " + service + ":\n    image: " + image + "\n"
    override = output / "compose.ci.yml"
    override.write_text(text)
    env["COMPOSE_OVERRIDE_FILE"] = str(override)
    compose[-1] = str(override)
