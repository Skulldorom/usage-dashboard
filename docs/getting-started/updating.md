# Updating

Use the upgrade procedure for the way Usage Dashboard was installed:

- [Docker Compose](/getting-started/docker-compose#upgrade)
- [Native Linux](/getting-started/native-linux#upgrade)
- [Standalone containers](/getting-started/standalone-containers#upgrade)

GitHub Releases are authoritative for published stable versions. Stable means the
latest published, non-draft, non-prerelease GitHub Release; a registry tag alone
does not establish that a release is published.

## Docker image channels

Compose defaults to `IMAGE_TAG=latest`; this behavior remains unchanged. `latest`
is the recommended stable channel; `stable` is its equivalent alias. Both move
after both reserved release images are verified, immediately before GitHub publication. `main` is the moving development channel and may contain unreleased
changes. The immutable `vX.Y.Z` tag identifies one exact release. The moving `vX.Y`
and `vX` tags point to the newest stable version in their respective series. Treat
moving tags as convenience channels, not immutable deployment references.

Compose does not pull images while running. Automatic updates require an explicitly
configured updater; none is installed by the official configuration. `docker compose pull` explicitly
fetches the selected tag, and `docker compose up -d` recreates changed containers.
Database migrations run automatically when the backend starts. Neither command
switches channels.

## Refresh the selected channel

```bash
docker compose pull
docker compose up -d
```

## Pin a version

To deploy an exact stable release, set `IMAGE_TAG` in `.env`. Both application
images use the same tag:

```bash
IMAGE_TAG=v1.2.0
```

Exact `vX.Y.Z` tags are immutable. Pin one for incident recovery or whenever a
moving channel is unsuitable; explicitly restore the desired channel afterward.

## Custom image references

If you publish under a different registry or name, override the full image
references instead of the tag:

```bash
BACKEND_IMAGE=ghcr.io/your-org/usage-dashboard-backend:latest
FRONTEND_IMAGE=ghcr.io/your-org/usage-dashboard-frontend:latest
```

See the [environment variable reference](/configuration/environment) for all
image-related settings.

## Channel promotion and recovery

The `stable-channels.yml` workflow on `main` performs promotion. Manual dispatch
requires its confirmation boolean to be `true`; the default is a dry run. Promotion
verifies both pulled images' OCI version/revision labels, then
updates moving tags using pinned image-index digests. It refuses to move a tag already
pointing to a newer version and shares `application-release` concurrency to avoid
racing release publication.

GitHub Releases and GHCR cannot be updated atomically. A partial promotion can leave
verified reserved-release images discoverable in GHCR before GitHub publication.
Those images are not a published release. Roll forward by rerunning the workflow
after resolving its reported issue; do not roll back moving tags. Temporarily pin
Compose to the latest published exact `vX.Y.Z` when a known published version is
needed during recovery.

To migrate from the previous `latest`-as-development behavior, manually dispatch
`stable-channels.yml` on `main`, review the dry-run plan, then dispatch with
confirmation set to `true`. Recovery through this workflow selects only the latest
published GitHub Release. If an `Application release` reservation is pending, rerun
`Application release`: it resumes the reservation using the exact existing images.
Bootstrap also uses a manual `stable-channels.yml` dispatch on `main`, initially
with confirmation false to review the plan. Compose retains its `latest` default,
and explicit stable-version pins remain supported. No workflow pulls images onto or
restarts an operator's host.

The commands on this page apply only to Docker Compose. Native and standalone
container deployments must follow their linked ordering so migrations complete
before the new backend serves traffic.


## Update notifications

The authenticated dashboard checks GitHub directly from the browser after a 2.5-second
delay. The footer displays the actual installed backend version, or **Version unknown**
when metadata is unavailable. Development builds display **Development** and a short
commit identifier. Full frontend/backend versions remain available through keyboard
focus or hover on **Version details**, and **Copy full version metadata**. Clipboard
copy requires browser permission and a secure context.

Only a verified, unexpired stable release can produce a notification:

| Installation | Notification |
| --- | --- |
| Matching stable artifacts below the latest stable release | **Update available**, latest version and **View release** link. |
| Matching development artifacts | **Stable release available** as an alternative; no newer-version comparison. |
| Current or newer stable artifacts | Installed version only; no success message or downgrade notice. |
| Unknown or mismatched artifacts, expired metadata, or failed checks | Installed version only; no availability claim. |

Drafts, prereleases, placeholder/malformed versions, future publication timestamps,
and unexpected repository/release URLs are rejected. The link opens only the verified
GitHub release page. Checks never pull images, restart services, or run migrations.
The desktop and mobile views retain keyboard-accessible links and dismissal controls.

Dismissal is stored per release and notification type in localStorage and synchronized
between views and tabs. A different release can appear again. Older stable-update
dismissals remain respected. With restricted storage, dismissal works for the active
views but does not survive a reload.

### Stable and development image channels

`main` is the development channel and embeds `v0.0.0-dev.<full-commit-SHA>`
because a branch build is not a published stable release, even if its source commit
also has a release tag. `latest` is the stable-equivalent moving channel. The footer
shortens only the presentation; full build metadata remains intact. Stable release
builds inject the actual release tag into backend `APP_VERSION`, frontend
`VITE_APP_VERSION`, and OCI version labels. Matching images share the same source
revision. No runtime version constant or Git checkout is required.

To select stable rather than development, set `IMAGE_TAG` to an exact **published**
release tag (for example `v1.0.0`) in Compose's `.env`, then run the pull/recreate
commands above. Standalone deployments must pin both full image references to the
same published exact tag. Follow the installation-specific migration ordering.
Moving minor aliases are not an atomic publication guarantee.

Native Linux installs run `sh scripts/build-release.sh` from a clean release
checkout. It builds matching frontend metadata and writes `deploy/version.env`,
loaded by the supplied backend systemd unit. Rerun after every upgrade. Other
native builds embed development metadata, with `.dirty` for tracked edits.
Local builds without embedded metadata remain unknown.

### Diagnose artifact mismatches

Focus **Version details** or copy metadata to compare the complete frontend and
backend versions, including development SHA and build suffixes. A known mismatch
suppresses the update banner and remains visible in these details. Unknown artifacts are never
reported as up to date. Check both container image references, backend
`APP_VERSION`, and OCI version/revision labels; deploy matching artifacts from the
same published exact tag or development build. Recreate both services, then
reload the browser to remove an older cached frontend. For native installs,
rebuild the frontend and generated `deploy/version.env` together and restart the
backend using the updated systemd units. Do not manually alter a version value
to hide a mismatch.

### Cache, browser access and failures

Successful validated checks are cached for **15 minutes** in localStorage, shared
across tabs on the same origin. Cached fields are revalidated before use. There is
no continuous polling: checks happen on dashboard load/reopen and when a tab becomes
visible, subject to the cache and a **one-minute failure backoff**. A visible notice
expires after 15 minutes even if the tab stays open; expiry itself makes no request.

A five-second AbortController timeout bounds the request and body read. HTTP 404,
403, 429, network errors, timeouts and invalid metadata quietly suppress notices;
none proves the installation is current. The browser console records bounded,
non-sensitive diagnostics. Only validated fields are persisted, never raw release
bodies or assets. Failures store only a retry deadline, not a successful result.

The browser needs HTTPS access to `api.github.com`, Fetch, AbortController and
streamed responses. GitHub's REST API supports
[CORS from any origin](https://docs.github.com/en/rest/using-the-rest-api/using-cors-and-jsonp-to-make-cross-origin-requests).
Requests explicitly omit cookies/credentials and referrers, use no GitHub token,
and never use the application's authenticated API client. If you configure a
Content Security Policy, allow `https://api.github.com` in `connect-src`. Privacy
extensions, firewalls or rate limits can prevent checks without blocking dashboard
operation. API rate limits apply to the browser's public IP, potentially shared by
other clients.

Web Locks avoid simultaneous cross-tab lookups where supported (normally secure
contexts). Other browsers still share cached results and backoff, but simultaneous
cold tabs may each send one request. Restricted localStorage falls back to page
memory; cross-tab/reload reuse is then unavailable. No worker or backend GitHub
access is required. The removed `/api/v1/updates` endpoint and backend cache/timeout
settings are no longer used. The existing auth-status response supplies the running
backend's `APP_VERSION`; frontend metadata still comes from `VITE_APP_VERSION`.
An older backend without that metadata quietly suppresses notifications.

Verification establishes published release metadata, not artifact contents or
migration compatibility. See [notification architecture](/development/update-notifications)
for implementation and regression coverage.

## Application versioning policy

Frontend and backend ship together under one canonical `vMAJOR.MINOR.PATCH` tag.
`frontend/package.json` is package tooling metadata, not the application version.
The README badge follows published stable GitHub Releases, not branch builds or tags.

New PRs targeting `main` automatically receive `release:patch` when no release classification is present. Maintainers may select `release:minor`, `release:major`, or `release:none`; the label workflow removes the previous classification when the event history establishes one unambiguous latest selection. Simultaneous or ambiguous changes fail closed and require a maintainer to leave exactly one label. Opening gets the default; reopening, synchronization, and deliberately removing a label never restore it. Draft PRs are classified too, and the required check remains active until exactly one valid label is present.

The release classifications are:

| Label | Meaning | Example from v1.2.3 |
| --- | --- | --- |
| `release:patch` | Backward-compatible fixes | v1.2.4 |
| `release:minor` | Backward-compatible features | v1.3.0 |
| `release:major` | Breaking API/configuration/deployment behavior | v2.0.0 |
| `release:none` | Explicitly reviewed skipped change (including docs/tests) | No release for this PR |

Create these labels in repository settings before adopting the workflow. The PR
classification check rejects missing, conflicting, or unrecognized classifications
on every PR targeting `main`, including documentation-only PRs. Label validation is
independent of changed-file eligibility; choose `release:none` for skipped changes.
Make it a required branch-protection check. Labels, not commit
subjects, are authoritative; a `feat:` title alone is not sufficient. The planner reconstructs label events from the PR timeline up to its matching
merge event, verifying merge commit and timestamp. Later relabeling cannot change
the release intent. Missing/conflicting merge-time labels or incomplete history
block planning; relabeling after merge cannot repair them. Include legacy history
only through an explicitly reviewed initial baseline. Do not delete or rename
release labels: GitHub timeline data is the audit source, not an immutable ledger.

Application paths include backend application/migrations/dependencies, frontend
source/public assets/dependencies, Dockerfiles, nginx/entrypoint assets, Compose,
`deploy/`, and the native build script. Documentation, tests, and release tooling
alone do not trigger a release, even with a release label. Use `release:none` only
when a runtime-path change truly needs no installation update. This is a deliberate
maintainer decision, recorded at merge time and printed with PR number and commit
in planner logs. It skips the increment, not deployment tests or publication gates.
A none-only batch creates no release; skipped commits are still included in the
source of a later eligible batch. Labels cannot prove a change is non-breaking:
require maintainer review and required checks before merging. Merge or squash
runtime PRs into `main`; rebase merges and direct runtime commits lack reliable PR
classification and block release planning rather than guessing intent.

### Creating a release

`Application release` evaluates every push to `main`, runs weekly (Monday 10:00 UTC), and can be dispatched manually from `main`. The same serialized pipeline batches pending changes since the last published stable release and applies the highest increment once. A merge triggers evaluation; it only publishes when eligible runtime changes have a release-worthy classification. Documentation-only, test-only, and other ineligible paths do not publish by themselves. The scheduled run remains a fallback for missed/failed evaluations, and manual dispatch retries a reserved attempt before planning newer commits.
A documentation-only/non-releasable batch does nothing. Ambiguous runtime changes
fail planning before any tag is created. Fix missing labels before merging;
after merge, editing labels does not rewrite intent. Legacy unlabeled history
requires a reviewed bootstrap baseline rather than retroactive classification.

Before the first stable release, automatic pushes deliberately skip planning; they cannot infer a baseline. To bootstrap, verify that `2040b2ef6e24f1cde5dc2fdb2ee09eaf77eaab0a` is the reviewed pre-feature baseline, open **Actions → Application release → Run workflow** on `main`, enter that full SHA in `initial_base`, and dispatch. Do not create the tag manually. Review the resulting reserved `v1.0.0` commit and allow the normal tests, both image pushes, registry verification, and publication to finish. Retry failed runs using the same workflow; planner resumes that exact reservation before newer changes. Once `v1.0.0` is published, pushes run normally without `initial_base`. A failed bootstrap reservation blocks later versions until retried or explicitly resolved.

The planner requires a reviewed full 40-character baseline SHA, exclusive. This explicitly selects the history
being classified instead of guessing which legacy commits should ship. For this
feature's adoption, use the pre-feature `main` commit as the baseline so the
classified update-notification PR is included. The first published stable release is
**v1.0.0** regardless of patch, minor, or major intent in the first eligible batch. A
`release:none`-only or documentation-only batch creates no release. Subsequent runs derive the
version from published stable releases automatically. No version file needs a
manual bump. History scanning is bounded to 500 first-parent commits per batch.

The workflow serializes release attempts without cancelling active runs. A
create-only GitHub tag reserves the immutable release commit and a **draft** Release.
The reusable Docker workflow tests that exact commit (including PostgreSQL
migrations), builds both images with the same version, then pushes the existing
`ghcr.io/skulldorom/usage-dashboard-backend` and
`ghcr.io/skulldorom/usage-dashboard-frontend` image names. Both image version/revision
labels are read back from GHCR before the draft Release becomes public. The build
explicitly targets `linux/amd64`; verification pulls that runnable platform and
uses `docker image inspect` to read image configuration labels, which works for
single manifests and OCI indexes with BuildKit provenance attestations. Exact
`vX.Y.Z` is the immutable release tag. After both images pass verification,
promotion copies their exact digests to `vX.Y`, `vX`, `stable`, and `latest`,
then publishes the GitHub Release. `main` and SHA tags identify development builds.
Legacy unprefixed version aliases are not maintained by this workflow.

Tests/build/push/verification failures leave only an unpublished reservation;
GitHub's latest stable release and the dashboard never advertise it. A failed
matrix push can leave one exact image/tag in GHCR; no moving alias changes until
both images verify. A promotion failure can leave partial moving aliases: **only published
GitHub Releases are installable release announcements**. Do not deploy an unpublished
reservation. Retry the workflow to reuse verified existing exact tags, build only missing
artifacts from the same reserved commit, and complete
publication before including newer merges. Newer triggers cannot cancel the active release; after publication a follow-up evaluation processes remaining commits. Never move an existing stable tag.
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
before merging the breaking PR (or stage them together in one PR). Review every pending
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
metadata remain unknown. Development prereleases never trigger a newer-version upgrade claim, even when
their numeric base is lower. They can show a separate **Stable release available**
notice. The authenticated sidebar retains a compact installed-version label and
exposes both artifact versions in details for a mismatch. Dismissal applies to the
specific release and notification type; nothing updates the installation automatically.

Compose operators normally keep `IMAGE_TAG=latest` (or `stable`) and pull/recreate
both services; a **published** `vX.Y.Z` provides explicit reproducible pinning. Standalone operators pin both image references to the same published tag.
Native operators check out that tag, run `sh scripts/build-release.sh`, and follow
the existing migration/systemd upgrade procedure. Neither container runtime nor
native runtime needs `.git`; Git is needed only during native build preparation.

### Required repository protection

Audit on 2026-11-12: active `main` ruleset (ID 19039282) requires PRs and
`release-classification`, `Test backend (pytest + Ruff)`,
`Test backend migrations (PostgreSQL)`, and `Test frontend (test + lint + build)`
from GitHub Actions (integration 15368). No bypass actors are configured.
Stable-tag ruleset 27110157 covers `refs/tags/v*`, prohibiting updates, deletion,
and non-fast-forward changes without bypass. It permits creation, so the release
workflow needs no tag-protection bypass. Neither ruleset was changed.

All PR validation workflows run without PR path filters, including docs-only and
draft PRs; release labels never bypass backend/frontend/migration checks.
The trusted `pull_request_target` label job fetches only its base commit's
script, never PR code, and validates immediately after its own label mutations.
This matters because `GITHUB_TOKEN` label writes do not trigger new workflow runs.
The read-only `release-classification` PR check remains in the Docker workflow
with its existing identity. It waits up to a minute for label reconciliation before
rejecting invalid labels. Keep it required from GitHub Actions. The label workflow
must exist on `main` before it can run: classify this adoption PR explicitly, then
verify defaults on the next PR. Neither workflow runs PR code with label-write permissions.
Rebase remains allowed by repository settings but unsupported for runtime release
history; use squash or merge commits for runtime PRs.

The reusable `images` caller explicitly allows `contents: read`, `packages: write`,
and `pull-requests: read`. The last permission fixes the pre-job startup error in
run 43204555380: GitHub validates nested permissions even for conditionally skipped
jobs. PR classification remains explicitly conditional on `pull_request`, so release
runs do not execute it while nested permissions remain compatible. Label reconciliation needs `contents: read`, `pull-requests: read`, and
`issues: write`. Reservation/publication use `contents: write`; registry operations
use package permissions. The post-publication follow-up job alone has `actions: write`
to dispatch this same workflow when `main` advanced beyond the published snapshot.
No PAT, custom service, or bypass actor is needed.

GitHub concurrency keeps one active and at most one pending run; newer triggers can
replace pending runs even with cancellation disabled. Planning reads current `main`,
resumes any reservation first, and after successful publication queues a fresh
evaluation when newer commits remain. Thus merges arriving during recovery are not
stranded waiting for another merge. A failed attempt is retried on the next push,
weekly run, or manual dispatch. No tag push trigger exists. Local syntax/permission
contract tests cannot prove GitHub token issuance, check attachment, or registry
publishing: verify those in Actions after adoption, without bypassing the gates.
