import { describe, it, expect } from 'vitest'
import {
  bucketWallClock,
  changeStatus,
  chartPoints,
  compactNumber,
  confidenceColor,
  displayUsageValue,
  formatMetricValue,
  formatPercent,
  formatTrend,
  isDeltaMetric,
  overviewTotalCards,
  peakLabel,
  pressureSummaryCards,
  qualityLabel,
  primaryValue,
  rangeToParams,
  riskRows,
  sortedCapacityProviders,
  shouldDisplayPercentUsed,
  unitLabel,
  unmeasurableProviders,
  usageAxisLabel,
  usageMetricLabel,
  utilizationChartScale,
  utilizationOverflowLabel,
} from './analyticsFormat.js'

describe('compactNumber', () => {
  it('formats integers, thousands, and millions', () => {
    expect(compactNumber(42)).toBe('42')
    expect(compactNumber(1234)).toBe('1.2k')
    expect(compactNumber(2_500_000)).toBe('2.5M')
  })
  it('returns null for non-finite values', () => {
    expect(compactNumber(null)).toBeNull()
    expect(compactNumber(undefined)).toBeNull()
    expect(compactNumber(NaN)).toBeNull()
  })
})

describe('formatMetricValue', () => {
  it('formats percent and unit suffixes', () => {
    expect(formatMetricValue(63, '%')).toBe('63%')
    expect(formatMetricValue(382_000, 'tokens')).toBe('382k tokens')
  })
  it('renders an em-dash for missing values', () => {
    expect(formatMetricValue(null, 'credits')).toBe('-')
  })
})

describe('isDeltaMetric', () => {
  it('treats counters and rate limits as delta metrics', () => {
    expect(isDeltaMetric('counter')).toBe(true)
    expect(isDeltaMetric('rate_limit')).toBe(true)
    expect(isDeltaMetric('remaining')).toBe(false)
    expect(isDeltaMetric('balance')).toBe(false)
    expect(isDeltaMetric('gauge')).toBe(false)
    expect(isDeltaMetric('rolling_total')).toBe(false)
  })
})

describe('primaryValue', () => {
  it('uses total for delta metrics and value for point metrics', () => {
    expect(primaryValue({ total: 10, value: 5 }, 'counter')).toBe(10)
    expect(primaryValue({ total: 10, value: 5 }, 'remaining')).toBe(5)
  })
  it('returns null for missing buckets', () => {
    expect(primaryValue(null, 'counter')).toBeNull()
  })
})

describe('chartPoints', () => {
  it('maps buckets to chart points using the metric type', () => {
    const buckets = [
      { start: '2026-08-20', total: 10, value: 5 },
      { start: '2026-08-21', total: 20, value: 8 },
    ]
    const points = chartPoints(buckets, 'counter')
    expect(points.map((p) => p.value)).toEqual([10, 20])
    expect(points.map((p) => p.x)).toEqual(['2026-08-20', '2026-08-21'])
  })

  it('converts percent-remaining metrics into percent-used chart values', () => {
    const buckets = [
      { start: '2026-08-20', value: 90 },
      { start: '2026-08-21', value: 80 },
    ]
    const points = chartPoints(buckets, 'remaining', { metric: 'session_remaining_percent', unit: '%' })
    expect(points.map((p) => p.value)).toEqual([10, 20])
  })
})

describe('percent-used display helpers', () => {
  it('detects remaining percent metrics and clamps converted values', () => {
    expect(shouldDisplayPercentUsed('session_remaining_percent', 'remaining', '%')).toBe(true)
    expect(shouldDisplayPercentUsed('usage_percent', 'gauge', '%')).toBe(false)
    expect(displayUsageValue(120, { metric: 'session_remaining_percent', metricType: 'remaining', unit: '%' })).toBe(0)
    expect(displayUsageValue(-28, { metric: 'session_remaining_percent', metricType: 'remaining', unit: '%' })).toBe(128)
  })

  it('labels converted metrics as used', () => {
    expect(usageAxisLabel({ metric: 'weekly_remaining_percent', metricType: 'remaining', unit: '%' })).toBe('used (%)')
    expect(usageMetricLabel('session_remaining_percent', 'remaining', '%')).toBe('session used percent')
  })
})

describe('confidenceColor', () => {
  it('maps levels to MUI color tokens', () => {
    expect(confidenceColor('high')).toBe('success')
    expect(confidenceColor('medium')).toBe('warning')
    expect(confidenceColor('low')).toBe('error')
  })
})

describe('changeStatus', () => {
  it('classifies period-over-period change', () => {
    expect(changeStatus(25)).toBe('High')
    expect(changeStatus(-25)).toBe('Low')
    expect(changeStatus(5)).toBe('Normal')
    expect(changeStatus(null)).toBe('Normal')
  })
})

describe('peakLabel', () => {
  it('formats hour of day with leading zero', () => {
    expect(peakLabel(14)).toBe('14:00')
    expect(peakLabel(5)).toBe('05:00')
    expect(peakLabel(null)).toBe('-')
  })
})

