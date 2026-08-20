# Introduction

Usage Dashboard is a self-hosted API usage dashboard for Firecrawl, DeepSeek,
OpenAI, Anthropic/Claude, OpenRouter, OpenAI Codex, and custom HTTP usage
endpoints. It stores provider credentials encrypted at rest, polls usage and
balance APIs, renders a dark React/MUI dashboard, and exposes a flat Homepage
Dashboard endpoint.

## Stack

- **Backend**: FastAPI, SQLAlchemy async, asyncpg, Alembic, cryptography/Fernet
- **Frontend**: Vite, React, MUI, React Router
- **Runtime**: PostgreSQL, nginx-based frontend/proxy image, Docker Compose

![Usage Dashboard screenshot](/screenshot.png)

## What you can do

- Add and manage provider configurations from the Settings page.
- See current balances, usage, and polling health at a glance.
- Configure alert thresholds and automatic polling.
- Serve a flat JSON payload to a Homepage Dashboard widget.
- Connect the Chrome/Brave browser extension for one-click, always-visible usage.

## Next steps

1. [Install](/getting-started/installation) the stack with Docker Compose.
2. Complete [first-run setup](/getting-started/first-run) to create the admin password.
3. Add your providers and review the [configuration](/configuration/environment) reference.
