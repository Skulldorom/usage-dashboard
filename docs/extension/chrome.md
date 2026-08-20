# Chrome & Brave

The extension is published to the Chrome Web Store, and Brave (a Chromium-based
browser) installs from the same listing.

## Install

1. Open the [Chrome Web Store listing](https://chromewebstore.google.com/detail/lajooelgpfeholbdkmammfladpefohgk).
2. Click **Add to Chrome** (or **Add to Brave**).
3. Pin the extension to the toolbar.

## Configure

The extension needs the URL of your Usage Dashboard instance before either setup
path can work:

1. Sign in to your dashboard and open **Settings → Integrations → Browser
   extension**.
2. Copy the dashboard URL shown there.
3. Open the extension **Options** page and paste the dashboard URL.
4. Return to the dashboard and choose a setup path:
   - **One-click setup**: use **Connect extension** to create and send a scoped
     token automatically.
   - **Manual setup**: use **Manual setup** to create a token, then paste it in
     the extension Options page yourself.

Manual tokens should use [API token](/configuration/api-tokens) scopes
`usage:read`, `poll:write`, and `configs:read`.

## Unpacked / dev builds

For local development, load an unpacked build and point the frontend at it with
`EXTENSION_TARGET_CHROME_ID`. See
[Browser Extension](/integrations/browser-extension).
