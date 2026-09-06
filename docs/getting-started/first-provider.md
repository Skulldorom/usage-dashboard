# Connect your first provider

After creating the admin password, open **Settings** and select **Add provider**.

1. Choose the provider type. The setup panel explains which credential it
   requires; Codex uses an OAuth flow instead of a normal API key.
2. Leave **Connection label** blank for an automatically unique label, or enter
   a useful identity such as `work`.
3. Keep the provider default endpoint unless you use a compatible proxy or
   self-hosted endpoint.
4. Choose the way you actually pay: PAYG, Subscription, or Free. For a
   subscription, add amount, currency, cadence, and preferably a billing anchor.
5. Test the connection. A successful test reads current usage but does not save
   another connection by itself.
6. Save, then use **Retry**/poll if you want an immediate stored reading.

The provider appears on the Dashboard after a successful collection. Historical
analytics accumulate from polling; providers with native history may populate
dated buckets immediately.

Next, read [Connected providers](../configuration/connected-providers.md) for
visibility, ordering, duplicate connections, thresholds, and health, then
[Usage & analytics](../using/usage-and-analytics.md).
