# Connected providers

Use **Settings → Connected providers** to add, order, enable, label, and maintain
provider connections.

## Add a connection

1. Select **Add provider** and choose a provider type.
2. Enter its credential or complete the Codex OAuth flow.
3. Optionally set a connection label and base URL override.
4. Choose PAYG, Subscription, or Free billing.
5. Test the connection, then save it.

Credentials are encrypted before storage and are returned only as masked text.
The replace-credential action overwrites the old secret without displaying it.

## Names and duplicate providers

The canonical name identifies the adapter, for example **Anthropic / Claude** or
**OpenAI Codex**. The connection label identifies a particular configuration.
Leave it blank to generate a unique label, or use a meaningful value such as
`work` or `personal`.

When only one connection exists, user-facing views normally use the canonical
name. When multiple configurations use the same provider, labels disambiguate
them, for example **DeepSeek - work** and **DeepSeek - personal**.

## Row controls

| Control | Effect |
| --- | --- |
| Reorder / drag | Changes provider order in Settings and consumers that honor display order. Keyboard-friendly up/down buttons are also available. |
| API | Enables polling and inclusion in API/Homepage output. Disabling it stops those behaviors. |
| UI | Shows or hides the connection on the main Dashboard. It does not disable polling. |
| Key | Replaces or reauthorizes the credential. |
| `$` | Opens billing configuration. |
| Bell | Configures warning, critical, and exhausted thresholds for supported metrics. |
| Trash | Permanently removes the connection and its associated configuration. |

The row also shows the masked credential, default or overridden endpoint,
billing model, thresholds, and health warnings. Use the warning's **Retry**
button for an immediate collection attempt.

See [Billing configuration](./billing.md), [Automatic polling](./polling.md), and
[Provider health & errors](../using/provider-health.md).
