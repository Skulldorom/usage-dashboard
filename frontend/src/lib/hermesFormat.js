export function fmt(value, unit) {
  if (value === null || value === undefined) return '—'
  const n = Number(value)
  const text = Math.abs(n) >= 1000 ? n.toLocaleString(undefined, { maximumFractionDigits: 0 }) : String(Math.round(n * 100) / 100)
  return unit ? `${text} ${unit}` : text
}

export function money(value) {
  return value === null || value === undefined ? '—' : `$${Number(value).toFixed(2)}`
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
  return hermesHeadlineCards(data).some((card) => !String(card.value).startsWith('—') && !String(card.value).startsWith('0 sessions'))
}
