# API tokens

API tokens are scoped bearer tokens for integrations. They are created from the
Settings page (or the API) and are stored hashed at rest, so the plaintext token
is only shown once at creation.

Tokens use a `udt_` prefix and can carry one or more scopes.

## Scopes

| Scope | Grants |
| --- | --- |
| `configs:read` | `GET /configs` — list provider configurations. |
| `history:read` | `GET /configs/{id}/history` — read usage history for a provider. |
| `poll:write` | `POST /poll`, `POST /configs/{id}/poll`, `GET /poll/status` — trigger and read polls. |
| `usage:read` | `GET /usage` and `GET /homepage` — read current usage and the Homepage payload. |

## Managing tokens

Tokens are managed by admin routes:

- `GET /api/v1/api-tokens` — list tokens.
- `POST /api/v1/api-tokens` — create a token with a name, scopes, and optional expiry.
- `POST /api/v1/api-tokens/{token_id}/revoke` — revoke a token.

Revoked and expired tokens are rejected on validation.

## Example

Create a token that can only read usage for the Homepage widget:

```json
{
  "name": "homepage-widget",
  "scopes": ["usage:read"]
}
```

Then use it as a bearer token in the widget config:

```yaml
headers:
  Authorization: Bearer udt_<token>
```
