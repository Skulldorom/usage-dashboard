import { describe, it, expect } from 'vitest'
import {
  alertMessage,
  alertSeverity,
  codexLimitSections,
  codexRemainingValue,
  firecrawlSummary,
  formatAge,
  formatDateTime,
  formatMetricLabel,
  formatMetricValue,
  formatRelativeReset,
  formatResetTime,
  formatThresholdRule,
  healthMeta,
  healthText,
  metricPercent,
  numericMetric,
  OPENCODEGO_LIMIT_METRIC_LABELS,
  opencodeGoLimitSections,
  overallUsageGroups,
  PREFERRED_METRICS,
  providerErrorActionLabel,
  providerErrorSummary,
  selectHistoryMetric,
  stageLabel,
} from './usageFormat.js'

describe('codexRemainingValue', () => {
  it('inverts a used_percent metric into remaining percent', () => {
    expect(codexRemainingValue({ label: 'session_used_percent', value: 21, unit: '%' })).toBe(79)
  })

  it('clamps the inverted value to [0, 100]', () => {
    expect(codexRemainingValue({ label: 'used_percent', value: 150, unit: '%' })).toBe(0)
    expect(codexRemainingValue({ label: 'used_percent', value: -5, unit: '%' })).toBe(100)
  })

  it('passes through non-used_percent values clamped to [0, 100]', () => {
    expect(codexRemainingValue({ label: 'session_remaining_percent', value: 54, unit: '%' })).toBe(54)
    expect(codexRemainingValue({ label: 'session_remaining_percent', value: 130, unit: '%' })).toBe(100)
  })
})

describe('metricPercent', () => {
  it('returns remaining percent for codex percent metrics', () => {
    expect(metricPercent({ label: 'used_percent', value: 21, unit: '%' }, 'codex')).toBe(79)
  })

  it('returns value/maximum for ordinary metrics', () => {
    expect(metricPercent({ label: 'remaining', value: 42, unit: 'credits', maximum: 100 }, 'fake')).toBe(42)
  })

  it('clamps to [0, 100]', () => {
    expect(metricPercent({ label: 'remaining', value: 150, maximum: 100 }, 'fake')).toBe(100)
    expect(metricPercent({ label: 'remaining', value: -5, maximum: 100 }, 'fake')).toBe(0)
  })

  it('returns null when maximum is missing or zero', () => {
    expect(metricPercent({ label: 'remaining', value: 42 }, 'fake')).toBeNull()
    expect(metricPercent({ label: 'remaining', value: 42, maximum: 0 }, 'fake')).toBeNull()
  })
})

describe('formatMetricLabel', () => {
  it('replaces underscores with spaces', () => {
    expect(formatMetricLabel('credits_remaining', 'firecrawl')).toBe('credits remaining')
  })

  it('rewrites codex used_percent labels to remaining_percent', () => {
    expect(formatMetricLabel('session_used_percent', 'codex')).toBe('session remaining percent')
  })
})

describe('formatMetricValue', () => {
  it('shows "X% left" for codex percent metrics', () => {
    expect(formatMetricValue({ label: 'used_percent', value: 21, unit: '%' }, 'codex', 79)).toBe('79% left')
  })

  it('shows value, unit, and percent for ordinary metrics', () => {
    expect(formatMetricValue({ label: 'remaining', value: 42, unit: 'credits', maximum: 100 }, 'fake', 42)).toBe('42 credits (42%)')
  })

  it('omits the percent suffix when percent is null', () => {
    expect(formatMetricValue({ label: 'remaining', value: 7, unit: 'requests' }, 'fake', null)).toBe('7 requests')
  })
})

