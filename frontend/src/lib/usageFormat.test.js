import { describe, it, expect } from 'vitest'
import {
  alertMessage,
  alertSeverity,
  codexRemainingValue,
  firecrawlSummary,
  formatDateTime,
  formatMetricLabel,
  formatMetricValue,
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
