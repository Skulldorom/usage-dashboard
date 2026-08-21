import { describe, it, expect } from 'vitest'
import {
  bucketWallClock,
  changeStatus,
  chartPoints,
  compactNumber,
  confidenceColor,
  formatMetricValue,
  isDeltaMetric,
  peakLabel,
  primaryValue,
  rangeToParams,
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
    expect(formatMetricValue(null, 'credits')).toBe('—')
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
    expect(peakLabel(null)).toBe('—')
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