describe('firecrawlSummary', () => {
  it('composes usage percent and remaining credits', () => {
    expect(
      firecrawlSummary([
        { label: 'usage_percent', value: 82, unit: '%' },
        { label: 'credits_remaining', value: 1200, unit: 'credits' },
      ]),
    ).toEqual({ label: 'Firecrawl credits', value: '82% • 1200 credits left', percent: 82 })
  })

  it('clamps percent to [0, 100]', () => {
    expect(
      firecrawlSummary([
        { label: 'usage_percent', value: 150, unit: '%' },
        { label: 'credits_remaining', value: 10 },
      ]).percent,
    ).toBe(100)
  })

  it('returns null when required metrics are missing', () => {
    expect(firecrawlSummary([{ label: 'usage_percent', value: 82, unit: '%' }])).toBeNull()
    expect(firecrawlSummary([{ label: 'credits_remaining', value: 10 }])).toBeNull()
    expect(firecrawlSummary([])).toBeNull()
  })
})


describe('overallUsageGroups', () => {
  const items = [
    {
      config: { id: 1, provider: 'codex', label: 'main', is_visible: true },
      latest: {
        metrics: [
          { label: 'session_used_percent', value: 25, unit: '%' },
          { label: 'reset_credits_available', value: 10, unit: 'credits', maximum: 20 },
        ],
      },
    },
    {
      config: { id: 2, provider: 'firecrawl', label: 'Firecrawl Prod', is_visible: true },
      latest: {
        metrics: [
          { label: 'usage_percent', value: 80, unit: '%' },
          { label: 'credits_remaining', value: 50, unit: 'credits', maximum: 100 },
          { label: 'pages', value: 4 },
        ],
      },
    },
    {
      config: { id: 3, provider: 'hidden', label: 'Hidden', is_visible: false },
      latest: { metrics: [{ label: 'usage_percent', value: 100, unit: '%' }] },
    },
  ]

  it('separates percentage metrics from unit metrics', () => {
    const groups = overallUsageGroups(items)
    expect(groups.percent.metrics.map((metric) => metric.label)).toEqual(['usage percent', 'session remaining percent'])
    expect(groups.units.metrics.map((metric) => metric.label)).toEqual(['credits remaining', 'reset credits available', 'pages'])
  })

  it('uses canonical provider display names and drops generic row labels', () => {
    const groups = overallUsageGroups(items)
    expect(groups.percent.metrics.find((metric) => metric.label === 'session remaining percent').providerLabel).toBe('OpenAI Codex')
    expect(groups.percent.metrics.find((metric) => metric.label === 'usage percent').providerLabel).toBe('Firecrawl')
  })

  it('adds labels only when multiple visible configs share a provider', () => {
    const groups = overallUsageGroups([
      ...items,
      {
        config: { id: 4, provider: 'codex', label: 'Work', is_visible: true },
        latest: { metrics: [{ label: 'session_used_percent', value: 40, unit: '%' }] },
      },
    ])
    expect(groups.percent.metrics.map((metric) => metric.providerLabel).filter((label) => label.startsWith('OpenAI Codex'))).toEqual([
      'OpenAI Codex',
      'OpenAI Codex - Work',
    ])
  })

  it('does not aggregate unit metrics across providers', () => {
    const groups = overallUsageGroups(items)
    const credits = groups.units.metrics.filter((metric) => metric.unit === 'credits')
    expect(credits).toHaveLength(2)
    expect(credits.map((metric) => metric.numericValue)).toEqual([50, 10])
    expect(credits.every((metric) => metric.percent !== null)).toBe(true)
  })
})

describe('formatDateTime', () => {
  it('returns "Not scheduled" for empty values', () => {
    expect(formatDateTime(null)).toBe('Not scheduled')
    expect(formatDateTime('')).toBe('Not scheduled')
    expect(formatDateTime(undefined)).toBe('Not scheduled')
  })

  it('returns the original value for invalid dates', () => {
    expect(formatDateTime('not-a-date')).toBe('not-a-date')
  })

  it('formats a valid date without throwing', () => {
    const result = formatDateTime('2026-08-14T12:00:00Z')
    expect(typeof result).toBe('string')
    expect(result).not.toBe('Not scheduled')
    expect(result.length).toBeGreaterThan(0)
  })
})