describe('rangeToParams', () => {
  it('produces from/to ISO params for a range', () => {
    const now = new Date('2026-08-21T12:00:00Z')
    const params = rangeToParams('7d', now)
    expect(params.to).toBe('2026-08-21T12:00:00.000Z')
    expect(params.from).toBe('2026-08-14T12:00:00.000Z')
  })
  it('defaults to 30 days for unknown ranges', () => {
    const now = new Date('2026-08-21T12:00:00Z')
    const params = rangeToParams('nope', now)
    expect(params.from).toBe('2026-07-22T12:00:00.000Z')
  })
})

describe('bucketWallClock', () => {
  it('derives hour and Monday-first weekday from the bucket offset', () => {
    // 2026-08-20 is a Thursday; Monday-first indexing => Thursday = 3.
    expect(bucketWallClock('2026-08-20T14:00:00-04:00')).toEqual({ hour: 14, weekday: 3 })
    // 2026-08-24 is a Monday => 0.
    expect(bucketWallClock('2026-08-24T00:00:00+00:00')).toEqual({ hour: 0, weekday: 0 })
  })
  it('falls back to hour 0 / Monday for empty input', () => {
    expect(bucketWallClock(null)).toEqual({ hour: 0, weekday: 0 })
    expect(bucketWallClock(undefined)).toEqual({ hour: 0, weekday: 0 })
  })
})

describe('unitLabel', () => {
  it('maps known units to friendly labels', () => {
    expect(unitLabel('tokens')).toBe('Tokens')
    expect(unitLabel('requests')).toBe('Requests')
    expect(unitLabel('credits')).toBe('Credits')
    expect(unitLabel('%')).toBe('Quota used')
    expect(unitLabel('USD')).toBe('Cost (USD)')
    expect(unitLabel('')).toBe('')
  })
})

describe('overviewTotalCards', () => {
  it('excludes percent and sorts by value descending', () => {
    const cards = overviewTotalCards({ tokens: 100, USD: 42, '%': 80, credits: 10 })
    expect(cards.map((c) => c.unit)).toEqual(['tokens', 'USD', 'credits'])
    expect(cards[0].label).toBe('Tokens')
  })
  it('returns an empty list for empty totals', () => {
    expect(overviewTotalCards(null)).toEqual([])
    expect(overviewTotalCards({})).toEqual([])
  })
})

describe('overview pressure helpers', () => {
  const overview = {
    provider_pressure_pct: 62.5,
    pressure: { trend_pct: 7.5 },
    coverage: {
      measurable_provider_count: 2,
      total_provider_count: 3,
      providers_with_history: 1,
      providers_with_forecasts: 2,
      stale_or_unavailable_provider_count: 0,
    },
    highest_utilization: { provider: 'openrouter', label: 'main', utilization_pct: 75 },
    providers: [
      { config_id: 1, provider: 'codex', utilization_pct: 50, quality: 'partial' },
      { config_id: 2, provider: 'openrouter', utilization_pct: 75, quality: 'partial' },
      { config_id: 3, provider: 'deepseek', utilization_pct: null, exclusion_reason: 'No normalizable quota/capacity metric' },
    ],
    risks: [{ config_id: 2, provider: 'openrouter', utilization_pct: 75, state: 'warning' }],
  }

  it('formats percent/trend summaries', () => {
    expect(formatPercent(62.5)).toBe('62.5%')
    expect(formatTrend(7.5, ' pts')).toBe('+7.5 pts')
    expect(formatTrend(null)).toBe('No comparable data')
  })

  it('builds top-level pressure cards with coverage', () => {
    const cards = pressureSummaryCards(overview)
    expect(cards[0]).toMatchObject({ label: 'Provider Pressure', value: '62.5%', detail: '2 of 3 providers measurable' })
    expect(cards[1].detail).toContain('75% used')
    expect(cards[3].value).toBe('1 history · 2 forecasts')
  })

  it('sorts measurable providers and separates unmeasurable providers', () => {
    expect(sortedCapacityProviders(overview.providers).map((p) => p.provider)).toEqual(['openrouter', 'codex'])
    expect(unmeasurableProviders(overview.providers).map((p) => p.provider)).toEqual(['deepseek'])
  })

  it('uses backend risks and labels quality states', () => {
    expect(riskRows(overview)).toEqual(overview.risks)
    expect(qualityLabel('partial')).toBe('Partial')
    expect(qualityLabel('wat')).toBe('Limited')
  })

  it('labels utilization overflow separately from progress-bar clamping', () => {
    expect(utilizationOverflowLabel({ utilization_pct: 128, overage_pct: 28 })).toBe('128% used · 28% over allowance')
    expect(utilizationOverflowLabel({ utilization_pct: 75 })).toBe('75% used')
  })

  it('extends utilization chart scale above the quota line', () => {
    expect(utilizationChartScale([{ buckets: [{ value: 40 }, { value: 128 }] }])).toBe(150)
    expect(utilizationChartScale([{ buckets: [{ value: 40 }, { value: 80 }] }])).toBe(100)
  })
})
