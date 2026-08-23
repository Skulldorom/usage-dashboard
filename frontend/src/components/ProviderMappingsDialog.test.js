import React from 'react'
import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ProviderMappingsTable } from './ProviderMappingsDialog.jsx'
import { mappingSummary, observedMetrics, selectValue } from '../lib/providerMappingsFormat.js'

const data = {
  source_id: 1,
  configured_providers: [
    { provider: 'codex', label: 'main' },
    { provider: 'deepseek', label: 'main' },
  ],
  mappings: { 'openai-codex': 'codex' },
  observed: [
    { raw_provider: 'auto', cost: null, tokens: 177969, requests: 13, observations: 3, last_observed_at: '2026-08-23T10:00:00Z', mapped_to: null, status: 'unmapped', reason: null },
    { raw_provider: 'openai-codex', cost: 9.4, tokens: 633532008, requests: 4804, observations: 5, last_observed_at: '2026-08-23T10:00:00Z', mapped_to: 'codex', status: 'mapped', reason: null },
    { raw_provider: 'unknown', cost: null, tokens: 60439, requests: 9, observations: 2, last_observed_at: '2026-08-23T10:00:00Z', mapped_to: 'anthropic', status: 'invalid', reason: "target provider 'anthropic' no longer exists" },
  ],
  mapped_count: 1,
  unmapped_count: 2,
  unmapped_observations: 5,
}

describe('provider mapping helpers', () => {
  it('formats observed metrics (cost, tokens, requests)', () => {
    expect(observedMetrics(data.observed[0])).toBe('177,969 tokens · 13 requests')
    expect(observedMetrics(data.observed[1])).toBe('$9.40 · 633,532,008 tokens · 4,804 requests')
  })

  it('builds the mapped/unmapped summary line', () => {
    expect(mappingSummary(data)).toBe('1 of 3 mapped · 5 observations unmapped')
  })

  it('resolves the dropdown value per status', () => {
    expect(selectValue(data.observed[0])).toBe('__leave_unmapped__') // unmapped
    expect(selectValue(data.observed[1])).toBe('codex') // mapped
    expect(selectValue(data.observed[2])).toBe('anthropic') // invalid keeps target
  })
})

describe('ProviderMappingsTable', () => {
  it('renders raw providers, status chips, and invalid reasons', () => {
    const html = renderToString(React.createElement(ProviderMappingsTable, { data, savingKey: null, onChange: () => {} }))
    expect(html).toContain('Hermes provider')
    expect(html).toContain('Maps to')
    expect(html).toContain('openai-codex')
    expect(html).toContain('auto')
    expect(html).toContain('Mapped')
    expect(html).toContain('Unmapped')
    expect(html).toContain('Invalid')
    expect(html).toContain('no longer exists')
    expect(html).toContain('anthropic')
    expect(html).toContain('(unavailable)')
  })
})
