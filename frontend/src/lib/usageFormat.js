// Pure formatting/metric helpers extracted from DashboardPage so they can be
// unit-tested in isolation without rendering React components.

export const PREFERRED_METRICS = {
  anthropic: ['input_tokens', 'output_tokens', 'num_requests'],
  codex: ['session_remaining_percent', 'weekly_remaining_percent', 'review_session_remaining_percent', 'review_weekly_remaining_percent', 'reset_credits_available'],
  deepseek: ['total_balance', 'granted_balance', 'topped_up_balance'],
  firecrawl: ['credits_remaining', 'credits_used', 'usage_percent', 'plan_credits'],
  openai: ['cost_30d'],
  openrouter: ['limit_remaining', 'usage_monthly', 'usage_weekly'],
  'opencode-go': ['weekly_remaining', 'five_hour_remaining', 'monthly_remaining', 'exhausted'],
}

// OpenCode Go metric labels consumed by the limit-window sections rather than
// the generic metric list. The 5-hour window is the provider's rolling session limit.
export const OPENCODEGO_LIMIT_METRIC_LABELS = [
  'five_hour_remaining',
  'five_hour_reset_at',
  'weekly_remaining',
  'weekly_reset_at',
  'monthly_remaining',
  'monthly_reset_at',
]

// Codex metric labels consumed by the usage-window limit sections rather than
// the generic metric list. The session window is the provider's 5-hour limit.
export const CODEX_LIMIT_METRIC_LABELS = [
  'session_remaining_percent',
  'session_reset_at',
  'weekly_remaining_percent',
  'weekly_reset_at',
]

const OPENCODEGO_LIMIT_WINDOWS = [
  { prefix: 'five_hour', title: '5-hour usage limit', includeDate: false },
  { prefix: 'weekly', title: 'Weekly usage limit', includeDate: true },
  { prefix: 'monthly', title: 'Monthly usage limit', includeDate: true },
]

const CODEX_LIMIT_WINDOWS = [
  { prefix: 'session', title: '5 hour usage limit', includeDate: false },
  { prefix: 'weekly', title: 'Weekly usage limit', includeDate: true },
]

export const PROVIDER_USAGE_URLS = {
  anthropic: 'https://console.anthropic.com/settings/usage',
  codex: 'https://chatgpt.com/codex/cloud/settings/analytics',
  deepseek: 'https://platform.deepseek.com/usage',
  firecrawl: 'https://www.firecrawl.dev/app',
  openai: 'https://platform.openai.com/settings/organization/usage',
  openrouter: 'https://openrouter.ai/settings/credits',
  'opencode-go': 'https://opencode.ai/auth',
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

export function isPercentBasedMetric(metric) {
  return metric?.unit === '%' && typeof metric.value === 'number'
}

export function formatResetTime(value, { includeDate = true } = {}) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  const options = includeDate
    ? { dateStyle: 'medium', timeStyle: 'short' }
    : { timeStyle: 'short' }
  return new Intl.DateTimeFormat(undefined, options).format(date)
}

export function formatRelativeReset(value, now = Date.now()) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  const diffMs = date.getTime() - now
  if (diffMs <= 0) return null
  const totalMinutes = Math.round(diffMs / 60000)
  if (totalMinutes < 60) return `in ${totalMinutes}m`
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours < 24) return minutes ? `in ${hours}h ${minutes}m` : `in ${hours}h`
  const days = Math.floor(hours / 24)
  return `in ${days}d ${hours % 24}h`
}

// Build the Codex 5-hour/session and weekly usage-window sections from a
// snapshot metric list. Returns sections only for windows that have a remaining
// percent or a reset timestamp; reset times are never fabricated.
export function codexLimitSections(metrics) {
  const byLabel = new Map((metrics || []).map((metric) => [metric.label, metric]))
  return CODEX_LIMIT_WINDOWS.map(({ prefix, title, includeDate }) => {
    const remaining = byLabel.get(`${prefix}_remaining_percent`)
    const resetAt = byLabel.get(`${prefix}_reset_at`)
    const remainingValue =
      typeof remaining?.value === 'number'
        ? Math.min(100, Math.max(0, remaining.value))
        : null
    const resetValue =
      typeof resetAt?.value === 'string' && resetAt.value ? resetAt.value : null
    if (remainingValue === null && resetValue === null) return null
    return {
      key: prefix,
      title,
      remaining: remainingValue,
      remainingLabel: remainingValue === null ? null : `${formatPercent(remainingValue)} remaining`,
      resetAt: resetValue,
      resetLabel: resetValue ? formatResetTime(resetValue, { includeDate }) : null,
      relativeLabel: resetValue ? formatRelativeReset(resetValue) : null,
    }
  }).filter(Boolean)
}

