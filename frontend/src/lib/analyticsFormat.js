// Pure formatting/data-shaping helpers for the Usage analytics page, extracted
// so filter/format logic is unit-testable without rendering React components.

export const RANGE_OPTIONS = [
  { value: '24h', label: '24 hours', days: 1 },
  { value: '7d', label: '7 days', days: 7 },
  { value: '30d', label: '30 days', days: 30 },
  { value: '90d', label: '90 days', days: 90 },
]

export const DEFAULT_RANGE = '30d'

export function compactNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return null
  const num = Number(value)
  if (!Number.isFinite(num)) return null
  const abs = Math.abs(num)
  if (abs >= 1_000_000) return `${(num / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
  if (abs >= 1_000) return `${(num / 1_000).toFixed(1).replace(/\.0$/, '')}k`
  if (Number.isInteger(num)) return String(num)
  return num.toFixed(2).replace(/\.?0+$/, '')
}

export function formatMetricValue(value, unit) {
  if (value === null || value === undefined) return '—'
  const suffix = unit ? (unit === '%' ? '%' : ` ${unit}`) : ''
  const compact = compactNumber(value)
  return `${compact ?? value}${suffix}`
}

export function isDeltaMetric(metricType) {
  return metricType === 'counter' || metricType === 'rate_limit'
}

export function primaryValue(bucket, metricType) {
  if (bucket == null) return null
  if (isDeltaMetric(metricType)) return bucket.total ?? null
  return bucket.value ?? null
}

export function chartPoints(buckets, metricType) {
  return (buckets || []).map((bucket) => ({
    x: bucket.start,
    value: primaryValue(bucket, metricType),
    raw: bucket,
  }))
}

export function confidenceColor(level) {
  return { high: 'success', medium: 'warning', low: 'error' }[level] || 'default'
}

export function changeStatus(changePct) {
  if (changePct === null || changePct === undefined) return 'Normal'
  if (changePct >= 20) return 'High'
  if (changePct <= -20) return 'Low'
  return 'Normal'
}

export function peakLabel(peakHour) {
  if (peakHour === null || peakHour === undefined) return '—'
  return `${String(peakHour).padStart(2, '0')}:00`
}

export function rangeToParams(range, now = new Date()) {
  const days = (RANGE_OPTIONS.find((option) => option.value === range)?.days) ?? 30
  const to = now.toISOString()
  const from = new Date(now.getTime() - days * 86_400_000).toISOString()
  return { from, to }
}

export function bucketWallClock(start) {
  // `start` is a timezone-aware ISO string (e.g. "2026-08-20T14:00:00-04:00").
  // Extract the wall-clock hour and day-of-week from the bucket's own offset
  // rather than the browser's local timezone, so cells land correctly around
  // timezone/DST boundaries regardless of the viewing machine's locale.
  const iso = String(start ?? '')
  const hour = Number.parseInt(iso.slice(11, 13), 10)
  let weekday = 0
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso.slice(0, 10))
  if (match) {
    const year = Number(match[1])
    const month = Number(match[2])
    const day = Number(match[3])
    weekday = (new Date(Date.UTC(year, month - 1, day)).getUTCDay() + 6) % 7
  }
  return { hour: Number.isNaN(hour) ? 0 : hour, weekday }
}

export function unitLabel(unit) {
  if (!unit) return ''
  if (unit === '%') return 'Quota used'
  if (unit === 'tokens') return 'Tokens'
  if (unit === 'requests') return 'Requests'
  if (unit === 'credits') return 'Credits'
  if (/^[A-Z]{3}$/.test(unit)) return `Cost (${unit})`
  return unit
}

export function overviewTotalCards(totals) {
  // Like-unit totals; "%" is a ratio and is excluded from summable cards.
  return Object.entries(totals || {})
    .filter(([unit]) => unit !== '%')
    .map(([unit, value]) => ({ unit, value, label: unitLabel(unit) }))
    .sort((a, b) => b.value - a.value)
}
