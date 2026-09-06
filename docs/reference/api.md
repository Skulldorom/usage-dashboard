# API reference

All paths below are relative to `/api/v1`. Admin sessions are allowed; API token
requests need the scope noted by each group.

## Current usage and providers

| Endpoint | Purpose | Scope |
| --- | --- | --- |
| `GET /providers` | Supported provider catalogue and capabilities | Public |
| `GET /configs` | Connection metadata | `configs:read` |
| `GET /configs/{id}/history` | Saved provider snapshots | `history:read` |
| `POST /configs/{id}/poll` | Poll one connection | `poll:write` |
| `POST /poll` | Poll all enabled connections | `poll:write` |
| `GET /poll/status` | Poll scheduler status | `poll:write` |
| `GET /usage` | Latest state, health, and last-known-good data | `usage:read` |
| `GET /homepage` | Flat Homepage Dashboard payload | allowed host or `usage:read` |

Configuration creation, update, ordering, deletion, credential testing, Codex
OAuth, and API-token management require an admin session.

## Analytics

All analytics endpoints require `analytics:read`.

| Endpoint | Important parameters |
| --- | --- |
| `GET /analytics/summary` | — |
| `GET /analytics/overview` | `from`, `to`, `interval=hour|day|week`, `timezone` |
| `GET /analytics/economics` | `from`, `to`, `provider`, `config_id` |
| `GET /analytics/providers/{id}` | — |
| `GET /analytics/providers/{id}/capacity` | `metric`, `timezone` |
| `GET /analytics/providers/{id}/timeseries` | `metric`, `interval`, `from`, `to`, `timezone` |
| `GET /analytics/providers/{id}/daily` | `metric`, `from`, `to`, `timezone` |
| `GET /analytics/providers/{id}/hourly` | `metric`, `date`, `timezone` |
| `GET /analytics/providers/{id}/forecast` | `metric`, `timezone` |
| `GET /analytics/providers/{id}/comparison` | `metric`, `window=day|week|month`, `timezone` |
| `GET /analytics/providers/{id}/attribution` | `from`, `to` |
| `GET /analytics/hermes` | `from`, `to`, `provider` |

`from` and `to` are ISO-8601 datetimes. `timezone` is an IANA timezone name;
the frontend sends the browser's local timezone for calendar grouping.

## Data sources

`GET /datasources/configs`, observations, and status require
`datasources:read`. Create, update, delete, test, sync, and provider-mapping
operations require an admin session.

| Endpoint | Purpose |
| --- | --- |
| `GET /datasources/configs/{id}/observations` | Inspect recent ingested records and aliases |
| `GET /datasources/configs/{id}/status` | Sync health and diagnostics |
| `GET /datasources/configs/{id}/provider-mappings` | Inspect Hermes provider mappings (admin) |
| `PUT /datasources/configs/{id}/provider-mappings` | Replace/update Hermes provider mappings (admin) |
| `POST /datasources/configs/{id}/test` | Test without saving observations (admin) |
| `POST /datasources/configs/{id}/sync` | Sync immediately (admin) |

Use the generated OpenAPI document exposed by the running backend for complete
request and response schemas. API consumers should preserve `null` as missing;
do not coerce it to zero.
