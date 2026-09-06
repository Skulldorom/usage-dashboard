import { describe, expect, it } from 'vitest'
import { billingLabel, costPresentation, providerUsageRows, quotaStatus, usageSummary } from './usageDashboardFormat.js'

const subscription = {
  config_id: 1, provider: 'codex', label: 'main', pricing_model: 'subscription', observed: { tokens: 100 },
  cost_basis: { amount: 9.67, currency: 'USD' }, actual_spend: null,
  audit: { subscription: { amount: 20, currency: 'USD', cadence: 'monthly' } },
}

it('keeps subscription commitment distinct from selected-range allocation', () => {
  expect(billingLabel(subscription)).toBe('$20.00/month')
  expect(costPresentation(subscription)).toMatchObject({ value: 20, allocated: 9.67, label: 'Subscription commitment' })
})

it('does not turn unknown PAYG spend into zero but preserves genuine free zero', () => {
  expect(costPresentation({ pricing_model: 'payg', cost_basis: { amount: null, currency: 'USD' } }).value).toBeNull()
  expect(costPresentation({ pricing_model: 'free', cost_basis: { amount: 0, currency: 'USD' } }).value).toBe(0)
  expect(usageSummary({ totals: [] }, { providers: [{ pricing_model: 'free' }] }).cost).toBe(0)
  expect(usageSummary({ totals: [] }, { providers: [{ pricing_model: 'payg', actual_spend: null }] }).cost).toBeNull()
})

it('summarizes commitments and reported PAYG without using prorated cost', () => {
  const summary = usageSummary({ totals: [{ metric: 'tokens', value: 500 }], sessions: 4 }, {
    providers: [subscription, { pricing_model: 'payg', actual_spend: { amount: 11.48, currency: 'USD' } }],
  })
  expect(summary).toMatchObject({ cost: 31.48, commitment: 20, payg: 11.48, tokens: 500, sessions: 4 })
})

describe('quota window states', () => {
  it.each([[100, 'exhausted'], [85, 'warning'], [50, 'healthy']])('maps %s used to %s', (used_pct, status) => {
    expect(quotaStatus({ used_pct })).toBe(status)
  })
  it('keeps missing quota unavailable and stale data stale', () => {
    expect(quotaStatus({ used_pct: null })).toBe('unavailable')
    expect(quotaStatus({ used_pct: 20 }, 'stale')).toBe('stale')
  })
})

it('preserves every Codex and OpenCode quota window and each reset', () => {
  const providers = providerUsageRows({ providers: [
    { config_id: 1, provider: 'codex', label: 'main', quota_windows: [{ label: 'session', reset_at: 'a' }, { label: 'weekly', reset_at: 'b' }] },
    { config_id: 2, provider: 'opencode-go', label: 'main', quota_windows: [{ label: '5h', reset_at: 'c' }, { label: 'weekly', reset_at: 'd' }, { label: 'monthly', reset_at: 'e' }] },
  ] }, { providers: [subscription] }, { by_provider: [] })
  expect(providers[0].quotaWindows.map((row) => row.reset_at)).toEqual(['a', 'b'])
  expect(providers[1].quotaWindows).toHaveLength(3)
})
