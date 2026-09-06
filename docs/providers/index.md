# Providers

Usage Dashboard ships with eight provider adapters. Provider support differs:
some expose historical usage/cost, while others expose only a current balance
or quota. Hermes can supplement workload detail but does not change what the
provider API authoritatively reports.

| Provider | Native usage/quota source | Native monetary history | Recommended billing | Hermes pricing fallback / limitation |
| --- | --- | --- | --- | --- |
| [OpenAI](/providers/openai) | Organization daily cost buckets | Yes | PAYG | Requires an organization admin key; provider cost is authoritative. |
| [Anthropic / Claude](/providers/anthropic) | Hourly Usage Admin API | Yes, best-effort Cost Admin API | PAYG | Admin key required; token usage remains available if cost enrichment fails. Priority Tier cost is not included by the provider cost endpoint. |
| [DeepSeek](/providers/deepseek) | Current account balance | No | PAYG | Price model/token telemetry when coverage is sufficient; balance is not historical spend. |
| [OpenRouter](/providers/openrouter) | Key limit and rolling daily/weekly/monthly usage | No arbitrary-range billing history | PAYG or actual plan | Hermes estimate needs a known model and token-class coverage; credit state is not automatically USD spend. |
| [Firecrawl](/providers/firecrawl) | Team credit state and historical credit periods | Credit history, not monetary billing | Match actual plan | Credits are not assumed to equal currency; token pricing does not apply. |
| [OpenAI Codex](/providers/codex) | ChatGPT OAuth session/weekly quotas | No | Subscription | Hermes can price attributed model/token workload as API-equivalent value. |
| [OpenCode Go](/providers/opencode-go) | Subscription 5h/weekly/monthly windows and model usage | No | Subscription | Allowance values are not PAYG spend; Hermes pricing depends on model coverage. |
| [Custom HTTP](/providers/custom-http) | Operator-defined JSON metrics | Only when compatible monetary deltas are returned | Match upstream | Generic point history; advanced semantics are limited. |

Credentials are encrypted at rest with Fernet before being written to the
database.

## Adding a provider

1. Open **Settings** in the dashboard.
2. Choose the provider, add its credential, label, and billing model, then test
   and save.
3. The backend polls the provider on the configured interval; you can also poll
   immediately from the dashboard.

See [Connected providers](/configuration/connected-providers) for labels,
visibility, ordering, health, and credential replacement.
