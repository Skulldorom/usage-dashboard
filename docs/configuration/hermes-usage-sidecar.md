# Installing the Hermes Usage Sidecar

Usage Dashboard connects to Hermes Agent through the standalone
[Hermes Usage Sidecar](https://github.com/Skulldorom/hermes-usage-sidecar).
Stock Hermes Agent does not expose the Usage Dashboard `/usage` contract
itself; the sidecar is the supported read-only bridge between Hermes usage
metadata and a Hermes data source in Usage Dashboard.

```text
Hermes Agent
    ↓ read-only SQLite
hermes-usage-sidecar
    ↓ GET /usage
Usage Dashboard
```

Hermes telemetry is supplemental and observational. It helps attribute usage
that flowed through Hermes, but it does not replace provider-reported account
usage where a provider exposes authoritative totals.

## What the sidecar reads

One sidecar instance discovers:

- `~/.hermes/state.db` as the `default` profile.
- `~/.hermes/profiles/*/state.db` for every named Hermes profile.

The sidecar opens Hermes databases read-only and exposes usage metadata only:
timestamps, profile, provider, model, session id, token counts, request counts,
and cost metadata. It does not expose prompts, responses, memories, tool
arguments, or conversation message bodies.

## Prerequisites

- Python 3.10 or newer for the local install path.
- Access to the Hermes home directory on the machine running Hermes, usually
  `~/.hermes`.
- A bearer token for Usage Dashboard to send when it polls the sidecar.
- Network reachability from the Usage Dashboard backend container/process to the
  sidecar base URL.

## Install and run locally

Clone the sidecar repository on the machine that runs Hermes, then install it
from that checkout:

```bash
git clone https://github.com/Skulldorom/hermes-usage-sidecar.git
cd hermes-usage-sidecar
python3.10 -m pip install .
```

Generate a local bearer token and keep it somewhere private:

```bash
USAGE_SIDECAR_TOKEN=$(openssl rand -hex 32)
printf 'USAGE_SIDECAR_TOKEN=%s\n' "$USAGE_SIDECAR_TOKEN"
```

Start the sidecar with the token and the Hermes home directory:

```bash
USAGE_SIDECAR_TOKEN="$USAGE_SIDECAR_TOKEN" \
  hermes-usage-sidecar --hermes-home ~/.hermes --bind 127.0.0.1 --port 8799
```

By default the sidecar binds to `127.0.0.1:8799`. That is the safest local
setting: only processes on the same host can reach it. If Usage Dashboard runs on
a different host or inside a container, see [Docker and networking](#docker-and-networking)
before widening the bind address.

You can also inspect what the sidecar can read without starting HTTP service:

```bash
hermes-usage-sidecar --dump --hermes-home ~/.hermes
```

## Run as a systemd user service

The sidecar repository ships a user-service unit under `deploy/`. From the cloned
sidecar checkout:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/hermes-usage-sidecar.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now hermes-usage-sidecar.service
```

Review the unit before enabling it so the token source, Hermes home, bind
address, and port match your environment. The shipped unit is designed to bind to
`127.0.0.1`, mount `~/.hermes` read-only, and keep sidecar-owned state under
`~/.local/state/hermes-usage-sidecar`.

## Run with Docker

Docker is the secondary deployment option. Build the image from the sidecar
checkout and mount Hermes read-only:

```bash
docker build -t hermes-usage-sidecar .
docker run --rm -p 127.0.0.1:8799:8799 \
  -e USAGE_SIDECAR_TOKEN="$USAGE_SIDECAR_TOKEN" \
  -v "$HOME/.hermes:/hermes:ro" \
  -v "$HOME/.local/state/hermes-usage-sidecar:/state" \
  hermes-usage-sidecar
```

Keep the bind address local unless you have a trusted network boundary or a
reverse proxy enforcing access controls. The bearer token protects the endpoint,
but the service still exposes usage metadata.

## Verify the sidecar

Both verification endpoints require the bearer token.

```bash
curl -fsS \
  -H "Authorization: Bearer $USAGE_SIDECAR_TOKEN" \
  http://127.0.0.1:8799/healthz
```

Then verify that Usage Dashboard's `/usage` contract returns observations and a
watermark:

```bash
curl -fsS \
  -H "Authorization: Bearer $USAGE_SIDECAR_TOKEN" \
  http://127.0.0.1:8799/usage
```

If `/usage` returns an empty `observations` array, the connection can still be
valid; it may simply mean Hermes has no new usage deltas since the sidecar's
current watermark.

## Add it to Usage Dashboard

1. Open **Settings → Data sources**.
2. Click **Add Hermes source**.
3. Set **Hermes sidecar base URL** to the URL Usage Dashboard can reach, for
   example `http://127.0.0.1:8799` for same-host installs.
4. Paste the bearer token from `USAGE_SIDECAR_TOKEN`.
5. Leave **Profiles** blank to ingest all discovered profiles, or enter a
   comma-separated allowlist such as `default,coder`.
6. Add **Provider mappings** only when Hermes provider identifiers do not match
   your Usage Dashboard provider ids. Use `hermes-provider=dashboard-provider`,
   comma-separated; for example `openrouter=openrouter,anthropic=anthropic`.
7. Choose a polling interval, then click **Connect**.
8. Use **Test connection** to confirm the dashboard can call the sidecar.

Use one sidecar/data-source pair per Hermes installation.

## Docker and networking

Container networking is the common trap. If Usage Dashboard runs in Docker,
`127.0.0.1` from inside the dashboard backend container means the dashboard
container itself, not the host running Hermes.

Choose a URL based on where the sidecar is reachable from the Usage Dashboard
backend:

- Same host, no containers: `http://127.0.0.1:8799`.
- Usage Dashboard in Docker, sidecar on the Docker host: use the host address
  reachable from the container, such as a LAN IP, Docker bridge gateway, or a
  Compose network alias.
- Sidecar in the same Compose project: put both services on the same Compose
  network and use `http://<sidecar-service-name>:8799`.
- Reverse-proxied sidecar: use the internal or external HTTPS URL and keep bearer
  token authentication enabled.

If you bind the sidecar to anything broader than `127.0.0.1`, restrict access at
the firewall or reverse proxy and treat the bearer token as a secret.

## Troubleshooting

### `401 Unauthorized`

The dashboard token does not match the sidecar token. Recheck
`USAGE_SIDECAR_TOKEN` or the configured `--token-file`, then update the data
source token in Usage Dashboard.

### Connection refused or timeout

The sidecar is not reachable from the Usage Dashboard backend. Check that the
sidecar process is running, confirm the bind address and port, and remember that
container `127.0.0.1` is not the host loopback address.

### Schema or compatibility error

The sidecar validates supported Hermes `state.db` schemas and returns explicit
compatibility errors rather than guessing. Update the sidecar from
[Skulldorom/hermes-usage-sidecar](https://github.com/Skulldorom/hermes-usage-sidecar)
and verify the Hermes version/schema it supports.

### No records imported

Run the `/usage` curl command directly. If the response is valid but empty,
Hermes may not have new usage deltas for the current watermark, the selected
profile filter may exclude the active profile, or provider mappings may not line
up with configured providers.

## Contract reference

For the exact JSON shapes Usage Dashboard accepts, see
[Data sources: HTTP contract](/configuration/data-sources.html#http-contract).
The sidecar is the supported implementation for Hermes Agent today; detailed
sidecar internals and development notes remain canonical in the
[sidecar repository](https://github.com/Skulldorom/hermes-usage-sidecar).
