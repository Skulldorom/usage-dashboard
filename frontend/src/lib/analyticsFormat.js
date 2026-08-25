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
  if (value === null || value === undefined) return '-'
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

export function clampPercent(value) {
  return Math.max(0, Math.min(100, Number(value)))
}

export function shouldDisplayPercentUsed(metric, metricType, unit) {
  const normalized = String(metric || '').toLowerCase().replaceAll('-', '_').replaceAll(' ', '_')
  if (unit !== '%') return false
  if (normalized.includes('remaining_percent') || normalized.includes('_remaining_') || normalized.endsWith('_remaining')) return true
  return metricType === 'remaining'
}

export function displayUsageValue(value, { metric, metricType, unit } = {}) {
  if (typeof value !== 'number') return value ?? null
  if (shouldDisplayPercentUsed(metric, metricType, unit)) return Math.max(0, 100 - value)
  return value
}

export function usageAxisLabel({ metric, metricType, unit } = {}) {
  if (shouldDisplayPercentUsed(metric, metricType, unit)) return 'used (%)'
  if (metricType === 'counter' || metricType === 'rate_limit') return `usage (${unit || ''})`.trim()
  return unit || ''
}

export function usageMetricLabel(label, metricType, unit) {
  if (shouldDisplayPercentUsed(label, metricType, unit)) return String(label || '').replace(/remaining/gi, 'used').replaceAll('_', ' ')
  return String(label || '').replaceAll('_', ' ')
}