// Build the OpenCode Go 5-hour, weekly, and monthly usage-window sections from
// a snapshot metric list. Values are USD remaining; reset times are never fabricated.
export function opencodeGoLimitSections(metrics) {
  const byLabel = new Map((metrics || []).map((metric) => [metric.label, metric]))
  return OPENCODEGO_LIMIT_WINDOWS.map(({ prefix, title, includeDate }) => {
    const remaining = byLabel.get(`${prefix}_remaining`)
    const limit = byLabel.get(`${prefix}_limit`)
    const resetAt = byLabel.get(`${prefix}_reset_at`)
    const remainingValue =
      typeof remaining?.value === 'number'
        ? Math.max(0, remaining.value)
        : null
    const limitValue =
      typeof limit?.value === 'number' && limit.value > 0 ? limit.value : null
    const resetValue =
      typeof resetAt?.value === 'string' && resetAt.value ? resetAt.value : null
    if (remainingValue === null && limitValue === null && resetValue === null) return null
    return {
      key: prefix,
      title,
      remaining: remainingValue,
      limit: limitValue,
      remainingLabel:
        remainingValue === null
          ? null
          : `$${remainingValue.toFixed(2)} remaining`,
      percent:
        remainingValue !== null && limitValue !== null && limitValue > 0
          ? Math.min(100, Math.max(0, (remainingValue / limitValue) * 100))
          : null,
      resetAt: resetValue,
      resetLabel: resetValue ? formatResetTime(resetValue, { includeDate }) : null,
      relativeLabel: resetValue ? formatRelativeReset(resetValue) : null,
    }
  }).filter(Boolean)
}

function displaySnapshot(item) {
  return item?.last_good || item?.latest || null
}

function displayProviderLabel(item) {
  const provider = item?.config?.provider || 'Provider'
  const label = item?.config?.label
  return label && label !== 'main' && label !== provider ? `${provider} · ${label}` : provider
}

function metricTooltip({ providerLabel, metricLabel, value }) {
  return `${providerLabel} · ${metricLabel}: ${value}`
}

export function overallUsageGroups(items) {
  const percentMetrics = []
  const unitMetrics = []

  items
    .filter((item) => item?.config?.is_visible)
    .forEach((item) => {
      const snapshot = displaySnapshot(item)
      const provider = item.config.provider
      const providerLabel = displayProviderLabel(item)

      ;(snapshot?.metrics || []).forEach((metric) => {
        if (typeof metric.value !== 'number') return

        const label = formatMetricLabel(metric.label, provider)
        const percent = metricPercent(metric, provider)
        const value = formatMetricValue(metric, provider, percent)
        const entry = {
          id: `${item.config.id}:${metric.label}`,
          provider,
          providerLabel,
          label,
          value,
          numericValue: metric.value,
          unit: metric.unit || 'units',
          percent,
          tooltip: metricTooltip({ providerLabel, metricLabel: label, value }),
        }

        if (isPercentBasedMetric(metric)) {
          percentMetrics.push({ ...entry, percent: percent ?? Math.min(100, Math.max(0, metric.value)) })
        } else {
          unitMetrics.push(entry)
        }
      })
    })

  const byProviderThenLabel = (a, b) => a.providerLabel.localeCompare(b.providerLabel) || a.label.localeCompare(b.label)
  const byUnitThenLabel = (a, b) => a.unit.localeCompare(b.unit) || a.providerLabel.localeCompare(b.providerLabel) || a.label.localeCompare(b.label)

  return {
    percent: {
      label: 'Percentage metrics',
      metrics: percentMetrics.sort(byProviderThenLabel),
    },
    units: {
      label: 'Unit metrics',
      metrics: unitMetrics.sort(byUnitThenLabel),
    },
  }
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

export function formatThresholdRule(rule) {
  if (!rule) return ''
  const levels = [rule.warning, rule.critical, rule.exhausted].filter((value) => value !== null && value !== undefined)
  const operator = rule.direction === 'decreasing' ? '≤' : '≥'
  return `${rule.metric.replaceAll('_', ' ')} ${operator} ${levels.join(' / ')}`
}

export const HEALTH_STATES = {
  healthy: { severity: 'success', label: 'Healthy' },
  stale: { severity: 'warning', label: 'Stale' },
  error: { severity: 'error', label: 'Unavailable' },
  never_connected: { severity: 'default', label: 'Not connected' },
}

export function healthMeta(health) {
  const raw = health?.status
  const status = HEALTH_STATES[raw] ? raw : 'never_connected'
  const meta = HEALTH_STATES[status]
  return { status, severity: meta.severity, label: meta.label }
}

export function formatAge(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return null
  const total = Math.max(0, Math.floor(Number(seconds)))
  if (total < 60) return 'just now'
  const minutes = Math.floor(total / 60)
  if (minutes < 60) return minutes === 1 ? '1 minute ago' : `${minutes} minutes ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    const remainder = minutes % 60
    return remainder ? `${hours}h ${remainder}m ago` : `${hours}h ago`
  }
  const days = Math.floor(hours / 24)
  return days === 1 ? '1 day ago' : `${days} days ago`
}

export function healthText(health) {
  const { status } = healthMeta(health)
  const age = formatAge(health?.age_seconds)
  if (status === 'healthy') return age ? `Updated ${age}` : 'Healthy'
  if (status === 'stale') return `Last successful update ${age || 'unknown'} · using last-known data`
  if (status === 'error') return health?.last_success_at ? `Unavailable · last successful update ${age || 'unknown'}` : 'Provider unavailable'
  return 'No successful connection yet'
}
