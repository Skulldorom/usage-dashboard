import { compactNumber, formatMoney, providerNameWithLabel } from './analyticsFormat.js'

export const WORKLOAD_METRICS = [
  { value: 'tokens', label: 'Tokens' },
  { value: 'cost', label: 'Cost' },
  { value: 'requests', label: 'Requests' },
  { value: 'sessions', label: 'Sessions' },
]

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

export function quotaStatus(window, quality = 'healthy') {
  if (quality === 'stale' || quality === 'unavailable') return quality
  if (window?.used_pct === null || window?.used_pct === undefined) return 'unavailable'
  if (window.used_pct >= 100) return 'exhausted'
  if (window.used_pct >= 70) return 'warning'
  return 'healthy'
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
      tokens: observed?.tokens ?? economic?.observed?.tokens ?? (provider.unit === 'tokens' ? provider.value : null),
      requests: observed?.requests ?? (provider.unit === 'requests' ? provider.value : null),
      sessions: observed?.sessions ?? null,
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
