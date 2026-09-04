# Homepage Dashboard widget

The Compose stack no longer has a separate `nginx` service. The `frontend`
service is the nginx-based static frontend **and** API proxy. Use the URL that
matches where Homepage is running:

- **Same Docker Compose project/network**: `http://frontend/api/v1/homepage`
- **Separate Compose project on a shared network**: connect Homepage to the
  Usage Dashboard network and use `http://frontend/api/v1/homepage`, or add a
  network alias such as `usage-dashboard` and use
  `http://usage-dashboard/api/v1/homepage`
- **Host/LAN access through the published port**:
  `http://<server-ip-or-dns>:${NGINX_HTTP_PORT:-3000}/api/v1/homepage`
- **Public reverse-proxy access**: `https://usage.example.com/api/v1/homepage`

If you use `HOMEPAGE_ALLOWED_HOSTS`, include the hostname that reaches the
frontend/proxy and is forwarded to the backend. For internal Docker calls that
is usually `frontend` or your network alias; for public access it is your
external hostname.

Two widget formats are supported. The UI generator defaults to the dynamic
provider list because it matches the dashboard provider rows.

## Option A - Dynamic list (one row per provider)

Recommended default. Requires Homepage >= 1.1.0. Set `display: dynamic-list` and
use the object-style `mappings` below. Each enabled provider config becomes a row
with its canonical provider name on the left and usage-left text on the right.
When more than one enabled configuration exists for the same provider, the
custom configuration label is added in parentheses to distinguish the rows.

```yaml
- API Usage:
    icon: mdi-api
    widget:
      type: customapi
      url: http://frontend/api/v1/homepage
      display: dynamic-list
      # Optional when HOMEPAGE_ALLOWED_HOSTS includes frontend; otherwise use a scoped token with usage:read.
      # headers:
      #   Authorization: Bearer <token>
      refreshInterval: 300000
      mappings:
        items: list
        name: label
        label: value
        format: text
```

`display: dynamic-list` is mandatory - omitting it causes
`TypeError: s.slice is not a function` because Homepage tries to treat the
object-style mappings as a block-display array.

The `list` array contains one flat object per enabled provider config:

- `label` → left side (for example `DeepSeek` for one configuration, or
  `DeepSeek (work)` and `DeepSeek (personal)` when duplicate configurations
  need disambiguation)
- `value` → right side (prefers remaining credits/usage, then percent-used, then
  summary fallback)

The existing scalar fields (`summary`, `configured_providers`,
`healthy_providers`, `degraded_providers`) and flattened `metrics` object remain
in the response for use with Option B or extra mappings.

## Option B - Block display (scalar fields)

The `block` display shows individual fields as labelled rows. Use this for a
compact summary tile:

```yaml
- API Usage:
    icon: mdi-api
    widget:
      type: customapi
      url: http://frontend/api/v1/homepage
      # Optional when HOMEPAGE_ALLOWED_HOSTS includes frontend; otherwise use a scoped token with usage:read.
      # headers:
      #   Authorization: Bearer <token>
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

Flattened `metrics` keys (e.g. `firecrawl_main_credits_remaining`,
`deepseek_main_total_balance`) are also available as extra `field` mappings.
These keys continue to include the configuration label for backward
compatibility, even when the visible dynamic-list row only shows the canonical
provider name.

## Public homepage behind reverse-proxy auth

Set `HOMEPAGE_ALLOWED_HOSTS` when a trusted proxy such as Authentik protects the
public hostname and you only want the flat homepage payload to be readable
without sharing a bearer token:

```bash
HOMEPAGE_ALLOWED_HOSTS=usage.example.com,status.local
```

Only `GET /api/v1/homepage` checks this allowlist. Without the allowlist,
Homepage can also use a scoped API token with `usage:read`. `/configs`, `/poll`,
`/usage`, and history endpoints still require a valid admin session or scoped
API token with the matching route scope. Hostnames are matched
case-insensitively and any port suffix is ignored.
