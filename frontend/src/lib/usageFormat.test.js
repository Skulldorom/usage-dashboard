import { describe, it, expect } from 'vitest'
import {
  alertMessage,
  alertSeverity,
  codexRemainingValue,
  firecrawlSummary,
  formatAge,
  formatDateTime,
  formatMetricLabel,
  formatMetricValue,
  formatThresholdRule,
  healthMeta,
  healthText,
  metricPercent,
  numericMetric,
  selectHistoryMetric,
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
