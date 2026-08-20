# Browser Extension

The Usage Dashboard browser extension is a Manifest V3 companion that puts
provider usage in your toolbar. It talks only to your own self-hosted instance.

- **Status**: [Chrome & Brave](/extension/chrome) are live in the Chrome Web
  Store. Firefox, Edge, Opera, and Safari builds are on the roadmap.
- **Getting started**: see the [extension guide](/extension/).
- **Privacy**: the extension stores data locally and sends it only to your own
  instance — see the [privacy policy](/extension-privacy).

## One-click setup

Before using one-click setup, copy the dashboard URL from **Settings →
Integrations → Browser extension** and paste it into the extension Options page.
That saved URL tells the extension which self-hosted instance may configure it.

A signed-in dashboard page can then hand off a connection to the extension through
a minimal, write-only external API:

- `usage-dashboard:ping` — check protocol compatibility before creating credentials.
- `usage-dashboard:configure` — send a bearer token for the page's own origin.

The extension derives the dashboard URL from the sending page's browser-provided
origin and never trusts a URL supplied in the message body.

## Overriding extension IDs (dev/testing)

The frontend resolves browser extension IDs at runtime through
`/runtime-config.js`, so you can test unpacked/dev builds without rebuilding the
GHCR image. Set the matching variable in `.env` and restart the frontend:

```bash
EXTENSION_TARGET_CHROME_ID=<dev-extension-id>
```

Available variables: `EXTENSION_TARGET_CHROME_ID`, `EXTENSION_TARGET_EDGE_ID`,
`EXTENSION_TARGET_OPERA_ID`, `EXTENSION_TARGET_FIREFOX_ID`, and
`EXTENSION_TARGET_SAFARI_ID`. See
[environment variables](/configuration/environment).
