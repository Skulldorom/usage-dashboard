# Usage Dashboard Extension - Privacy Policy

Last updated: 2026-08-25

This policy describes how the **Usage Dashboard** browser extension ("the
extension") handles data. The extension is a companion client for a self-hosted
[Usage Dashboard](https://github.com/Skulldorom/usage-dashboard) instance that
**you** operate.

## Data stored locally

The extension stores the following information on your device using
`chrome.storage.local` (local browser storage only - **not**
`chrome.storage.sync`, and never sent to any server operated by the extension
developer):

- The **Usage Dashboard URL** you configure (the main address of your own instance).
- Your **bearer authentication token** for that instance.
- Your **refresh interval** and **auto-poll** preferences.
- A short-lived **cache** of provider usage/status data retrieved from your
  instance, used to render the popup quickly.
- **Popup presentation preferences**, such as which providers are pinned or
  hidden and a preferred metric per provider.
- **Popup filter and sort** preferences.
- **Alert dismissal state**, so acknowledged alerts stay acknowledged.
- **Notification preferences** and **notification deduplication / last-seen
  state** (see below).
- **Connection-health state**, including whether the last sync succeeded and the
  timestamp of the last successful sync.
- Other minimal local state needed for polling and popup presentation.

None of this data is transmitted to the extension developer or any third party.
Locally stored data is required for the extension to function; it is **not**
collected by the extension developer.

## Browser notifications

If you enable browser notifications, the extension may display local browser
notifications when configured usage thresholds are reached (warning, critical,
or exhausted) or when a configured provider becomes unavailable. Notifications
are **optional** and **off by default**. The extension requests the browser
notification permission only after you enable the feature, and you can disable
notifications at any time in extension settings.

Notifications are driven by **state changes** rather than sent on every polling
cycle, so a provider that remains in the same state does not repeat its
notification. Clicking a provider notification opens the Usage Dashboard you
configured.

Notification preferences and notification state are stored locally in the
browser. Notification information is not transmitted to the extension developer
or to third-party analytics or advertising services. Sensitive values such as
bearer tokens are never included in notification text.

## Provider diagnostics and error information

Provider or API error information may be temporarily cached and displayed
locally in the popup to help you troubleshoot your own self-hosted Usage
Dashboard connection and providers. This error/diagnostic information is stored
and shown only in your browser.

The extension does not intentionally transmit provider errors to the extension
developer, and it uses no telemetry or crash-reporting service. Sensitive values
such as bearer tokens are excluded from notifications and from displayed
diagnostic information.

## What data the extension sends, and where

The extension only makes network requests to the **single server origin you
configure** - your own Usage Dashboard instance. Specifically, it calls:

- `GET /api/v1/usage`
- `GET /api/v1/providers`
- `GET /api/v1/poll/status`
- `POST /api/v1/poll` (scheduled/manual refresh)
- `POST /api/v1/configs/{id}/poll` (per-provider refresh)

Your bearer token is sent **only** to the server origin you explicitly configure
and authorize. It is never sent anywhere else.

Normal extension operation does **not** route your dashboard credentials, usage
data, or provider information through infrastructure operated by the extension
developer. The only data flow is directly between the extension and the Usage
Dashboard instance you configure.

## Host access

The extension declares `http://*/*` and `https://*/*` as **optional** host
permissions and requests access **only** to the origin of the Usage Dashboard URL
you enter. If you decline, the extension cannot contact your dashboard.

## One-click dashboard setup

A Usage Dashboard page can initiate a one-click setup handshake with the
extension. The external API is deliberately minimal and write-only:

- `usage-dashboard:ping` lets a dashboard page check protocol compatibility
  before creating credentials.
- `usage-dashboard:configure` lets that same page send a bearer token for its own
  origin.

The extension derives the dashboard URL from the sending page's browser-provided
origin. It does **not** trust a dashboard URL supplied in the message body, and
external pages cannot read the stored dashboard URL, token, cached usage,
provider data, or extension settings. If the extension is already connected to a
different dashboard origin, replacement requires explicit confirmation in the
dashboard flow before the extension overwrites the saved connection.

## Telemetry, analytics, and tracking

The extension does **not** collect analytics, usage telemetry, or crash reports,
and does **not** use tracking, advertising, or any third-party telemetry or
crash-reporting service. No data is transmitted to the developer or any third
party.

## Data retention and deletion

All stored data lives in `chrome.storage.local` and is removed when you clear the
extension's data or uninstall it. To delete your token at any time, open the
extension's **Options** page and click **Clear token**.

## Contact

For questions about this policy or the extension, open an issue in the
[Usage Dashboard](https://github.com/Skulldorom/usage-dashboard) repository.
