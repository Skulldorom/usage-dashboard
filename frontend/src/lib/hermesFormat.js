export function fmt(value, unit) {
  if (value === null || value === undefined) return '-'
  const n = Number(value)
  const text = Math.abs(n) >= 1000 ? n.toLocaleString(undefined, { maximumFractionDigits: 0 }) : String(Math.round(n * 100) / 100)
  return unit ? `${text} ${unit}` : text
}

export function money(value) {
  return value === null || value === undefined ? '-' : `$${Number(value).toFixed(2)}`
}

export function hermesTotalMap(totals = []) {
  return Object.fromEntries(totals.map((item) => [item.metric, item]))
}

export function hermesHeadlineCards(data) {
  const totals = hermesTotalMap(data?.totals || [])
  return [
    { key: 'tokens', label: 'Observed tokens', value: fmt(totals.tokens?.value, 'tokens') },
    { key: 'input_tokens', label: 'Input tokens', value: fmt(totals.input_tokens?.value, 'tokens') },
    { key: 'output_tokens', label: 'Output tokens', value: fmt(totals.output_tokens?.value, 'tokens') },
    { key: 'requests', label: 'Requests', value: fmt(totals.requests?.value, 'requests') },
    { key: 'cost', label: 'Observed cost', value: money(totals.cost?.value) },
    { key: 'sessions', label: 'Sessions', value: fmt(data?.sessions, 'sessions') },
  ]
}

export function hasHermesData(data) {
  return hermesHeadlineCards(data).some((card) => !String(card.value).startsWith('-') && !String(card.value).startsWith('0 sessions'))
}

export function estimatedCostTotal(estimate) {
  if (!estimate || estimate.total_cost === null || estimate.total_cost === undefined) return null
  return Number(estimate.total_cost)
}

export function estimatedCostCards(estimate) {
  // Build headline cards for the derived estimated-cost block, distinct from
  // provider/Hermes-reported cost. Returns [] when no estimate is present.
  const cards = []
  const total = estimatedCostTotal(estimate)
  const pricedTokens = estimate?.total_tokens ?? 0
  const unpricedTokens = estimate?.unpriced_tokens ?? 0
  const unpricedModels = Object.keys(estimate?.unpriced?.models ?? {})
  if (total === null && !pricedTokens && !unpricedTokens && unpricedModels.length === 0) return cards
  if (total !== null) cards.push({ key: 'estimated_cost', label: 'Estimated cost', value: money(total) })
  if (pricedTokens) cards.push({ key: 'priced_tokens', label: 'Priced tokens', value: fmt(pricedTokens, 'tokens') })
  if (unpricedTokens) cards.push({ key: 'unpriced_tokens', label: 'Unpriced tokens', value: fmt(unpricedTokens, 'tokens') })
  if (unpricedModels.length) cards.push({ key: 'unpriced_models', label: 'Unpriced models', value: String(unpricedModels.length) })
  return cards
}

export function estimatedCostNote(estimate) {
  if (!estimate) return ''
  const parts = [`Pricing catalogue ${estimate.pricing_version || 'unknown'}`]
  const unpricedModels = Object.keys(estimate?.unpriced?.models ?? {})
  if (unpricedModels.length) {
    parts.push(`unpriced: ${unpricedModels.join(', ')}`)
  }
  return parts.join(' · ')
}
