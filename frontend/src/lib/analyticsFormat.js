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
