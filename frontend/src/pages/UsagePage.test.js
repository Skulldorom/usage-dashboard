import { describe, expect, it } from 'vitest'
import { openRouterAnalyticsState } from './UsagePage.jsx'

describe('openRouterAnalyticsState', () => {
  it('keeps absent OpenRouter fields compatible and reports empty data', () => {
    expect(openRouterAnalyticsState({})).toEqual({ state: 'empty', rows: [], scope: null })
  })

  it('only exposes explicitly supplied scope and preserves breakdown rows', () => {
    const result = openRouterAnalyticsState({
      openrouter: { account_scope: 'workspace', completeness: { state: 'partial' } },
      activity: [{ dimension: 'spend', total: 12, providers: [{ provider: 'openrouter', label: 'workspace' }] }],
    })
    expect(result).toMatchObject({ state: 'partial', scope: 'workspace' })
    expect(result.rows[0].dimension).toBe('spend')
  })

  it('surfaces stale and unavailable states without inventing scope', () => {
    expect(openRouterAnalyticsState({ openrouter_analytics: { freshness: { state: 'stale' } } }).state).toBe('stale')
    expect(openRouterAnalyticsState({ openrouter_status: 'permission_or_upstream_error' })).toEqual({ state: 'unavailable', rows: [], scope: null })
  })
})