describe('numericMetric', () => {
  const metrics = [{ label: 'remaining', value: 42 }, { label: 'status', value: 'healthy' }]

  it('returns the metric with a numeric value', () => {
    expect(numericMetric(metrics, 'remaining')).toEqual({ label: 'remaining', value: 42 })
  })

  it('returns null for non-numeric or missing metrics', () => {
    expect(numericMetric(metrics, 'status')).toBeNull()
    expect(numericMetric(metrics, 'missing')).toBeNull()
  })
})

describe('selectHistoryMetric', () => {
  const snapshots = [
    { metrics: [{ label: 'total_balance', value: 100 }, { label: 'one_off', value: 5 }] },
    { metrics: [{ label: 'total_balance', value: 90 }] },
    { metrics: [{ label: 'total_balance', value: 80 }] },
  ]

  it('picks a preferred metric with more than one numeric value', () => {
    const selected = selectHistoryMetric('deepseek', snapshots)
    expect(selected.label).toBe('total_balance')
    expect(selected.values).toEqual([100, 90, 80])
  })

  it('returns null when no metric has more than one value', () => {
    expect(selectHistoryMetric('deepseek', [{ metrics: [{ label: 'total_balance', value: 100 }] }])).toBeNull()
  })

  it('prefers OpenCode Go used-percent metrics for history', () => {
    const snapshots = [
      { metrics: [{ label: 'five_hour_used_percent', value: 33 }, { label: 'weekly_remaining', value: 20 }] },
      { metrics: [{ label: 'five_hour_used_percent', value: 44 }, { label: 'weekly_remaining', value: 19 }] },
    ]

    expect(PREFERRED_METRICS['opencode-go'].slice(0, 3)).toEqual([
      'five_hour_used_percent',
      'weekly_used_percent',
      'monthly_used_percent',
    ])
    expect(selectHistoryMetric('opencode-go', snapshots).label).toBe('five_hour_used_percent')
  })
})

describe('alertSeverity', () => {
  it('maps alert states to MUI severities', () => {
    expect(alertSeverity('normal')).toBeNull()
    expect(alertSeverity('warning')).toBe('warning')
    expect(alertSeverity('critical')).toBe('error')
    expect(alertSeverity('exhausted')).toBe('error')
    expect(alertSeverity(undefined)).toBeNull()
  })
})

describe('alertMessage', () => {
  it('summarizes crossed thresholds', () => {
    const alerts = [
      { metric: 'usage_percent', value: 92, unit: '%', alert_state: 'critical' },
    ]
    expect(alertMessage(alerts, 'critical')).toContain('usage percent at 92 %')
  })

  it('uses "exhausted" wording for the exhausted state', () => {
    const alerts = [{ metric: 'credits_remaining', value: 0, unit: 'USD', alert_state: 'exhausted' }]
    expect(alertMessage(alerts, 'exhausted')).toContain('Threshold exhausted')
  })

  it('returns null when nothing crossed', () => {
    expect(alertMessage([], 'normal')).toBeNull()
    expect(alertMessage([{ metric: 'x', alert_state: 'normal' }], 'normal')).toBeNull()
    expect(alertMessage(null, 'critical')).toBeNull()
  })
})

describe('formatThresholdRule', () => {
  it('formats an increasing threshold with all levels', () => {
    expect(formatThresholdRule({ metric: 'usage_percent', direction: 'increasing', warning: 80, critical: 90, exhausted: 100 })).toBe('usage percent ≥ 80 / 90 / 100')
  })

  it('uses ≤ for decreasing thresholds', () => {
    expect(formatThresholdRule({ metric: 'credits_remaining', direction: 'decreasing', warning: 500, critical: 100 })).toBe('credits remaining ≤ 500 / 100')
  })

  it('omits unset levels and returns empty for missing rules', () => {
    expect(formatThresholdRule({ metric: 'cost_30d', direction: 'increasing', warning: 10 })).toBe('cost 30d ≥ 10')
    expect(formatThresholdRule(null)).toBe('')
    expect(formatThresholdRule(undefined)).toBe('')
  })
})

