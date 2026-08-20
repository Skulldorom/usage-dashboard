# Usage Dashboard Extension - Privacy Policy

Last updated: 2026-08-20

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

None of this data is transmitted to the extension developer or any third party.

## What data the extension sends, and where

The extension only makes network requests to the **single server origin you
configure** - your own Usage Dashboard instance. Specifically, it calls:

- `GET /api/v1/usage`
- `GET /api/v1/poll/status`
- `POST /api/v1/poll` (scheduled/manual refresh)
- `POST /api/v1/configs/{id}/poll` (per-provider refresh)

Your bearer token is sent **only** to the server origin you explicitly configure
and authorize. It is never sent anywhere else.

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
and does **not** use tracking or advertising. No data is transmitted to the
developer or any third party.

## Data retention and deletion

All stored data lives in `chrome.storage.local` and is removed when you clear the
extension's data or uninstall it. To delete your token at any time, open the
extension's **Options** page and click **Clear token**.

## Contact

For questions about this policy or the extension, open an issue in the
[Usage Dashboard](https://github.com/Skulldorom/usage-dashboard) repository.
