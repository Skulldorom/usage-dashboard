# Custom HTTP

The Custom HTTP provider queries any user-defined HTTP endpoint and extracts
metrics from the JSON response using JSON paths.

## Configuration

Choose **Custom HTTP** in Settings and provide:

- **Base URL** - the absolute endpoint host, e.g. `https://api.example.com`.
- **Path** - the relative path, e.g. `/v1/billing`.
- **Method** - `GET` or `POST`.
- **Auth header** - header name and template. The encrypted API key is inserted
  via the `{api_key}` placeholder.
- **Metrics** - one or more `{ label, path, unit, maximum_path }` entries.

## Example metric config

```json
{
  "method": "GET",
  "path": "/v1/billing",
  "auth_header_name": "Authorization",
  "auth_header_template": "Bearer {api_key}",
  "metrics": [
    {
      "label": "remaining",
      "path": "$.credits.remaining",
      "unit": "credits",
      "maximum_path": "$.credits.limit"
    }
  ]
}
```

## Security

- Secrets must not go in the base URL or path - the backend rejects
  credential-looking URLs and paths.
- The host must be a public hostname. Requests to `localhost` or to hosts that
  resolve to private, loopback, link-local, reserved, or multicast addresses are
  rejected to prevent SSRF.
- To allow a specific internal host, add it to `CUSTOM_HTTP_ALLOWED_HOSTS`.

## JSON paths

Metric paths use a small JSON-path dialect starting with `$`, e.g.
`$.credits.remaining` or `$.items[0].value`. Unsupported or non-matching paths
return no value rather than raising.
