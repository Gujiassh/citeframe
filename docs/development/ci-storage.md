# CI object storage

The Conflict and Research service workflows use
[`ci_minio.py`](../../infra/testing/ci_minio.py) to select storage images. R800 enables
this selection with `--ci-minio-assembly`. The helper first pulls both original
MinIO and mc digest-pinned images. Successful pulls retain those image identities.
If either pull fails or exceeds its 120-second timeout, it records that image as unavailable
and assembles local Linux amd64 images from fixed official binaries.

## Deployment registry origins

The Web Dockerfile uses official `docker.io/library/node:22-bookworm-slim` for both
stages, pinned to `sha256:f86be15afa9a8277608e141ce2a8aa55d3d9c40845921b8511f4fb7897be2554`.
Deployment Compose uses official `docker.io/library/redis:7.4.9`, pinned to
`sha256:d3be87a1060455213a204d2b0a7f04d45d19a16a98e85b3c37b7c33b5f0c489e`.
These manifests retain the digests previously addressed through the ECR mirror.

The immutable historical R800 checkout retains its ECR Redis reference. Only its
CI invocation enables `--ci-redis-origin-alias`: the harness requires that exact
historical tag/digest, pulls the official Docker Hub reference and verifies its
RepoDigest and image ID. It writes `redis-origin-alias.json` and adds only the
Redis image reference to the generated Compose override. The same override also
carries the MinIO image when assembly is needed. Commands, volumes, healthchecks
and source files retain their existing definitions. This does not demonstrate
availability of the historical ECR origin. A failed pull or identity mismatch fails
the run; there is no alternate tag or digest selection.

## Fixed artifacts

| Binary | Release | SHA-256 |
| --- | --- | --- |
| MinIO | `RELEASE.2025-09-07T16-13-09Z` | `7c5bd8512c6e966455b1d198209358b2d191c77a83ab377c4073281065fb855f` |
| mc | `RELEASE.2025-08-13T08-35-41Z` | `01f866e9c5f9b87c2b09116fa5d7c06695b106242d829a8bb32990c00312e891` |

The official [MinIO release assets](https://github.com/minio/minio/releases/expanded_assets/RELEASE.2025-09-07T16-13-09Z)
and [mc release assets](https://github.com/minio/mc/releases/expanded_assets/RELEASE.2025-08-13T08-35-41Z)
publish the binaries and digests. The helper verifies each download and the binary
inside its assembled container, then checks the reported release version.

Assembly uses
`python:3.12-slim@sha256:c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28`.
It installs curl and CA certificates from Debian; these packages are not separately
version-pinned. The images include upstream AGPL license files and notices linking
[MinIO source](https://github.com/minio/minio/tree/RELEASE.2025-09-07T16-13-09Z)
and [mc source](https://github.com/minio/mc/tree/RELEASE.2025-08-13T08-35-41Z).
Images remain local to the runner.

## Runtime checks and provenance

For substituted assemblies, the helper requires the production curl healthcheck and a
non-root mc mirror backup/restore round trip with byte comparison before emitting a successful manifest.
Checksum, build, version, health, and mc probe failures fail the command. Every helper
container has an explicit client or server name. Cleanup attempts removal of both names
and checks that neither remains; an unverified removal also fails assembly. Cleanup
errors are recorded separately and preserve the primary failure.

Command failures and timeouts retain sanitized stdout/stderr bounded to 16 KiB each
plus a truncation marker, with stage, exit-code, and timeout metadata. Probe credentials
are passed through the subprocess environment and redacted from diagnostics. A failed
assembly emits `assembly-failure.json`; it emits no successful `assembly.json`.

`assembly.json` records original pull results, image IDs, fixed artifacts, helper-source
identity, and assembly file hashes. Workflow artifacts retain manifests, bounded logs,
Dockerfile, licenses, and NOTICE. Images and downloaded binaries are not uploaded.

R800 applies substituted images through a generated Compose override and the existing
`MINIO_MC_IMAGE` environment override. Source identity, product-delta admission,
scenario, backup/restore, new-task, cleanup, and serial negative controls remain active.
Substituted runs record `dependencySubstitution: true` and
`defaultRegistryPassed: false`. Historical comparisons with substituted dependencies
retain that attribution. Runs using original images retain the default-image checks.
A final hosted gate requires all three baseline, positive, and serial manifests to exist
and match on exact server/client image IDs, original/substituted mode, helper source,
base, artifact/source pins, and assembly file hashes. Different images or packaging
fail this gate even when release versions match.

## Production-default coverage

A substituted run exercises the recorded application source with the assembled storage
dependency. It leaves production Compose and backup/restore defaults unchanged.
It does not establish availability of the original pinned registry images, their exact
container packaging or entrypoints, or successful backup/restore with the unoverridden
production mc image. Those claims require a separate run using the original images.
