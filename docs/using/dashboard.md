# Dashboard

The Dashboard is the current-state view. Each card represents one configured
provider connection and shows its latest successful reading.

## Reading a provider card

A card can contain a balance, usage total, one or more quota windows, a summary,
and a last-refresh time. Providers expose different metrics, so cards are not
expected to look identical.

Quota-based providers show each independent window separately. For example,
OpenAI Codex can show **Session** and **Weekly**, while OpenCode Go can show
**Session**, **Weekly**, and **Monthly**. A missing window is omitted; it is not
shown as 0%.

Provider cards use the canonical provider name, such as **OpenAI Codex**. A
configuration label is added when multiple connections of the same provider
must be distinguished, such as **OpenAI Codex - work** and
**OpenAI Codex - personal**.

## Visibility and ordering

The Dashboard follows the order and **UI** visibility configured under
**Settings → Connected providers**. UI visibility only controls the main
Dashboard. The separate **API** switch controls polling and API/Homepage output.

## Warnings

A warning means the latest provider state, health, or configured threshold needs
attention. A failed refresh does not overwrite the last successful reading with
zero. See [Provider health & errors](./provider-health.md) to distinguish stale
last-known-good data from a provider with no usable result.

For historical analysis, open [Usage & analytics](./usage-and-analytics.md).
