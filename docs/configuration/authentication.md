# Authentication

There are two ways to authenticate against the API:

1. **Admin password login** - the browser UI signs in with a password and holds a
   session token.
2. **Scoped API tokens** - bearer tokens with a limited set of scopes, for
   integrations such as the Homepage widget or the browser extension.

## Admin sessions

Password login returns a bearer session token. Sessions are validated against a
per-credential token list and expire after `ADMIN_SESSION_EXPIRE_HOURS`
(default `24`).

- `POST /api/v1/auth/login` - sign in with the admin password.
- `POST /api/v1/auth/logout` - revoke the current session.

## First-run and reset codes

The admin password is created via a one-time code, and resets follow the same
pattern. See [First-run setup](/getting-started/first-run).

## How endpoints are protected

- Admin-only routes (creating/configuring providers, managing API tokens,
  Codex OAuth) require an admin session.
- Read routes are protected by scoped API tokens via the
  [`require_scope`](/configuration/api-tokens) dependency.
- `GET /api/v1/homepage` can additionally be exposed to trusted hosts without a
  token via `HOMEPAGE_ALLOWED_HOSTS` - see
  [Homepage Dashboard](/integrations/homepage).