describe('healthMeta', () => {
  it('maps each health status to a severity and label', () => {
    expect(healthMeta({ status: 'healthy' })).toEqual({ status: 'healthy', severity: 'success', label: 'Healthy' })
    expect(healthMeta({ status: 'stale' })).toEqual({ status: 'stale', severity: 'warning', label: 'Stale' })
    expect(healthMeta({ status: 'error' })).toEqual({ status: 'error', severity: 'error', label: 'Unavailable' })
    expect(healthMeta({ status: 'never_connected' })).toEqual({ status: 'never_connected', severity: 'default', label: 'Not connected' })
  })

  it('defaults to never_connected for missing/unknown status', () => {
    expect(healthMeta(null).status).toBe('never_connected')
    expect(healthMeta({}).status).toBe('never_connected')
    expect(healthMeta({ status: 'bogus' }).status).toBe('never_connected')
  })
})

describe('formatAge', () => {
  it('formats sub-minute and minute durations', () => {
    expect(formatAge(30)).toBe('just now')
    expect(formatAge(60)).toBe('1 minute ago')
    expect(formatAge(90)).toBe('1 minute ago')
    expect(formatAge(5 * 60)).toBe('5 minutes ago')
  })

  it('formats hours and days', () => {
    expect(formatAge(3600)).toBe('1h ago')
    expect(formatAge(2 * 3600 + 14 * 60)).toBe('2h 14m ago')
    expect(formatAge(3 * 86400)).toBe('3 days ago')
  })

  it('handles null/undefined/NaN', () => {
    expect(formatAge(null)).toBe(null)
    expect(formatAge(undefined)).toBe(null)
    expect(formatAge(Number.NaN)).toBe(null)
  })
})

describe('healthText', () => {
  it('describes healthy with age', () => {
    expect(healthText({ status: 'healthy', age_seconds: 120 })).toBe('Updated 2 minutes ago')
  })

  it('describes stale with last-known-good age', () => {
    expect(healthText({ status: 'stale', age_seconds: 8040 })).toBe('Last successful update 2h 14m ago · using last-known data')
  })

  it('describes error with and without a last success', () => {
    expect(healthText({ status: 'error', age_seconds: null })).toBe('Provider unavailable')
    expect(healthText({ status: 'error', last_success_at: 'x', age_seconds: 172800 })).toBe('Unavailable · last successful update 2 days ago')
  })

  it('describes never_connected', () => {
    expect(healthText({ status: 'never_connected' })).toBe('No successful connection yet')
  })
})

describe('formatResetTime', () => {
  it('returns null for empty or invalid values', () => {
    expect(formatResetTime(null)).toBeNull()
    expect(formatResetTime('')).toBeNull()
    expect(formatResetTime('not-a-date')).toBeNull()
  })

  it('includes the date for weekly windows', () => {
    expect(formatResetTime('2026-08-20T00:00:00Z', { includeDate: true })).toContain('2026')
  })

  it('omits the date for same-day session windows', () => {
    expect(formatResetTime('2026-08-14T12:30:00Z', { includeDate: false })).not.toContain('2026')
  })
})

describe('formatRelativeReset', () => {
  const NOW = Date.parse('2026-08-14T09:46:00Z')

  it('returns null for empty, invalid, or past values', () => {
    expect(formatRelativeReset(null, NOW)).toBeNull()
    expect(formatRelativeReset('not-a-date', NOW)).toBeNull()
    expect(formatRelativeReset('2026-08-14T08:00:00Z', NOW)).toBeNull()
  })

  it('formats sub-hour, hour, and day spans', () => {
    expect(formatRelativeReset('2026-08-14T09:46:00Z', NOW)).toBeNull() // now, not future
    expect(formatRelativeReset('2026-08-14T10:31:00Z', NOW)).toBe('in 45m')
    expect(formatRelativeReset('2026-08-14T12:00:00Z', NOW)).toBe('in 2h 14m')
    expect(formatRelativeReset('2026-08-15T12:00:00Z', NOW)).toBe('in 1d 2h')
  })
})

