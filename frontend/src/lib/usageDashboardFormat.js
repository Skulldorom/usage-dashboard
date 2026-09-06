import { compactNumber, formatMoney, providerNameWithLabel } from './analyticsFormat.js'

export const WORKLOAD_METRICS = [
  { value: 'tokens', label: 'Tokens' },
  { value: 'cost', label: 'Observed cost' },
  { value: 'requests', label: 'Requests' },
  { value: 'sessions', label: 'Sessions' },
]

export function workloadChartData(hermes, metric, grouping) {
  const series = grouping === 'provider' ? hermes?.daily_by_provider || [] : hermes?.daily_by_model || []
  const visible = series.filter((item) => item.points.some((point) => point[metric] !== null && point[metric] !== undefined))
  const observedDates = [...new Set(visible.flatMap((item) => item.points.map((point) => point.date)))].sort()
  const dates = []
  const start = new Date(hermes?.period?.start)
  const end = new Date(hermes?.period?.end)
  if (!Number.isNaN(start.getTime()) && !Number.isNaN(end.getTime())) {
    const cursor = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate()))
    while (cursor < end && dates.length < 100) {
      dates.push(cursor.toISOString().slice(0, 10))
      cursor.setUTCDate(cursor.getUTCDate() + 1)
    }
  }
  if (!dates.length) dates.push(...observedDates)
  const lookup = visible.map((item) => new Map(item.points.map((point) => [point.date, point[metric]])))
  const points = dates.map((date) => {
    const values = lookup.map((items) => items.get(date))
    const observed = values.some((value) => value !== null && value !== undefined)
    return {
      date,
      total: observed ? values.reduce((sum, value) => sum + Number(value ?? 0), 0) : null,
      values,
    }
  })
  return { series: visible, points }
}

export function workloadTooltipLabel({ date, key, value, total, metric, grouping }) {
  const formattedDate = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(`${date}T00:00:00Z`))
  if (total === null) return `${formattedDate} · No observation · Missing data is not zero`
  const metricName = WORKLOAD_METRICS.find((item) => item.value === metric)?.label || metric
  const source = metric === 'cost' ? 'Hermes observed cost' : 'Hermes observed'
  if (key === null || key === undefined) return `${formattedDate} · ${metricDisplay(total, metric)} ${metricName.toLowerCase()} · ${source}`
  const groupLabel = grouping === 'provider' ? providerNameWithLabel(key) : key
  const totalLabel = total === value ? '' : ` · Daily total ${metricDisplay(total, metric)}`
  return `${formattedDate} · ${groupLabel} · ${metricDisplay(value, metric)} ${metricName.toLowerCase()}${totalLabel} · ${source}`
}

export function totalValue(totals, metric) {
  return (totals || []).find((item) => item.metric === metric)?.value ?? null
}

export function usageSummary(hermes, economics, overview) {
  const subscriptions = (economics?.providers || []).filter((row) => row.pricing_model === 'subscription')
  const commitment = subscriptions.reduce((sum, row) => sum + Number(row.audit?.subscription?.amount || 0), 0)
  const paygRows = (economics?.providers || []).filter((row) => row.pricing_model === 'payg')
  const knownPayg = paygRows.filter((row) => row.actual_spend?.amount !== null && row.actual_spend?.amount !== undefined)
  const freeRows = (economics?.providers || []).filter((row) => row.pricing_model === 'free')
  const payg = knownPayg.reduce((sum, row) => sum + Number(row.actual_spend.amount), 0)
  const currencies = new Set([
    ...subscriptions.map((row) => row.audit?.subscription?.currency || 'USD'),
    ...knownPayg.map((row) => row.actual_spend.currency || 'USD'),
  ])
  const hasKnownPaidCost = subscriptions.length || knownPayg.length
  const cost = currencies.size <= 1 && hasKnownPaidCost
    ? commitment + payg
    : freeRows.length && !paygRows.length && !subscriptions.length ? 0 : null
  const activity = new Map((overview?.activity || []).map((row) => [row.dimension, row.total]))
  return {
    cost,
    currency: currencies.size === 1 ? [...currencies][0] : 'USD',
    commitment,
    payg,
    hasUnknownPayg: paygRows.length > knownPayg.length,
    tokens: totalValue(hermes?.totals, 'tokens') ?? activity.get('tokens') ?? null,
    requests: totalValue(hermes?.totals, 'requests') ?? activity.get('requests') ?? null,
    sessions: hermes?.sessions ?? null,
  }
}

export function selectedUsageSummary(base, selectedProvider, hermes, economics) {
  if (!selectedProvider) return { ...base, sharedWorkload: false }
  const economic = (economics?.providers || []).find((row) => row.config_id === selectedProvider.config_id)
  const cost = economic?.pricing_model === 'subscription'
    ? economic.audit?.subscription?.amount ?? null
    : economic?.actual_spend?.amount ?? (economic?.pricing_model === 'free' ? 0 : null)
  const ambiguous = Boolean(selectedProvider.attributionAmbiguous || economic?.attribution_ambiguous)
  const observed = ambiguous
    ? null
    : (hermes?.by_provider || []).find((row) => row.key === selectedProvider.provider)
  return {
    ...base,
    cost,
    currency: economic?.actual_spend?.currency || economic?.audit?.subscription?.currency || 'USD',
    commitment: economic?.pricing_model === 'subscription' ? cost || 0 : 0,
    payg: economic?.pricing_model === 'payg' && cost !== null ? cost : 0,
    tokens: ambiguous ? null : observed?.tokens ?? economic?.observed?.tokens ?? null,
    requests: ambiguous ? null : observed?.requests ?? null,
    sessions: ambiguous ? null : observed?.sessions ?? null,
    hasUnknownPayg: economic?.pricing_model === 'payg' && cost === null,
    sharedWorkload: ambiguous,
  }
}

