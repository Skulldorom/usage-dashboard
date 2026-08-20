# Integrations

Usage Dashboard exposes two integrations beyond the main dashboard UI:

- **[Homepage Dashboard](/integrations/homepage)** - a flat JSON endpoint for the
  popular Homepage dashboard's `customapi` widget, with dynamic per-provider rows.
- **[Browser Extension](/integrations/browser-extension)** - a Manifest V3
  companion for Chrome and Brave that surfaces usage in a toolbar popup, with
  one-click setup from the dashboard.

Both are read-mostly and authenticate with scoped API tokens (or, for the
Homepage widget, an allowlisted host).
