# Testing

CI runs both suites before building images. Run them locally to match.

## Backend

```bash
cd backend
. .venv/bin/activate   # or your active environment
pytest
```

Tests live under `backend/tests/`. `pytest.ini` sets `pythonpath = backend` so
imports resolve to `app.*` without an editable install.

## Frontend

```bash
cd frontend
npm ci
npm run test    # vitest run
npm run lint    # eslint .
npm run build   # vite build
```

Unit tests are Vitest specs colocated with the code (e.g.
`src/lib/*.test.js`).

## CI

`.github/workflows/docker-images.yml` runs pytest, the frontend test/lint/build
checks, and then builds both images on push to `main` and on tags.
