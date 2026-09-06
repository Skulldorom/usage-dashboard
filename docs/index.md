# Usage Dashboard

Self-hosted provider usage, quota, cost, and attribution dashboard for Firecrawl,
DeepSeek, OpenAI, Anthropic/Claude, OpenRouter, OpenAI Codex, OpenCode Go, and
custom HTTP endpoints. It
stores provider credentials encrypted at rest, polls usage/balance APIs, renders
a dark React/MUI dashboard, and exposes a flat Homepage Dashboard endpoint.

## Stack

- **Backend**: FastAPI, SQLAlchemy async, asyncpg, Alembic, cryptography/Fernet
- **Frontend**: Vite, React, MUI, React Router
- **Runtime**: PostgreSQL, nginx-based frontend/proxy image, Docker Compose

## Start here

- [Installation](/getting-started/installation) - Docker Compose quick start.
- [First-run setup](/getting-started/first-run) - create the admin password.
- [Connect your first provider](/getting-started/first-provider) - credential, billing, test, and first poll.
- [Environment variables](/configuration/environment) - the configuration reference.
- [Providers](/providers/) - supported providers and their endpoints.
- [Dashboard](/using/dashboard) - latest quotas, balances, and warnings.
- [Usage & analytics](/using/usage-and-analytics) - history, attribution, cost, and value.
- [Connected providers](/configuration/connected-providers) - add and manage connections.
- [Homepage Dashboard](/integrations/homepage) - the Homepage widget.
- [Browser Extension](/extension/) - the Chrome/Brave companion.
