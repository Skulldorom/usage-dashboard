// Pure Homepage YAML-generation helpers extracted from SettingsPage so they
// can be unit-tested without rendering React components.

const HOMEPAGE_WIDGET_FIELDS = [
  ['summary', 'Summary'],
  ['configured_providers', 'Configured'],
  ['healthy_providers', 'Healthy'],
  ['degraded_providers', 'Degraded'],
]

export function yamlQuote(value) {
  const text = String(value ?? '').trim()
  if (!text) return '""'
  if (/^[A-Za-z0-9_./:@-]+$/.test(text)) return text
  return JSON.stringify(text)
}

export function joinUrl(base, path) {
  const safeBase = (base || 'https://usage-dashboard.example.com').trim().replace(/\/+$/, '')
  const safePath = (path || '/api/v1/homepage').trim()
  return `${safeBase}${safePath.startsWith('/') ? safePath : `/${safePath}`}`
}

export function homepageYaml(form) {
  const dashboardUrl = (form.dashboardUrl || 'https://usage-dashboard.example.com').trim().replace(/\/+$/, '')
  const apiUrl = joinUrl(dashboardUrl, '/api/v1/homepage')
  const tokenValue = form.includeToken && form.token.trim() ? form.token.trim() : 'REPLACE_WITH_ADMIN_OR_HOMEPAGE_TOKEN'
  const refreshInterval = String(form.refreshInterval || '').trim()
  const lines = [
    '- Usage Dashboard:',
    `    href: ${yamlQuote(dashboardUrl)}`,
    '    widget:',
    '      type: customapi',
    `      url: ${yamlQuote(apiUrl)}`,
    '      method: GET',
  ]
  if (refreshInterval) lines.push(`      refreshInterval: ${yamlQuote(refreshInterval)}`)
  if (form.displayMode === 'dynamic-list') lines.push('      display: dynamic-list')
  if (form.authMode === 'bearer') {
    lines.push('      headers:')
    lines.push(`        Authorization: ${yamlQuote(`Bearer ${tokenValue}`)}`)
  }
  lines.push('      mappings:')
  if (form.displayMode === 'dynamic-list') {
    lines.push('        items: list')
    lines.push('        name: label')
    lines.push('        label: value')
    lines.push('        format: text')
  } else {
    HOMEPAGE_WIDGET_FIELDS.forEach(([field, label]) => {
      lines.push(`        - field: ${field}`)
      lines.push(`          label: ${label}`)
    })
  }
  return `${lines.join('\n')}\n`
}
