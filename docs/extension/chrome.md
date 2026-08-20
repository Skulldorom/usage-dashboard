# Chrome & Brave

The extension is published to the Chrome Web Store, and Brave (a Chromium-based
browser) installs from the same listing.

## Install

1. Open the [Chrome Web Store listing](https://chromewebstore.google.com/detail/lajooelgpfeholbdkmammfladpefohgk).
2. Click **Add to Chrome** (or **Add to Brave**).
3. Pin the extension to the toolbar.

## Configure

The extension needs the URL of your Usage Dashboard instance and a bearer token:

- **One-click setup**: sign in to your dashboard and use the **Connect
  extension** button.
- **Manual setup**: open the extension **Options** page and enter the dashboard
  URL plus an [API token](/configuration/api-tokens) with `usage:read` and
  `poll:write` scopes.

## Unpacked / dev builds

For local development, load an unpacked build and point the frontend at it with
`EXTENSION_TARGET_CHROME_ID`. See
[Browser Extension](/integrations/browser-extension).
