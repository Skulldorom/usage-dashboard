import { describe, it, expect } from 'vitest'
import { yamlQuote, joinUrl, homepageYaml } from './homepageYaml.js'

describe('yamlQuote', () => {
  it('returns plain values for safe characters', () => {
    expect(yamlQuote('dashboard')).toBe('dashboard')
    expect(yamlQuote('https://example.com')).toBe('https://example.com')
  })

  it('quotes values with unsafe characters', () => {
    expect(yamlQuote('Usage Dashboard')).toBe('"Usage Dashboard"')
    expect(yamlQuote('Bearer abc123')).toBe('"Bearer abc123"')
  })

  it('returns empty quotes for blank values', () => {
    expect(yamlQuote('')).toBe('""')
    expect(yamlQuote('   ')).toBe('""')
    expect(yamlQuote(undefined)).toBe('""')
  })
})

describe('joinUrl', () => {
  it('joins a base and path', () => {
    expect(joinUrl('https://example.com', '/api/v1/homepage')).toBe('https://example.com/api/v1/homepage')
  })

  it('normalizes trailing/leading slashes', () => {
    expect(joinUrl('https://example.com/', '/api/v1/homepage')).toBe('https://example.com/api/v1/homepage')
    expect(joinUrl('https://example.com', 'api/v1/homepage')).toBe('https://example.com/api/v1/homepage')
  })
})

describe('homepageYaml', () => {
  const base = {
    dashboardUrl: 'https://usage.example.com',
    refreshInterval: '300000',
    displayMode: 'dynamic-list',
    authMode: 'bearer',
    token: 'secret-token',
    includeToken: true,
  }

  it('generates a dynamic-list service block with bearer auth', () => {
    const expected = [
      '- Usage Dashboard:',
      '    href: https://usage.example.com',
      '    widget:',
      '      type: customapi',
      '      url: https://usage.example.com/api/v1/homepage',
      '      method: GET',
      '      refreshInterval: 300000',
      '      display: dynamic-list',
      '      headers:',
      '        Authorization: "Bearer secret-token"',
      '      mappings:',
      '        items: list',
      '        name: label',
      '        label: value',
      '        format: text',
    ].join('\n') + '\n'

    expect(homepageYaml(base)).toBe(expected)
  })

  it('uses a placeholder when the token is not included', () => {
    const yaml = homepageYaml({ ...base, includeToken: false, token: 'secret-token' })
    expect(yaml).toContain('Authorization: "Bearer REPLACE_WITH_ADMIN_OR_HOMEPAGE_TOKEN"')
  })

  it('omits headers when authMode is none', () => {
    const yaml = homepageYaml({ ...base, authMode: 'none' })
    expect(yaml).not.toContain('headers:')
    expect(yaml).not.toContain('Authorization:')
  })

  it('omits refreshInterval when blank', () => {
    const yaml = homepageYaml({ ...base, refreshInterval: '' })
    expect(yaml).not.toContain('refreshInterval:')
  })

  it('renders summary-card mappings instead of a dynamic list', () => {
    const yaml = homepageYaml({ ...base, displayMode: 'summary' })
    expect(yaml).toContain('        - field: summary')
    expect(yaml).toContain('          label: Summary')
    expect(yaml).not.toContain('items: list')
  })
})
