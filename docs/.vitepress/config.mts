import { defineConfig } from 'vitepress'

// https://vitepress.dev/reference/site-config
export default defineConfig({
  lang: 'en-US',
  title: 'Usage Dashboard',
  description:
    'Self-hosted API usage dashboard for Firecrawl, DeepSeek, OpenAI, Anthropic/Claude, OpenRouter, OpenAI Codex, and custom HTTP endpoints.',
  base: '/usage-dashboard/docs/',
  cleanUrls: false,
  lastUpdated: true,
  appearance: 'dark',
  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/usage-dashboard/docs/logo.svg' }],
  ],

  themeConfig: {
    logo: '/logo.svg',
    nav: [
      { text: 'Home', link: 'https://skulldorom.github.io/usage-dashboard/' },
      { text: 'Browser Extension', link: '/extension/' },
      { text: 'GitHub', link: 'https://github.com/Skulldorom/usage-dashboard' },
    ],
    sidebar: [
      {
        text: 'Getting Started',
        collapsed: false,
        items: [
          { text: 'Introduction', link: '/getting-started/' },
          { text: 'Installation', link: '/getting-started/installation' },
          { text: 'First-run setup', link: '/getting-started/first-run' },
          { text: 'Updating', link: '/getting-started/updating' },
        ],
      },
      {
        text: 'Configuration',
        collapsed: false,
        items: [
          { text: 'Environment variables', link: '/configuration/environment' },
          { text: 'Authentication', link: '/configuration/authentication' },
          { text: 'API tokens', link: '/configuration/api-tokens' },
          { text: 'Automatic polling', link: '/configuration/polling' },
        ],
      },
      {
        text: 'Providers',
        collapsed: false,
        items: [
          { text: 'OpenAI', link: '/providers/openai' },
          { text: 'Anthropic', link: '/providers/anthropic' },
          { text: 'DeepSeek', link: '/providers/deepseek' },
          { text: 'OpenRouter', link: '/providers/openrouter' },
          { text: 'Firecrawl', link: '/providers/firecrawl' },
          { text: 'OpenAI Codex', link: '/providers/codex' },
          { text: 'Custom HTTP', link: '/providers/custom-http' },
        ],
      },
      {
        text: 'Integrations',
        collapsed: false,
        items: [
          { text: 'Homepage Dashboard', link: '/integrations/homepage' },
          { text: 'Browser Extension', link: '/integrations/browser-extension' },
        ],
      },
      {
        text: 'Browser Extension',
        collapsed: false,
        items: [
          { text: 'Getting Started', link: '/extension/' },
          { text: 'Chrome & Brave', link: '/extension/chrome' },
          { text: 'Privacy', link: '/extension-privacy' },
        ],
      },
      {
        text: 'Development',
        collapsed: false,
        items: [
          { text: 'Local development', link: '/development/local-development' },
          { text: 'Docker images', link: '/development/docker-images' },
          { text: 'Testing', link: '/development/testing' },
        ],
      },
      { text: 'Troubleshooting', link: '/troubleshooting' },
    ],
    search: {
      provider: 'local',
    },
    outline: {
      level: [2, 3],
      label: 'On this page',
    },
    socialLinks: [
      { icon: 'github', link: 'https://github.com/Skulldorom/usage-dashboard' },
    ],
    editLink: {
      pattern: 'https://github.com/Skulldorom/usage-dashboard/edit/main/docs/:path',
      text: 'Edit this page on GitHub',
    },
    footer: {
      message: 'Self-hosted API usage dashboard.',
      copyright: 'Copyright © Skulldorom',
    },
    lastUpdated: {
      text: 'Last updated',
    },
  },
})
