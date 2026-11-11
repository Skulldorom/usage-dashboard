import { describe, expect, it } from 'vitest'
import { openRouterAnalyticsState } from './UsagePage.jsx'

const response = {
  config_id: 7,
  scope: 'account',
  state: 'ready',
  start: '2026-10-01T00:00:00Z',
  end: '2026-11-01T00:00:00Z',
  last_success_at: '2026-10-31T00:00:00Z',
  totals: { openrouter_account_spend: 12.5, openrouter_account_requests: 8 },
  groups: [{ dimension: 'workspace', value: 'ws_alpha', totals: { openrouter_account_spend: 12.5, openrouter_account_requests: 8 } }],
  coverage: { first_observed_at: '2026-10-01T00:00:00Z', last_observed_at: '2026-10-31T00:00:00Z', samples: 31 },
}

describe('openRouterAnalyticsState', () => {
  it('consumes the provider-scoped OpenRouter response without overview fields', () => {
    expect(openRouterAnalyticsState(response)).toMatchObject({
      state: 'ready', scope: 'account', totals: response.totals, lastSuccessAt: response.last_success_at,
    })
    expect(openRouterAnalyticsState(response).rows).toEqual(response.groups)
  })

  it('keeps unavailable and empty endpoint states truthful', () => {
    expect(openRouterAnalyticsState(null)).toEqual({ state: 'unavailable', rows: [], scope: null })
    expect(openRouterAnalyticsState({ ...response, state: 'empty', groups: [] })).toMatchObject({ state: 'empty', rows: [] })
    expect(openRouterAnalyticsState({ ...response, state: 'unavailable' })).toEqual({ state: 'unavailable', rows: [], scope: null })
  })
})
