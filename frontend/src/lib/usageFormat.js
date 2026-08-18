// Pure formatting/metric helpers extracted from DashboardPage so they can be
// unit-tested in isolation without rendering React components.

export const PREFERRED_METRICS = {
  anthropic: ['input_tokens', 'output_tokens', 'num_requests'],
  codex: ['session_remaining_percent', 'weekly_remaining_percent', 'review_session_remaining_percent', 'review_weekly_remaining_percent', 'reset_credits_available'],
  deepseek: ['total_balance', 'granted_balance', 'topped_up_balance'],
  firecrawl: ['credits_remaining', 'credits_used', 'usage_percent', 'plan_credits'],
  openai: ['cost_30d'],
  openrouter: ['limit_remaining', 'usage_monthly', 'usage_weekly'],
}

export const PROVIDER_USAGE_URLS = {
  anthropic: 'https://console.anthropic.com/settings/usage',
  codex: 'https://chatgpt.com/codex/cloud/settings/analytics',
  deepseek: 'https://platform.deepseek.com/usage',
  firecrawl: 'https://www.firecrawl.dev/app',
  openai: 'https://platform.openai.com/settings/organization/usage',
  openrouter: 'https://openrouter.ai/settings/credits',
}

export function isCodexPercentMetric(provider, metric) {
  return provider === 'codex' && metric.unit === '%' && typeof metric.value === 'number'
}

export function codexRemainingValue(metric) {
  if (metric.label.includes('used_percent')) return Math.min(100, Math.max(0, 100 - metric.value))
  return Math.min(100, Math.max(0, metric.value))
}

export function metricPercent(metric, provider) {
  if (isCodexPercentMetric(provider, metric)) return codexRemainingValue(metric)
  return typeof metric.maximum === 'number' && metric.maximum > 0 && typeof metric.value === 'number'
    ? Math.min(100, Math.max(0, (metric.value / metric.maximum) * 100))
    : null
}

export function formatPercent(value) { return `${Math.round(value)}%` }

export function formatMetricLabel(label, provider) {
  if (provider === 'codex') return label.replace('used_percent', 'remaining_percent').replaceAll('_', ' ')
  return label.replaceAll('_', ' ')
}

export function formatMetricValue(metric, provider, percent) {
  if (isCodexPercentMetric(provider, metric)) return `${formatPercent(codexRemainingValue(metric))} left`
  return `${String(metric.value ?? '-')} ${metric.unit || ''}${percent !== null ? ` (${formatPercent(percent)})` : ''}`
}

export function formatDateTime(value) {
  if (!value) return 'Not scheduled'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export function numericMetric(metrics, label) {
  const metric = metrics.find((item) => item.label === label)
  return typeof metric?.value === 'number' ? metric : null
}

export function selectHistoryMetric(provider, snapshots) {
  const preferred = PREFERRED_METRICS[provider] || []
  const labels = [...preferred, ...new Set(snapshots.flatMap((snapshot) => (snapshot.metrics || []).map((metric) => metric.label)))]
  return labels
    .map((label) => ({ label, values: snapshots.map((snapshot) => numericMetric(snapshot.metrics || [], label)?.value).filter((value) => typeof value === 'number') }))
    .find((candidate) => candidate.values.length > 1) || null
}

export function firecrawlSummary(metrics) {
  const usagePercent = metrics.find((metric) => metric.label === 'usage_percent' && typeof metric.value === 'number')
  const creditsRemaining = metrics.find((metric) => metric.label === 'credits_remaining' && metric.value !== null && metric.value !== undefined)
  if (!usagePercent || !creditsRemaining) return null

  return {
    label: 'Firecrawl credits',
    value: `${usagePercent.value}% • ${creditsRemaining.value} credits left`,
    percent: Math.min(100, Math.max(0, usagePercent.value)),
  }
}

export const ALERT_SEVERITY = {
  warning: 'warning',
  critical: 'error',
  exhausted: 'error',
}

export function alertSeverity(alertState) {
  return ALERT_SEVERITY[alertState] || null
}

export function alertMessage(alerts, alertState) {
  if (!alerts || alerts.length === 0 || alertState === 'normal') return null
  const verb = alertState === 'exhausted' ? 'exhausted' : alertState
  const detail = alerts
    .filter((alert) => alert.alert_state !== 'normal')
    .map((alert) => {
      const value = alert.value ?? '-'
      const unit = alert.unit ? ` ${alert.unit}` : ''
      return `${alert.metric.replaceAll('_', ' ')} at ${value}${unit}`
    })
    .join(', ')
  return `Threshold ${verb}: ${detail}`
}
