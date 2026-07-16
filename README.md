# Usage Dashboard

Self-hosted API usage dashboard for Firecrawl, DeepSeek, and OpenAI/Codex. It stores provider credentials encrypted at rest, polls usage/balance APIs, renders a dark React/MUI dashboard, and exposes a flat Homepage Dashboard endpoint.

## Stack

- Backend: FastAPI, SQLAlchemy async, asyncpg, Alembic, cryptography/Fernet
- Frontend: Vite, React 19, MUI 6, React Router
- Runtime: PostgreSQL 16, nginx, Docker Compose

## Quick start

```bash
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# paste that value into ENCRYPTION_KEY in .env
docker compose up -d --build
```

Open:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/health
- API docs: http://localhost:8000/docs
- Homepage payload: http://localhost:8000/api/v1/homepage

## Configuration

| Variable | Description |
| --- | --- |
| `DATABASE_URL` | Async SQLAlchemy URL. Defaults to the Compose PostgreSQL service. |
| `ENCRYPTION_KEY` | Required Fernet key used to encrypt API credentials at rest. |
| `BACKEND_CORS_ORIGINS` | Comma-separated allowed origins for the FastAPI API. |
| `VITE_API_BASE_URL` | Frontend API base path. Defaults to `/api` for nginx proxying. |

## Providers

### Firecrawl

Uses `GET https://api.firecrawl.dev/v2/team/token-usage` and `GET https://api.firecrawl.dev/v2/team/credit-usage/historical`.

### DeepSeek

Uses `GET https://api.deepseek.com/user/balance`.

### OpenAI / Codex

Uses `GET https://api.openai.com/v1/organization/costs`. This endpoint requires an organization admin key.

## Homepage Dashboard widget

```yaml
- API Usage:
    icon: mdi-api
    widget:
      type: customapi
      url: http://usage-dashboard:8000/api/v1/homepage
      refreshInterval: 300000
      mappings:
        - field: summary
          label: Providers
        - field: configured_providers
          label: Configured
        - field: healthy_providers
          label: Healthy
        - field: degraded_providers
          label: Degraded
```

The `metrics` object contains flattened keys like `firecrawl_main_remaining_tokens` and `deepseek_main_total_balance` for extra mappings.

## Development

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
pytest
```

```bash
cd frontend
npm install
npm run dev
npm run build
```
