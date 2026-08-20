# Usage Dashboard

Self-hosted API usage dashboard for Firecrawl, DeepSeek, OpenAI,
Anthropic/Claude, OpenRouter, OpenAI Codex, and custom HTTP usage endpoints. It
stores provider credentials encrypted at rest, polls usage/balance APIs, renders
a dark React/MUI dashboard, and exposes a flat Homepage Dashboard endpoint.

## Stack

- **Backend**: FastAPI, SQLAlchemy async, asyncpg, Alembic, cryptography/Fernet
- **Frontend**: Vite, React, MUI, React Router
- **Runtime**: PostgreSQL, nginx-based frontend/proxy image, Docker Compose

## Start here

- [Installation](/getting-started/installation) - Docker Compose quick start.
- [First-run setup](/getting-started/first-run) - create the admin password.
- [Environment variables](/configuration/environment) - the configuration reference.
- [Providers](/providers/) - supported providers and their endpoints.
- [Homepage Dashboard](/integrations/homepage) - the Homepage widget.
- [Browser Extension](/extension/) - the Chrome/Brave companion.