export function quotaStatus(window, quality = 'healthy') {
  if (quality === 'stale' || quality === 'unavailable') return quality
  if (window?.used_pct === null || window?.used_pct === undefined) return 'unavailable'
  if (window.used_pct >= 100) return 'exhausted'
  if (window.used_pct >= 70) return 'warning'
  return 'healthy'
}

export function quotaTooltipLabel(window, quality = 'healthy') {
  const status = quotaStatus(window, quality)
  const label = String(window?.label || 'Quota').replace(/^./, (letter) => letter.toUpperCase())
  if (window?.used_pct === null || window?.used_pct === undefined) return `${label} · Quota unavailable · ${status}`
  const remaining = window.remaining_pct ?? Math.max(0, 100 - Number(window.used_pct))
  const reset = window.reset_at
    ? ` · Resets ${new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(window.reset_at))}`
    : ''
  const source = window.source ? ` · ${window.source.replaceAll('_', ' ')}` : ''
  return `${label} · ${Math.round(window.used_pct)}% used · ${Math.round(remaining)}% remaining · ${status}${reset}${source}`
}

export function billingLabel(row) {
  if (!row) return 'Billing unavailable'
  if (row.pricing_model === 'subscription') {
    const subscription = row.audit?.subscription
    if (subscription?.amount === null || subscription?.amount === undefined) return 'Subscription'
    const cadence = subscription.cadence === 'yearly' ? 'year' : 'month'
    return `${formatMoney(subscription.amount, subscription.currency)}/${cadence}`
  }
  if (row.pricing_model === 'free') return 'Free'
  return 'PAYG'
}

export function costPresentation(row) {
  if (!row) return { value: null, label: 'Unknown cost', source: null }
  if (row.pricing_model === 'subscription') {
    const commitment = row.audit?.subscription
    return {
      value: commitment?.amount ?? null,
      currency: commitment?.currency || 'USD',
      label: 'Subscription commitment',
      allocated: row.cost_basis?.amount ?? null,
    }
  }
  if (row.pricing_model === 'free') return { value: 0, currency: row.cost_basis?.currency || 'USD', label: 'Free' }
  return {
    value: row.actual_spend?.amount ?? null,
    currency: row.actual_spend?.currency || row.cost_basis?.currency || 'USD',
    label: row.actual_spend?.amount === null || row.actual_spend?.amount === undefined ? 'Spend unavailable' : 'Provider-reported spend',
  }
}

export function providerUsageRows(overview, economics, hermes) {
  const economicsById = new Map((economics?.providers || []).map((row) => [row.config_id, row]))
  const hermesByProvider = new Map((hermes?.by_provider || []).map((row) => [row.key, row]))
  return (overview?.providers || []).map((provider) => {
    const economic = economicsById.get(provider.config_id)
    const ambiguous = Boolean(economic?.attribution_ambiguous)
    const observed = ambiguous ? null : hermesByProvider.get(provider.provider)
    return {
      ...provider,
      displayName: providerNameWithLabel(provider.provider, provider.label, { disambiguate: provider.disambiguate }),
      billing: billingLabel(economic),
      cost: costPresentation(economic),
      tokens: ambiguous ? null : observed?.tokens ?? economic?.observed?.tokens ?? (provider.unit === 'tokens' ? provider.value : null),
      requests: ambiguous ? null : observed?.requests ?? (provider.unit === 'requests' ? provider.value : null),
      sessions: ambiguous ? null : observed?.sessions ?? null,
      attributionAmbiguous: ambiguous,
      pricingModel: economic?.pricing_model || null,
      quotaWindows: provider.quota_windows || [],
    }
  })
}

export function economicsRows(economics, hermes) {
  const grouped = new Map((hermes?.by_provider || []).map((row) => [row.key, row]))
  return (economics?.providers || []).map((row) => {
    const usage = row.attribution_ambiguous ? null : grouped.get(row.provider)
    const cost = costPresentation(row)
    const tokens = usage?.tokens ?? row.observed?.tokens ?? null
    const requests = usage?.requests ?? null
    const denominator = cost.value
    return {
      ...row,
      displayName: providerNameWithLabel(row.provider, row.label, { disambiguate: row.disambiguate }),
      cost,
      tokens,
      requests,
      sessions: usage?.sessions ?? null,
      tokensPerDollar: denominator > 0 && tokens !== null ? tokens / denominator : null,
      requestsPerDollar: denominator > 0 && requests !== null ? requests / denominator : null,
      costPerMillion: denominator > 0 && tokens > 0 ? denominator / tokens * 1_000_000 : null,
    }
  })
}

export function metricDisplay(value, metric) {
  if (value === null || value === undefined) return '—'
  if (metric === 'cost') return formatMoney(value)
  return compactNumber(value) ?? '—'
}

export function pricingQuality(hermes) {
  const estimate = hermes?.cost_estimate
  const total = Number(estimate?.total_tokens || 0)
  const unpriced = Number(estimate?.unpriced_tokens || 0)
  const priced = Math.max(0, total - unpriced)
  return {
    coverage: total > 0 ? priced / total * 100 : null,
    unpricedTokens: unpriced,
    unpricedModels: Object.keys(estimate?.unpriced?.models || {}),
    version: estimate?.pricing_version || null,
  }
}
