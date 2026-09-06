<p align="center"><img src="logo.svg" alt="Usage Dashboard logo" width="96" /></p>

# Usage Dashboard

Self-hosted provider usage dashboard for Firecrawl, DeepSeek, OpenAI, Anthropic/Claude, OpenRouter, OpenAI Codex, OpenCode Go, and custom HTTP endpoints. It tracks current quota and health, retains history, analyzes cost and value, attributes Hermes-observed workload by provider/model/profile, stores provider credentials encrypted at rest, and exposes integrations for Homepage Dashboard and the browser extension.

<p align="center">
  <a href="https://ko-fi.com/skulldorom"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support me on Ko-fi" /></a>
</p>

![Usage Dashboard screenshot](screenshot.png)

## Documentation

Full documentation lives in the [documentation site](https://skulldorom.github.io/usage-dashboard/docs/). Useful starting points are [Dashboard](https://skulldorom.github.io/usage-dashboard/docs/using/dashboard.html), [Usage & analytics](https://skulldorom.github.io/usage-dashboard/docs/using/usage-and-analytics.html), [Connected providers](https://skulldorom.github.io/usage-dashboard/docs/configuration/connected-providers.html), and [Understanding cost & value](https://skulldorom.github.io/usage-dashboard/docs/using/cost-and-value.html).

## Quick start

Start from a machine with Git and Docker Compose installed. This path uses the published containers, so you do not need to build anything locally.

```bash
git clone https://github.com/Skulldorom/usage-dashboard.git
cd usage-dashboard
cp .env.example .env
openssl rand -base64 32 | tr '+/' '-_'
```

Copy the generated value into `ENCRYPTION_KEY` in `.env`, replacing `replace-with-generated-fernet-key`. Then start the stack:

```bash
docker compose pull
docker compose up -d
docker compose logs backend
```

Open the frontend, then use the one-time setup code from the backend logs to create the admin password.

- Frontend: http://localhost:3000
- Backend health: http://localhost:3000/health

See [First-run setup](https://skulldorom.github.io/usage-dashboard/docs/getting-started/first-run.html) for the setup-code flow in more detail.

## Features

- 🔐 Provider credentials encrypted at rest with Fernet.
- 📊 Current quota, balance, usage history, forecasts, and provider health for eight provider types.
- 💵 PAYG and subscription cost accounting with explicit provenance and pricing coverage.
- 🧭 Hermes workload attribution by provider, model, profile, request, and session.
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
