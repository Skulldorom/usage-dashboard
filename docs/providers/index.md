# Providers

Usage Dashboard ships with adapters for the providers below. Each adapter knows
the provider's usage/balance endpoint and how to surface the important metrics
on the dashboard.

| Provider | Endpoint | Credential |
| --- | --- | --- |
| [Firecrawl](/providers/firecrawl) | Team credit usage | Firecrawl API key |
| [DeepSeek](/providers/deepseek) | Account balance | DeepSeek API key |
| [OpenAI](/providers/openai) | Organization costs | Organization admin key |
| [Anthropic / Claude](/providers/anthropic) | Usage & Cost Admin API | Anthropic Admin API key |
| [OpenRouter](/providers/openrouter) | API key usage | OpenRouter API key |
| [OpenAI Codex](/providers/codex) | ChatGPT wham usage | ChatGPT OAuth tokens |
| [Custom HTTP](/providers/custom-http) | User-defined | Bearer/auth header |

Credentials are encrypted at rest with Fernet before being written to the
database.

## Adding a provider

1. Open **Settings** in the dashboard.
2. Choose the provider, paste the credential, and save.
3. The backend polls the provider on the configured interval; you can also poll
   immediately from the dashboard.