describe('codexLimitSections', () => {
  it('builds session and weekly sections with titles and reset times', () => {
    const sections = codexLimitSections([
      { label: 'session_remaining_percent', value: 42.4, unit: '%', maximum: 100 },
      { label: 'session_reset_at', value: '2026-08-14T12:30:00Z' },
      { label: 'weekly_remaining_percent', value: 12, unit: '%', maximum: 100 },
      { label: 'weekly_reset_at', value: '2026-08-20T00:00:00Z' },
    ])

    expect(sections.map((section) => section.key)).toEqual(['session', 'weekly'])
    expect(sections.map((section) => section.title)).toEqual(['5 hour usage limit', 'Weekly usage limit'])
    expect(sections[0].remaining).toBe(42.4)
    expect(sections[0].remainingLabel).toBe('42% remaining')
    expect(sections[0].resetAt).toBe('2026-08-14T12:30:00Z')
    expect(typeof sections[0].resetLabel).toBe('string')
    expect(sections[1].remaining).toBe(12)
    expect(sections[1].resetLabel).toContain('2026')
  })

  it('clamps remaining percent to [0, 100]', () => {
    const sections = codexLimitSections([
      { label: 'session_remaining_percent', value: 150, unit: '%' },
      { label: 'weekly_remaining_percent', value: -5, unit: '%' },
    ])
    expect(sections[0].remaining).toBe(100)
    expect(sections[1].remaining).toBe(0)
  })

  it('omits a window that has neither percent nor reset timestamp', () => {
    const sections = codexLimitSections([
      { label: 'session_remaining_percent', value: 88, unit: '%' },
    ])
    expect(sections.map((section) => section.key)).toEqual(['session'])
  })

  it('keeps a window that has a reset timestamp but no percent', () => {
    const sections = codexLimitSections([
      { label: 'weekly_reset_at', value: '2026-08-20T00:00:00Z' },
    ])
    expect(sections).toHaveLength(1)
    expect(sections[0].key).toBe('weekly')
    expect(sections[0].remaining).toBeNull()
    expect(sections[0].remainingLabel).toBeNull()
    expect(typeof sections[0].resetLabel).toBe('string')
  })

  it('does not fabricate a reset time when the provider omits it', () => {
    const sections = codexLimitSections([
      { label: 'session_remaining_percent', value: 88, unit: '%' },
      { label: 'weekly_remaining_percent', value: 12, unit: '%' },
      { label: 'weekly_reset_at', value: '' },
    ])
    expect(sections[0].resetLabel).toBeNull()
    expect(sections[0].relativeLabel).toBeNull()
    expect(sections[1].resetAt).toBeNull()
    expect(sections[1].resetLabel).toBeNull()
  })

  it('returns an empty list for empty or missing metrics', () => {
    expect(codexLimitSections([])).toEqual([])
    expect(codexLimitSections(undefined)).toEqual([])
  })
})

