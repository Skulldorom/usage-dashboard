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
          { text: 'Usage analytics', link: '/configuration/analytics' },
          { text: 'Data sources', link: '/configuration/data-sources' },
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
      { icon: { svg: '<svg role="img" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><title>Ko-fi</title><path fill="currentColor" d="M11.351 2.715c-2.7 0-4.986.025-6.83.26C2.078 3.285 0 5.154 0 8.61c0 3.506.182 6.13 1.585 8.493 1.584 2.701 4.233 4.182 7.662 4.182h.83c4.209 0 6.494-2.234 7.637-4a9.5 9.5 0 0 0 1.091-2.338C21.792 14.688 24 12.22 24 9.208v-.415c0-3.247-2.13-5.507-5.792-5.87-1.558-.156-2.65-.208-6.857-.208m0 1.947c4.208 0 5.09.052 6.571.182 2.624.311 4.13 1.584 4.13 4v.39c0 2.156-1.792 3.844-3.87 3.844h-.935l-.156.649c-.208 1.013-.597 1.818-1.039 2.546-.909 1.428-2.545 3.064-5.922 3.064h-.805c-2.571 0-4.831-.883-6.078-3.195-1.09-2-1.298-4.155-1.298-7.506 0-2.181.857-3.402 3.012-3.714 1.533-.233 3.559-.26 6.39-.26m6.547 2.287c-.416 0-.65.234-.65.546v2.935c0 .311.234.545.65.545 1.324 0 2.051-.754 2.051-2s-.727-2.026-2.052-2.026m-10.39.182c-1.818 0-3.013 1.48-3.013 3.142 0 1.533.858 2.857 1.949 3.897.727.701 1.87 1.429 2.649 1.896a1.47 1.47 0 0 0 1.507 0c.78-.467 1.922-1.195 2.623-1.896 1.117-1.039 1.974-2.364 1.974-3.897 0-1.662-1.247-3.142-3.039-3.142-1.065 0-1.792.545-2.338 1.298-.493-.753-1.246-1.298-2.312-1.298"/></svg>' }, link: 'https://ko-fi.com/skulldorom', ariaLabel: 'Support Skulldorom on Ko-fi' },
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
