# Local development

Run the backend and frontend outside Docker for a fast edit/test loop.

::: warning Development only
This workflow uses SQLite by default and the Vite development server. It is not
a production deployment. Use one of the supported
[installation options](/getting-started/installation) for production.
:::

## Backend

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
pytest
```

Start the API with uvicorn (see `backend/app/main.py`) pointing at a database -
the default falls back to SQLite for local use.

## Frontend

```bash
cd frontend
npm install
npm run dev
npm run build
```

The dev server proxies `/api` to the backend (see `frontend/vite.config.js`).
Set `VITE_API_BASE_URL` to override the API base path.