export function chartPoints(buckets, metricType, options = {}) {
  return (buckets || []).map((bucket) => ({
    x: bucket.start,
    value: displayUsageValue(primaryValue(bucket, metricType), { ...options, metricType }),
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
  if (peakHour === null || peakHour === undefined) return '-'
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

export function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${compactNumber(value)}%`
}

export function formatTrend(value, suffix = '%') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'No comparable data'
  const sign = Number(value) > 0 ? '+' : ''
  return `${sign}${compactNumber(value)}${suffix}`
}

export function qualityLabel(quality) {
  return {
    full: 'Full',
    partial: 'Partial',
    limited: 'Limited',
    estimated: 'Estimated',
    stale: 'Stale',
    unavailable: 'Unavailable',
  }[quality] || 'Limited'
}

export function pressureSummaryCards(overview) {
  const pressure = overview?.pressure || {}
  const coverage = overview?.coverage || pressure.coverage || {}
  const highest = overview?.highest_utilization
  return [
    {
      key: 'pressure',
      label: 'Provider Pressure',
      value: formatPercent(overview?.provider_pressure_pct ?? pressure.provider_pressure_pct),
      detail: `${coverage.measurable_provider_count ?? 0} of ${coverage.total_provider_count ?? 0} providers measurable`,
    },
    {
      key: 'highest',
      label: 'Highest Utilization',
      value: highest ? `${highest.provider}${highest.label && highest.label !== 'main' ? ` · ${highest.label}` : ''}` : '-',
      detail: highest ? `${formatPercent(highest.utilization_pct)} used${highest.reset_at ? ` · resets ${new Date(highest.reset_at).toLocaleString()}` : ''}` : 'No measurable providers',
    },
    {
      key: 'burn',
      label: 'Burn Rate / Pace',
      value: formatTrend(pressure.trend_pct ?? null, ' pts'),
      detail: 'Normalized movement vs. previous comparable period',
    },
    {
      key: 'coverage',
      label: 'Data Coverage',
      value: `${coverage.providers_with_history ?? 0} history · ${coverage.providers_with_forecasts ?? 0} forecasts`,
      detail: `${coverage.stale_or_unavailable_provider_count ?? 0} stale/unavailable`,
    },
  ]
}

export function sortedCapacityProviders(providers) {
  return (providers || [])
    .filter((provider) => typeof provider.utilization_pct === 'number')
    .slice()
    .sort((a, b) => b.utilization_pct - a.utilization_pct)
}

export function unmeasurableProviders(providers) {
  return (providers || []).filter((provider) => typeof provider.utilization_pct !== 'number')
}

export function riskRows(overview) {
  if (overview?.risks?.length) return overview.risks
  return sortedCapacityProviders(overview?.providers).filter((provider) => provider.utilization_pct >= 70)
}

export function utilizationOverflowLabel(provider) {
  const utilization = provider?.utilization_pct
  if (typeof utilization !== 'number') return ''
  const overage = typeof provider?.overage_pct === 'number' ? provider.overage_pct : Math.max(0, utilization - 100)
  if (overage > 0) return `${formatPercent(utilization)} used · ${formatPercent(overage)} over allowance`
  return `${formatPercent(utilization)} used`
}

export function utilizationChartScale(comparison) {
  const values = (comparison || [])
    .flatMap((series) => series?.buckets || [])
    .map((bucket) => bucket?.value)
    .filter((value) => typeof value === 'number' && Number.isFinite(value))
  const max = Math.max(100, ...values)
  return Math.ceil(max / 25) * 25
}

export function activityDimensions(overview) {
  // Return [{ dimension, unit, label, total, providers }] in stable order.
  return (overview?.activity || []).map((dimension) => ({
    ...dimension,
    label: unitLabel(dimension.unit),
  }))
}

export function activityShareRows(dimension) {
  // Providers sorted desc by value, each with a normalized share fraction.
  const total = dimension?.total ?? 0
  return (dimension?.providers || [])
    .slice()
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0))
    .map((provider) => ({
      ...provider,
      shareFraction: total > 0 && provider.value !== null && provider.value !== undefined
        ? provider.value / total
        : 0,
    }))
}

export function activityChartScale(dimension) {
  const values = (dimension?.providers || [])
    .flatMap((provider) => provider?.buckets || [])
    .map((bucket) => bucket?.total)
    .filter((value) => typeof value === 'number' && Number.isFinite(value))
  if (values.length === 0) return 100
  const max = Math.max(...values)
  if (max <= 0) return 100
  // Round up to a "nice" number so the top of the axis isn't cramped.
  const magnitude = Math.pow(10, Math.floor(Math.log10(max)))
  return Math.ceil(max / magnitude) * magnitude
}

export function paceRatioLabel(paceRatio) {
  if (paceRatio === null || paceRatio === undefined || Number.isNaN(Number(paceRatio))) return null
  const ratio = Number(paceRatio)
  if (ratio > 1.05) return `${ratio.toFixed(2)}× sustainable pace`
  if (ratio < 0.95) return `${ratio.toFixed(2)}× sustainable pace`
  return 'on sustainable pace'
}

export function paceStatus(paceRatio) {
  if (paceRatio === null || paceRatio === undefined || Number.isNaN(Number(paceRatio))) return 'normal'
  const ratio = Number(paceRatio)
  if (ratio > 1.05) return 'warning'
  return 'normal'
}

export function hermesActivityLabel(activity) {
  const entries = Object.entries(activity || {})
    .filter(([, value]) => typeof value === 'number' && Number.isFinite(value) && value > 0)
    .sort(([a], [b]) => {
      const order = ['cost', 'input_tokens', 'output_tokens', 'requests', 'sessions']
      const ai = order.indexOf(a)
      const bi = order.indexOf(b)
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi) || a.localeCompare(b)
    })
  if (entries.length === 0) return null
  const pieces = entries.slice(0, 3).map(([metric, value]) => {
    const label = metric.replaceAll('_', ' ')
    if (metric === 'cost') return `${formatMetricValue(value, 'USD')} estimated cost`
    if (metric.includes('tokens')) return `${compactNumber(value)} ${label}`
    if (metric === 'requests') return `${compactNumber(value)} requests`
    return `${compactNumber(value)} ${label}`
  })
  const suffix = entries.length > 3 ? ` +${entries.length - 3} more` : ''
  return `Hermes observed: ${pieces.join(' · ')}${suffix}`
}