describe('opencodeGoLimitSections', () => {
  it('builds 5-hour, weekly, and monthly used-percent sections', () => {
    const sections = opencodeGoLimitSections([
      { label: 'five_hour_used_percent', value: 33, unit: '%', maximum: 100 },
      { label: 'five_hour_remaining_percent', value: 67, unit: '%', maximum: 100 },
      { label: 'five_hour_reset_at', value: '2026-09-01T16:06:10.272Z' },
      { label: 'weekly_used_percent', value: 13, unit: '%', maximum: 100 },
      { label: 'weekly_remaining_percent', value: 87, unit: '%', maximum: 100 },
      { label: 'weekly_reset_at', value: '2026-09-07T00:00:00.272Z' },
      { label: 'monthly_used_percent', value: 6, unit: '%', maximum: 100 },
      { label: 'monthly_remaining_percent', value: 94, unit: '%', maximum: 100 },
      { label: 'monthly_reset_at', value: '2026-10-01T11:00:59.272Z' },
    ])

    expect(sections.map((section) => section.key)).toEqual(['five_hour', 'weekly', 'monthly'])
    expect(sections.map((section) => section.title)).toEqual(['5-hour Usage', 'Weekly Usage', 'Monthly Usage'])
    expect(sections.map((section) => section.percent)).toEqual([33, 13, 6])
    expect(sections.map((section) => section.usageLabel)).toEqual([
      '33% used / 67% remaining',
      '13% used / 87% remaining',
      '6% used / 94% remaining',
    ])
    expect(sections[0].resetAt).toBe('2026-09-01T16:06:10.272Z')
    expect(typeof sections[0].resetLabel).toBe('string')
    expect(sections[1].resetLabel).toContain('2026')
  })

  it('clamps displayed used and remaining percentages', () => {
    const sections = opencodeGoLimitSections([
      { label: 'five_hour_used_percent', value: 133, unit: '%' },
      { label: 'five_hour_remaining_percent', value: -12, unit: '%' },
    ])

    expect(sections[0].percent).toBe(100)
    expect(sections[0].remaining).toBe(0)
    expect(sections[0].usageLabel).toBe('100% used / 0% remaining')
  })

  it('filters dedicated window metrics out of generic rows', () => {
    expect(OPENCODEGO_LIMIT_METRIC_LABELS).toEqual(
      expect.arrayContaining([
        'five_hour_used_percent',
        'five_hour_remaining_percent',
        'five_hour_reset_at',
        'weekly_used_percent',
        'weekly_remaining_percent',
        'weekly_reset_at',
        'monthly_used_percent',
        'monthly_remaining_percent',
        'monthly_reset_at',
      ]),
    )

    const genericRows = [
      { label: 'five_hour_used_percent', value: 33 },
      { label: 'balance_fallback_enabled', value: false },
      { label: 'exhausted', value: false },
    ].filter((metric) => !OPENCODEGO_LIMIT_METRIC_LABELS.includes(metric.label))

    expect(genericRows.map((metric) => metric.label)).toEqual(['balance_fallback_enabled', 'exhausted'])
  })
})

describe('providerErrorSummary', () => {
  it('returns null for a healthy provider with no error details', () => {
    expect(providerErrorSummary({ status: 'healthy' })).toBeNull()
    expect(providerErrorSummary({ status: 'healthy', latest_error_details: null })).toBeNull()
  })

  it('surfaces normalized error fields from health', () => {
    const summary = providerErrorSummary({
      latest_error_details: {
        category: 'rate_limit',
        message: 'Too Many Requests',
        http_status: 429,
        stage: 'fetch_usage',
        retryable: true,
        occurred_at: '2026-09-03T15:03:00Z',
      },
    })
    expect(summary.category).toBe('rate_limit')
    expect(summary.httpStatus).toBe(429)
    expect(summary.stage).toBe('fetch_usage')
    expect(summary.retryable).toBe(true)
    expect(summary.occurredAt).toBe('2026-09-03T15:03:00Z')
  })

  it('falls back to latest_error for the message', () => {
    const summary = providerErrorSummary({
      latest_error_details: { category: 'authentication', message: null, http_status: 401, stage: 'fetch_usage', retryable: false, occurred_at: '2026-09-03T15:03:00Z' },
      latest_error: 'Authentication rejected',
    })
    expect(summary.message).toBe('Authentication rejected')
  })
})

describe('providerErrorActionLabel', () => {
  it('gives actionable reconnect wording for authentication failures', () => {
    expect(providerErrorActionLabel({ category: 'authentication' })).toBe('Authentication rejected - reconnect provider.')
  })

  it('gives schema/upstream wording for schema_changed', () => {
    expect(providerErrorActionLabel({ category: 'schema_changed' })).toBe('Provider returned an unsupported response. Check server logs for diagnostic details.')
  })

  it('falls back to the message otherwise', () => {
    expect(providerErrorActionLabel({ category: 'rate_limit', message: 'Too Many Requests' })).toBe('Too Many Requests')
  })
})

describe('stageLabel', () => {
  it('humanizes known stages', () => {
    expect(stageLabel('fetch_usage')).toBe('Fetch usage')
    expect(stageLabel('oauth_refresh')).toBe('OAuth refresh')
  })

  it('falls back to spaced raw stage', () => {
    expect(stageLabel('custom_stage')).toBe('custom stage')
  })

  it('returns null for missing stage', () => {
    expect(stageLabel(null)).toBeNull()
    expect(stageLabel(undefined)).toBeNull()
  })
})
