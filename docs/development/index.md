# Development

Usage Dashboard is a FastAPI backend with a React/MUI frontend, orchestrated by
Docker Compose in production.

- [Local development](/development/local-development) - run backend and frontend
  outside Docker.
- [Docker images](/development/docker-images) - build local images.
- [Testing](/development/testing) - run the test suites and lint.

## Repository layout

```text
backend/            FastAPI app, Alembic migrations, pytest tests
frontend/           Vite + React + MUI app, Vitest tests
docs/               This documentation site (VitePress)
docker-compose.yml  Production stack (db, backend, frontend)
```
