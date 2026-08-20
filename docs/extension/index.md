# Browser Extension - Getting Started

The Usage Dashboard extension is a companion client for a self-hosted Usage
Dashboard instance that **you** operate. It shows provider usage and polling
status in a toolbar popup without opening the dashboard.

## What it does

- Reads current usage and polling status from your instance.
- Triggers scheduled and manual polls.
- Supports one-click setup from a signed-in dashboard page.

## Availability

| Browser        | Status                                   |
| -------------- | ---------------------------------------- |
| Chrome         | Live - Chrome Web Store                  |
| Brave          | Live - same Web Store listing (Chromium) |
| Firefox        | Roadmap - WebExtension port              |
| Microsoft Edge | Roadmap - Chromium                       |
| Opera          | Roadmap - Chromium                       |
| Safari         | Roadmap - Web Extension conversion       |

## Connect

1. [Install the extension](/extension/chrome) for your browser.
2. Open your Usage Dashboard settings and copy the dashboard URL from the
   Browser extension card.
3. Open the extension **Options** page and paste that dashboard URL. This tells
   the extension which self-hosted instance is allowed to use one-click setup.
4. Return to the dashboard and use **Connect extension**, or use **Manual setup**
   to create and paste a bearer token yourself.

The extension makes requests only to the single server origin you configure. See
the [privacy policy](/extension-privacy) for exactly what data it stores and
sends.
