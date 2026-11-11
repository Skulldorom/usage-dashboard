import React from 'react'
import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { OpenRouterAnalyticsPanel, openRouterAnalyticsState } from './UsagePage.jsx'

const renderPanel = (props) => renderToString(React.createElement(OpenRouterAnalyticsPanel, { groupBy: 'workspace', onGroupBy: () => {}, ...props }))

const states = ['ready', 'empty', 'partial', 'stale', 'unavailable', 'unsupported', 'unauthorized']

it.each(states)('preserves the %s response state', (state) => {
  expect(openRouterAnalyticsState({ state }).state).toBe(state)
})

it('renders response errors instead of hiding failed analytics requests', () => {
  expect(renderPanel({ data: null, error: 'Forbidden' })).toContain('OpenRouter Analytics request failed:')
  expect(renderPanel({ data: null, error: 'Forbidden' })).toContain('Forbidden')
})

it('renders scope, workspace, and declared grouping without claiming unsupported groups', () => {
  const html = renderPanel({ data: { state: 'ready', scope: 'account', workspace: 'ws_alpha', grouping: 'workspace', totals: {}, groups: [{ dimension: 'model', value: 'wrong', totals: {} }, { dimension: 'workspace', value: 'ws_alpha', totals: {} }] } })
  expect(html).toContain('Workspace: ws_alpha')
  expect(html).toContain('Grouping:')
  expect(html).toContain('workspace')
  expect(html).toContain('ws_alpha')
  expect(html).not.toContain('wrong')
})

it('renders all non-ready contract states with their truthful labels', () => {
  expect(renderPanel({ data: { state: 'partial' } })).toContain('data is partial')
  expect(renderPanel({ data: { state: 'stale' } })).toContain('data is stale')
  expect(renderPanel({ data: { state: 'unsupported' } })).toContain('unsupported')
  expect(renderPanel({ data: { state: 'unauthorized' } })).toContain('unauthorized')
})

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
    expect(openRouterAnalyticsState(null)).toMatchObject({ state: 'unavailable', rows: [], scope: null })
    expect(openRouterAnalyticsState({ ...response, state: 'empty', groups: [] })).toMatchObject({ state: 'empty', rows: [] })
    expect(openRouterAnalyticsState({ ...response, state: 'unavailable' })).toMatchObject({ state: 'unavailable', rows: [], scope: null })
  })
})
