<p align="center"><img src="logo.svg" alt="Usage Dashboard logo" width="96" /></p>

# Usage Dashboard

Self-hosted API usage dashboard for Firecrawl, DeepSeek, OpenAI, Anthropic/Claude, OpenRouter, OpenAI Codex, and custom HTTP usage endpoints. It stores provider credentials encrypted at rest, polls usage/balance APIs, renders a dark React/MUI dashboard, and exposes a flat Homepage Dashboard endpoint.

![Usage Dashboard screenshot](screenshot.png)

## Documentation

Full documentation — installation, configuration, providers, integrations, the browser extension, and development — lives in the [documentation site](https://skulldorom.github.io/usage-dashboard/docs/).

## Quick start

```bash
cp .env.example .env
openssl rand -base64 32 | tr '+/' '-_'
# paste that value into ENCRYPTION_KEY in .env
docker compose pull
docker compose up -d
# open the frontend, copy the one-time setup code from backend logs, and create the admin password
```

Open through the frontend container, which also proxies API traffic to the backend:

- Frontend: http://localhost:3000
- Backend health: http://localhost:3000/health

First-run admin setup is log-based: the backend prints a one-time setup code when no password exists yet. See [First-run setup](https://skulldorom.github.io/usage-dashboard/docs/getting-started/first-run.html) for details.

## Features

- 🔐 Provider credentials encrypted at rest with Fernet.
- 📊 Usage and balance tracking for seven provider types.
- 🏠 Homepage Dashboard widget with dynamic per-provider rows.
- 🧩 Chrome/Brave browser extension with one-click setup.
- 🔔 Alert thresholds and automatic background polling.

## Stack

- Backend: FastAPI, SQLAlchemy async, asyncpg, Alembic, cryptography/Fernet
- Frontend: Vite, React, MUI, React Router
- Runtime: PostgreSQL, nginx-based frontend/proxy image, Docker Compose

## Development

See the [documentation site](https://skulldorom.github.io/usage-dashboard/docs/development/local-development.html) for local development, testing, and Docker image build instructions.

## License

[Mozilla Public License 2.0](LICENSE)
