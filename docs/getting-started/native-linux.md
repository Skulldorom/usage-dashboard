# Native Linux production installation

This is the supported non-container production layout for Debian/Ubuntu hosts:

```text
nginx :80/:443 -> /api and /health -> Uvicorn 127.0.0.1:8000 -> PostgreSQL
              -> all other paths -> frontend/dist
```

systemd runs migrations before starting the backend, restarts the API after a
failure, starts it after reboot, and sends logs to the journal. nginx serves the
Vite production build; the Vite development server is not used.

## Supported baseline and prerequisites

The production images and CI define the runtime baseline: **Python 3.14**,
**Node.js 26**, PostgreSQL **18**, and nginx. The application directory used by
the supplied assets is `/opt/usage-dashboard`; secrets live in
`/etc/usage-dashboard/backend.env`.

On Debian or Ubuntu, install the host packages first:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git nginx postgresql-common
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh
sudo apt install -y postgresql-18 postgresql-client-18
```

Install Node.js 26 from your trusted package source (this example uses
NodeSource). Install Python 3.14 from your distribution or with `uv`; this
example installs `uv` system-wide and lets it provision the exact Python runtime
for the service account when the virtual environment is created:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh
curl -fsSL https://deb.nodesource.com/setup_26.x | sudo -E bash -
sudo apt install -y nodejs
node --version   # must report v26.x
uv --version
```

If your PostgreSQL package is older than 18, use a supported PostgreSQL 18
repository or external PostgreSQL 18 service before continuing.

## 1. Create PostgreSQL and the service account

Generate a URL-safe password, then create the database role and database:

```bash
DB_PASSWORD=$(openssl rand -base64 36 | tr '+/' '-_' | tr -d '=\n')
sudo -u postgres psql --set=db_password="$DB_PASSWORD" <<'SQL'
CREATE ROLE usage_dashboard LOGIN PASSWORD :'db_password';
CREATE DATABASE usage_dashboard OWNER usage_dashboard;
SQL
sudo useradd --system --create-home --home-dir /var/lib/usage-dashboard \
  --shell /usr/sbin/nologin usage-dashboard
```

Save the generated password now; the next step needs it.

## 2. Install the application

Clone a release (replace the example version with a real release tag), create the virtual
environment, install backend requirements, and build the frontend:

```bash
VERSION=v1.2.0
sudo git clone --branch "$VERSION" --depth 1 \
  https://github.com/Skulldorom/usage-dashboard.git /opt/usage-dashboard
sudo chown -R usage-dashboard:usage-dashboard /opt/usage-dashboard

sudo -H -u usage-dashboard uv venv --python 3.14 --seed /opt/usage-dashboard/backend/.venv
sudo -H -u usage-dashboard /opt/usage-dashboard/backend/.venv/bin/pip \
  install -r /opt/usage-dashboard/backend/requirements.txt

cd /opt/usage-dashboard/frontend
sudo -H -u usage-dashboard env VITE_API_BASE_URL=/api npm ci
sudo -H -u usage-dashboard env VITE_API_BASE_URL=/api npm run build
```

Do not track `main` on a production host. Use a release tag so installs and
upgrades are reproducible.

## 3. Configure the backend

Install the example environment file and edit it:

```bash
sudo install -d -m 0750 -o root -g usage-dashboard /etc/usage-dashboard
sudo install -m 0640 -o root -g usage-dashboard \
  /opt/usage-dashboard/deploy/backend.env.example \
  /etc/usage-dashboard/backend.env
sudo /opt/usage-dashboard/backend/.venv/bin/python -c \
  "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
sudoedit /etc/usage-dashboard/backend.env
```

Set `DATABASE_URL` with the URL-safe database password and put the generated
Fernet value in `ENCRYPTION_KEY`. Keep the same encryption key for the lifetime
of the installation. See [Environment variables](/configuration/environment).

## 4. Install systemd and nginx assets

```bash
sudo install -m 0644 /opt/usage-dashboard/deploy/systemd/*.service /etc/systemd/system/
sudo install -m 0644 /opt/usage-dashboard/deploy/nginx/usage-dashboard.conf \
  /etc/nginx/sites-available/usage-dashboard
sudo ln -s /etc/nginx/sites-available/usage-dashboard \
  /etc/nginx/sites-enabled/usage-dashboard
sudo rm -f /etc/nginx/sites-enabled/default
sudoedit /etc/nginx/sites-available/usage-dashboard  # set server_name

sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now postgresql nginx usage-dashboard-backend.service
```

Enabling the backend also starts its required migration unit. On every backend
start, `usage-dashboard-migrate.service` must finish successfully before Uvicorn
starts. The migration unit uses the same `alembic upgrade head` command as the
backend container.

Confirm the complete route:

```bash
systemctl status usage-dashboard-backend.service --no-pager
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1/health
```

Configure TLS with your normal ACME/certificate tooling before exposing the
site publicly. Only nginx should be internet-facing; PostgreSQL and Uvicorn
remain bound locally.

## First run, logs, and shutdown

Open the nginx URL and follow [First-run setup](/getting-started/first-run). Get
the one-time code and follow live logs with:

```bash
sudo journalctl -u usage-dashboard-backend.service -f
sudo journalctl -u usage-dashboard-migrate.service
```

systemd starts the service after reboot and restarts Uvicorn after failures.
For maintenance:

```bash
sudo systemctl stop usage-dashboard-backend.service
sudo systemctl start usage-dashboard-backend.service
```

Uvicorn receives `SIGTERM` and has up to 30 seconds for application shutdown.

## Upgrade

Read the target release notes, then use this order:

1. Back up PostgreSQL and `/etc/usage-dashboard/backend.env`.
2. Stop the backend so old application code cannot run against a new schema.
3. Fetch and check out the target release tag.
4. Update the Python dependencies.
5. Install frontend dependencies and rebuild production assets.
6. Reinstall the systemd units and review changed configuration examples.
7. Start the backend; its required migration unit runs first and blocks startup
   if migration fails.
8. Reload nginx and verify the complete route.

```bash
cd /opt/usage-dashboard
sudo systemctl stop usage-dashboard-backend.service
VERSION=v1.2.0
sudo -H -u usage-dashboard git fetch --tags --prune
sudo -H -u usage-dashboard git checkout "$VERSION"
sudo -H -u usage-dashboard backend/.venv/bin/pip install -r backend/requirements.txt
sudo -H -u usage-dashboard env VITE_API_BASE_URL=/api npm --prefix frontend ci
sudo -H -u usage-dashboard env VITE_API_BASE_URL=/api npm --prefix frontend run build
sudo install -m 0644 deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo nginx -t
sudo systemctl start usage-dashboard-backend.service
sudo systemctl reload nginx
curl --fail http://127.0.0.1/health
```

Before starting, compare the release's `deploy/backend.env.example` and nginx
example with the files in `/etc`. Merge relevant changes rather than overwriting
your secrets, `server_name`, or TLS configuration.

If a step fails, do not start the backend until it is corrected. Database
downgrades are not automatic; follow release-specific rollback instructions.

## Backups

Back up the PostgreSQL database and environment file together:

```bash
sudo -u postgres pg_dump -d usage_dashboard -Fc \
  | sudo tee /var/backups/usage-dashboard.dump >/dev/null
sudo chmod 0600 /var/backups/usage-dashboard.dump
sudo install -m 0600 /etc/usage-dashboard/backend.env \
  /var/backups/usage-dashboard-backend.env
```

Store copies off-host, protect them as secrets, and test restores. The source
tree and frontend build are reproducible; PostgreSQL and `ENCRYPTION_KEY` are
the irreplaceable state.
