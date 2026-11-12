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

Released container images receive `APP_VERSION` from their `v*` release tag. Native Linux installs run `sh scripts/build-release.sh` from a clean release checkout. This builds the frontend with the exact tag and writes `deploy/version.env`, loaded by the supplied backend systemd unit. Run this script after each upgrade; no manual version constant is required. Without Git at runtime, the built frontend and generated environment file retain the version. Development/default-branch builds use `unknown`. The UI compares the frontend build metadata with the backend version; mismatched or unknown artifact versions suppress update claims and show separate artifact labels. Use the same pinned tag for both standalone images and diagnose a mismatch with the image tag and backend `APP_VERSION`.

The backend caches successful GitHub metadata in memory for six hours and uses conditional ETag revalidation. GitHub is optional: outages, rate limits, or invalid responses do not affect dashboard operation; the last trusted result may be reported as stale and no fresh update claim is made. The backend requires outbound HTTPS access to `api.github.com` only for a fresh check.

Requests use a five-second timeout, no redirects or retries, and a 256 KiB response limit. Failed checks back off for 15 minutes. `GET /api/v1/updates` reports `status: check_failed` and `cache_status: stale` after a failed refresh, preserving the original `checked_at` timestamp and trusted release data but never advertising it as freshly verified. Each backend worker has its own bounded cache; restarts clear it. Only admin sessions can access the endpoint, not scoped API tokens. No session or provider credentials are sent to GitHub.

The browser stops/ignores requests after logout and avoids checks while hidden. It checks on returning to a visible tab when due. Frontend and backend artifact metadata must match before an update banner or latest-version tooltip can appear. An installed version label alone does not assert freshness. Development/prerelease builds suppress update claims.

The release workflow publishes a stable GitHub Release only after both tagged images are pushed. `latest` follows the default branch and reports an unknown development version; pin matching explicit release tags for stable installations. Old images without embedded metadata remain unknown. Production runtime does not require `.git`. For native installations, reinstall the updated systemd units when adopting the generated `deploy/version.env` mechanism. If versions are unknown, rebuild from a clean release checkout or deploy newly published tagged images; inspect backend `APP_VERSION` and frontend build metadata when labels disagree.
