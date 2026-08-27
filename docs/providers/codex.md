# OpenAI Codex

The Codex provider reads your ChatGPT Codex rate-limit windows through the
official ChatGPT OAuth flow. Because there is no personal usage API key, the
provider authenticates with OAuth tokens instead.

## Endpoint

Usage Dashboard queries `GET /chatgpt.com/backend-api/wham/usage` with the OAuth
access token and the `OpenAI-Beta: codex-1` header.

## Authentication

On the Settings page, choose **OpenAI Codex** and follow the OAuth handshake.
Access and refresh tokens are stored **encrypted** in the provider secret and are
refreshed automatically before they expire.

## Metrics

- `plan_type` - your Codex plan.
- `session_remaining_percent` / `session_reset_at` - remaining in the current session window.
- `weekly_remaining_percent` / `weekly_reset_at` - remaining in the weekly window.
- `reset_credits_available` - credits available for a rate-limit reset.
- `limit_reached` - whether the current window is exhausted.
- `review_session_remaining_percent` / `review_weekly_remaining_percent` - code review windows, when present.

The provider card groups the session (5-hour) and weekly limits into usage-window
sections that show the remaining percentage, a progress bar, and a "Resets …"
timestamp in the viewer's local timezone whenever the provider supplies one.

## Notes

- If the OAuth token is rejected (401/403), re-authorize the Codex provider from
  Settings.
- Refresh tokens that expire cannot be silently recovered - re-run the OAuth
  handshake to reconnect.
