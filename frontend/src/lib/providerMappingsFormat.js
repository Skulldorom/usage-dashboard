import { fmt, money } from './hermesFormat.js'

export const LEAVE_UNMAPPED = '__leave_unmapped__'

export function observedMetrics(row) {
  const parts = []
  if (row.cost !== null && row.cost !== undefined) parts.push(money(row.cost))
  if (row.tokens !== null && row.tokens !== undefined) parts.push(fmt(row.tokens, 'tokens'))
  if (row.requests !== null && row.requests !== undefined) parts.push(fmt(row.requests, 'requests'))
  return parts.join(' · ') || '-'
}

export function selectValue(row) {
  return row.status === 'mapped' || row.status === 'invalid' ? row.mapped_to : LEAVE_UNMAPPED
}

export function mappingSummary(data) {
  if (!data) return ''
  const base = `${data.mapped_count} of ${data.observed.length} mapped`
  return data.unmapped_observations ? `${base} · ${data.unmapped_observations} observations unmapped` : base
}
