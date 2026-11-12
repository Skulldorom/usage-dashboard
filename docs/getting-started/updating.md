# Updating

Use the upgrade procedure for the way Usage Dashboard was installed:

- [Docker Compose](/getting-started/docker-compose#upgrade)
- [Native Linux](/getting-started/native-linux#upgrade)
- [Standalone containers](/getting-started/standalone-containers#upgrade)

Updates are shipped as release tags and matching images on GitHub Container Registry.

## Update to the latest release

```bash
docker compose pull
docker compose up -d
```

Compose recreates any containers whose image changed. Database migrations run
automatically when the backend starts.

## Pin a version

By default the stack tracks the `latest` image tag. To pin a specific release,
set `IMAGE_TAG` in `.env`:

```bash
IMAGE_TAG=v1.2.0
```

## Custom image references

If you publish under a different registry or name, override the full image
references instead of the tag:

```bash
BACKEND_IMAGE=ghcr.io/your-org/usage-dashboard-backend:latest
FRONTEND_IMAGE=ghcr.io/your-org/usage-dashboard-frontend:latest
```

See the [environment variable reference](/configuration/environment) for all
image-related settings.

The commands on this page apply only to Docker Compose. Native and standalone
container deployments must follow their linked ordering so migrations complete
before the new backend serves traffic.


## Update notifications

After an admin session is established, the sidebar shows the installed backend version and checks GitHub's published stable release about every six hours. It only offers an update when a newer valid semantic-version GitHub Release exists. Drafts, prereleases, malformed tags, and tags without a matching release page are ignored.

The check is informational: it never pulls images, restarts containers, or runs migrations. Select **View release notes** to open the verified GitHub release page. Dismissing a notice stores that release tag only in the browser; the next release is shown again.

Released container images receive `APP_VERSION` from their `v*` release tag. Native Linux installs run `sh scripts/build-release.sh` from a clean release checkout. This builds the frontend with the exact tag and writes `deploy/version.env`, loaded by the supplied backend systemd unit. Run this script after each upgrade; no manual version constant is required. Without Git at runtime, the built frontend and generated environment file retain the version. Default-branch builds use a SHA-bearing development prerelease; local builds without metadata use `unknown`. The UI compares the frontend build metadata with the backend version; mismatched or unknown artifact versions suppress update claims and show separate artifact labels. Use the same pinned tag for both standalone images and diagnose a mismatch with the image tag and backend `APP_VERSION`.

The backend caches successful GitHub metadata in memory for six hours and uses conditional ETag revalidation. GitHub is optional: outages, rate limits, or invalid responses do not affect dashboard operation; the last trusted result may be reported as stale and no fresh update claim is made. The backend requires outbound HTTPS access to `api.github.com` only for a fresh check.

Requests use a five-second timeout, no redirects or retries, and a 256 KiB response limit. Failed checks back off for 15 minutes. `GET /api/v1/updates` reports `status: check_failed` and `cache_status: stale` after a failed refresh, preserving the original `checked_at` timestamp and trusted release data but never advertising it as freshly verified. Each backend worker has its own bounded cache; restarts clear it. Only admin sessions can access the endpoint, not scoped API tokens. No session or provider credentials are sent to GitHub.

The browser stops/ignores requests after logout and avoids checks while hidden. It checks on returning to a visible tab when due. Frontend and backend artifact metadata must match before an update banner or latest-version tooltip can appear. An installed version label alone does not assert freshness. Development/prerelease builds suppress update claims.

The release workflow publishes a stable GitHub Release only after both tagged images are pushed. `latest` follows the default branch and reports a SHA-bearing development version; pin matching explicit release tags for stable installations. Old images without embedded metadata remain unknown. Production runtime does not require `.git`. For native installations, reinstall the updated systemd units when adopting the generated `deploy/version.env` mechanism. If versions are unknown, rebuild from a clean release checkout or deploy newly published tagged images; inspect backend `APP_VERSION` and frontend build metadata when labels disagree.

## Application versioning policy

Frontend and backend ship together under one canonical `vMAJOR.MINOR.PATCH` tag.
`frontend/package.json` is package tooling metadata, not the application version.
The README badge follows published stable GitHub Releases, not branch builds or tags.

Maintainers classify each runtime-changing PR with exactly one repository label:

| Label | Meaning | Example from v1.2.3 |
| --- | --- | --- |
| `release:patch` | Backward-compatible fixes | v1.2.4 |
| `release:minor` | Backward-compatible features | v1.3.0 |
| `release:major` | Breaking API/configuration/deployment behavior | v2.0.0 |
| `release:none` | Explicitly reviewed non-releasable runtime change | No increment |

Create these labels in repository settings before adopting the workflow. The PR
classification check rejects missing, conflicting, or unrecognized classifications
for runtime paths. Make it a required branch-protection check. Labels, not commit
subjects, are authoritative; a `feat:` title alone is not sufficient. Do not remove
or change release labels on merged PRs until they have shipped.

Application paths include backend application/migrations/dependencies, frontend
source/public assets/dependencies, Dockerfiles, nginx/entrypoint assets, Compose,
`deploy/`, and the native build script. Documentation, tests, and release tooling
alone do not trigger a release, even with a release label. Use `release:none` only
when a runtime-path change truly needs no installation update. Merge or squash
runtime PRs into `main`; rebase merges and direct runtime commits lack reliable PR
classification and block release planning rather than guessing intent.

### Creating a release

`Application release` runs weekly (Monday 10:00 UTC) and can be dispatched manually
from `main`. It batches all changes since the last published stable release and
applies the highest increment once. There is no release per commit or per merge.
A documentation-only/non-releasable batch does nothing. Ambiguous runtime changes
fail planning before any tag is created; add the missing classification to their
merged PRs and retry.

For the **first release**, dispatch with `initial_base` set to a reviewed full
40-character baseline commit SHA, exclusive. This explicitly selects the history
being classified instead of guessing which legacy commits should ship. For this
feature's adoption, use the pre-feature `main` commit as the baseline so the
classified update-notification PR is included. The initial numeric baseline is
v0.0.0: patch yields v0.0.1, minor v0.1.0, major v1.0.0. Subsequent runs derive the
version from published stable releases automatically. No version file needs a
manual bump. History scanning is bounded to 500 first-parent commits per batch.

The workflow serializes release attempts without cancelling active runs. A
create-only GitHub tag reserves the immutable release commit and a **draft** Release.
The reusable Docker workflow tests that exact commit (including PostgreSQL
migrations), builds both images with the same version, then pushes the existing
`ghcr.io/skulldorom/usage-dashboard-backend` and
`ghcr.io/skulldorom/usage-dashboard-frontend` image names. Both image version/revision
labels are read back from GHCR before the draft Release becomes public. Exact
`vX.Y.Z`, `X.Y.Z`, `X.Y`, and SHA tags remain available. `main` and `latest` remain
development channels; stable releases do not move them.

Tests/build/push/verification failures leave only an unpublished reservation;
GitHub's latest stable release and the dashboard never advertise it. A failed
matrix push can leave one image/tag or a moving minor alias in GHCR: **only published
GitHub Releases are installable release announcements**. Do not deploy an unpublished
reservation. Retry the workflow to rebuild the same reserved commit and complete
publication before including newer merges. Never move an existing stable tag.
Multiple unpublished tags or unmanaged draft Releases require operator resolution;
the workflow fails closed. GitHub cannot atomically publish two images, so moving
image aliases are not a release transaction. Pin a published exact version in both
artifacts. Publication is idempotent; an already published managed release is not
announced twice. Protect release tags from manual creation/movement and limit
workflow dispatch/write permissions to trusted maintainers. Tag creation with
`GITHUB_TOKEN` does not trigger another workflow: tests/builds are explicitly called.

### Preparing a major release

Label the breaking PR `release:major` before merging, document migration and
configuration changes in that PR, and merge any companion frontend/backend work
before the weekly run (or dispatch once the batch is ready). Review every pending
PR's label and ensure the breaking release is deployable as one commit snapshot.
The highest pending intent makes the next version `v(N+1).0.0`; no separate frontend
or backend bump is needed. Branch protection should require classification and the
existing tests. The workflow does not infer breaking changes from titles.

### Stable versus development metadata

Stable release builds inject the reserved tag into backend `APP_VERSION` and
frontend `VITE_APP_VERSION`, and include matching OCI version/source-revision labels.
Default-branch images use `v0.0.0-dev.<full-commit-SHA>`. Native builds from a clean
exact stable-tag checkout use that tag; other native builds use
`v0.0.0-dev.<short-SHA>` with `.dirty` for tracked edits. Plain local builds with no
metadata remain unknown. Development prereleases cannot trigger stable update
claims, even when their numeric base is lower. The authenticated sidebar retains
the installed version and shows separate artifact labels for a mismatch. Dismissal
still applies only to the specific available release; this process never updates
an installation automatically.

Compose operators set `IMAGE_TAG` to a **published** `vX.Y.Z` and recreate both
services. Standalone operators pin both image references to the same published tag.
Native operators check out that tag, run `sh scripts/build-release.sh`, and follow
the existing migration/systemd upgrade procedure. Neither container runtime nor
native runtime needs `.git`; Git is needed only during native build preparation.
