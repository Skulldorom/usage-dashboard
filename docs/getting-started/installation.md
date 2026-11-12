# Installation options

Usage Dashboard supports three production deployment methods. Docker Compose is
the recommended default because it manages PostgreSQL, networking, persistence,
migrations, and service restarts as one tested stack.

| Method | Best for | PostgreSQL | Reverse proxy / TLS | Persistence | Startup | Upgrades |
| --- | --- | --- | --- | --- | --- | --- |
| [Docker Compose (recommended)](/getting-started/docker-compose) | Most self-hosters | Included | HTTP proxy included; operator adds TLS | Named PostgreSQL volume | Compose restart policies | Pull and recreate |
| [Native Linux](/getting-started/native-linux) | Debian/Ubuntu hosts managed with systemd | Operator-managed local PostgreSQL | Operator-managed nginx and TLS | PostgreSQL plus `/etc/usage-dashboard` | systemd | Update source, dependencies, build, migrate, restart |
| [Standalone containers](/getting-started/standalone-containers) | Portainer, Unraid, Synology, or custom container management | Operator-managed container or external service | Frontend image provides HTTP proxy; operator adds TLS | PostgreSQL storage | Container platform | Pull and recreate in order |

All production methods use PostgreSQL, the same Alembic migrations, the same
Uvicorn ASGI application, and a production Vite build served through nginx.
Compose defaults to the stable-equivalent moving `latest` image tag; `main` is the
moving development tag. Pin both images to the same immutable published `vX.Y.Z`
release when an exact version is required. GitHub Releases are authoritative for
published stable versions, and images are never pulled or deployed automatically.
See [Docker channel promotion and recovery](/getting-started/updating#channel-promotion-and-recovery).
Back up both PostgreSQL and the `ENCRYPTION_KEY`; losing that key makes stored
provider credentials unreadable.

## Development is separate

The Python virtual environment plus Vite development server described in
[Local development](/development/local-development) is an edit/test workflow.
It is not a production installation and does not provide production process
supervision, static asset serving, TLS, or PostgreSQL lifecycle management.

After choosing a method, continue to [First-run setup](/getting-started/first-run)
and [connect your first provider](/getting-started/first-provider).
