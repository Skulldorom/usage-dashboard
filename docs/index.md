---
layout: home

hero:
  name: Usage Dashboard
  text: Self-hosted API usage monitoring
  tagline: Monitor provider balances, polling health, and Homepage widget data from one self-hosted dashboard.
  image:
    src: /screenshot.png
    alt: Usage Dashboard screenshot
  actions:
    - theme: brand
      text: Get Started
      link: /getting-started/installation
    - theme: alt
      text: Documentation
      link: /getting-started/
    - theme: alt
      text: GitHub
      link: https://github.com/Skulldorom/usage-dashboard

features:
  - title: Encrypted credentials
    details: Provider API keys are encrypted at rest with Fernet before they ever touch the database.
  - title: Multi-provider usage
    details: Track balances and usage across Firecrawl, DeepSeek, OpenAI, Anthropic/Claude, OpenRouter, Codex, and custom HTTP endpoints.
  - title: Homepage Dashboard widget
    details: A flat JSON endpoint for the popular Homepage dashboard, with dynamic per-provider rows.
  - title: Browser extension
    details: A Manifest V3 companion for Chrome and Brave that puts provider usage in your toolbar.
---

## Supported providers

Usage Dashboard ships with adapters for:

- [Firecrawl](/providers/firecrawl)
- [DeepSeek](/providers/deepseek)
- [OpenAI](/providers/openai)
- [Anthropic / Claude](/providers/anthropic)
- [OpenRouter](/providers/openrouter)
- [OpenAI Codex](/providers/codex)
- [Custom HTTP](/providers/custom-http)

Provider credentials are stored encrypted at rest, and the backend polls each
provider's usage/balance API on a configurable interval.

## Integrations

- **[Homepage Dashboard](/integrations/homepage)** — expose a flat JSON payload for the Homepage dashboard's `customapi` widget.
- **[Browser Extension](/integrations/browser-extension)** — a Chrome/Brave companion that surfaces usage in a toolbar popup, with one-click setup from the dashboard.

## Start here

- **[Installation](/getting-started/installation)** — Docker Compose quick start.
- **[First-run setup](/getting-started/first-run)** — create the admin password.
- **[Configuration](/configuration/environment)** — environment variable reference.
