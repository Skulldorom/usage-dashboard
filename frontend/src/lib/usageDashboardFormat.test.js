import React from 'react'
import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { Overview, WorkloadChart } from '../pages/UsageDashboardPage.jsx'
import { WORKLOAD_METRICS, billingLabel, costPresentation, providerUsageRows, quotaStatus, selectedUsageSummary, usageSummary, workloadChartData } from './usageDashboardFormat.js'

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

it('preserves missing chart days instead of converting them to zero', () => {
  const hermes = {
    period: { start: '2026-09-01T00:00:00Z', end: '2026-09-04T00:00:00Z' },
    daily_by_provider: [{ key: 'codex', points: [
      { date: '2026-09-01', tokens: 100 },
      { date: '2026-09-03', tokens: 200 },
    ] }],
  }
  const chart = workloadChartData(hermes, 'tokens', 'provider')
  expect(chart.points.map((point) => point.total)).toEqual([100, null, 200])
  const html = renderToString(React.createElement(WorkloadChart, { hermes, metric: 'tokens', grouping: 'provider' }))
  expect(html).toContain('2026-09-02 missing')
  expect(html).toContain('2026-09-02: No observation')
})

it('renders observed zero distinctly from a missing chart sample', () => {
  const hermes = {
    period: { start: '2026-09-01T00:00:00Z', end: '2026-09-03T00:00:00Z' },
    daily_by_provider: [{ key: 'codex', points: [{ date: '2026-09-01', tokens: 0 }] }],
  }
  const chart = workloadChartData(hermes, 'tokens', 'provider')
  expect(chart.points.map((point) => point.total)).toEqual([0, null])
  const html = renderToString(React.createElement(WorkloadChart, { hermes, metric: 'tokens', grouping: 'provider' }))
  expect(html).toContain('2026-09-01 observed zero')
  expect(html).toContain('2026-09-02 missing')
})

it('does not assign provider-level Hermes workload to an ambiguous selected config', () => {
  const hermes = { by_provider: [{ key: 'codex', tokens: 539_000_000, requests: 5053, sessions: 41 }], totals: [] }
  const economics = { providers: [
    { ...subscription, config_id: 1, label: 'work', attribution_ambiguous: true },
    { ...subscription, config_id: 2, label: 'personal', attribution_ambiguous: true },
  ] }
  const providers = providerUsageRows({ providers: [
    { config_id: 1, provider: 'codex', label: 'work', disambiguate: true },
    { config_id: 2, provider: 'codex', label: 'personal', disambiguate: true },
  ] }, economics, hermes)
  expect(providers.map((row) => row.tokens)).toEqual([null, null])
  const selectedProvider = providers[0]
  const summary = selectedUsageSummary(usageSummary(hermes, economics), selectedProvider, hermes, economics)
  expect(summary).toMatchObject({ tokens: null, requests: null, sessions: null, sharedWorkload: true })
  const html = renderToString(React.createElement(Overview, { hermes, economics, overview: null, selectedProvider }))
  expect(html).toContain('Shared provider workload cannot be attributed to this config')
  expect(html).not.toContain('539M')
  expect(html).not.toContain('5.1k')
})

it('labels the chart cost metric with Hermes provenance', () => {
  expect(WORKLOAD_METRICS.find((item) => item.value === 'cost').label).toBe('Observed cost')
})
