import React from 'react'
import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import {
  hasHermesData,
  hermesHeadlineCards,
  hermesTotalMap,
} from '../lib/hermesFormat.js'
import {
  HermesDataSourcesCards,
  HermesSourceCard,
} from './HermesPanels.jsx'

const hermesData = {
  totals: [
    { metric: 'tokens', unit: 'tokens', value: 2400 },
    { metric: 'input_tokens', unit: 'tokens', value: 1400 },
    { metric: 'output_tokens', unit: 'tokens', value: 1000 },
    { metric: 'requests', unit: 'count', value: 42 },
    { metric: 'cost', unit: 'USD', value: 1.23 },
  ],
  sessions: 7,
  sources: [
    {
      id: 1,
      name: 'Hermes main',
      status: 'healthy',
      observations_in_range: 5,
      total_observations: 9,
      latest_observation_at: '2026-08-23T12:00:00Z',
      providers_observed: ['anthropic', 'openrouter'],
      providers_unmapped: [],
    },
  ],
}

describe('HermesPanels helpers', () => {
  it('maps Hermes totals and builds headline cards', () => {
    expect(hermesTotalMap(hermesData.totals).tokens.value).toBe(2400)
    const cards = hermesHeadlineCards(hermesData)
    expect(cards.map((card) => card.label)).toContain('Observed tokens')
    expect(cards.find((card) => card.key === 'cost').value).toBe('$1.23')
    expect(cards.find((card) => card.key === 'sessions').value).toBe('7 sessions')
  })

  it('distinguishes empty Hermes payloads from observed telemetry', () => {
    expect(hasHermesData(hermesData)).toBe(true)
    expect(hasHermesData({ totals: [], sessions: 0 })).toBe(false)
  })
})

describe('HermesDataSourcesCards', () => {
  it('renders data source status and supplemental wording targets', () => {
    const html = renderToString(React.createElement(HermesDataSourcesCards, { data: hermesData, compact: true }))
    expect(html).toContain('Data Sources')
    expect(html).toContain('Hermes main')
    expect(html).toContain('healthy')
    expect(html).toMatch(/5<!-- --> observations in selected range|5 observations in selected range/)
    expect(html).toContain('/usage')
  })

  it('surfaces unmapped provider warnings on source cards', () => {
    const source = {
      ...hermesData.sources[0],
      providers_unmapped: ['mystery'],
    }
    const html = renderToString(React.createElement(HermesSourceCard, { source }))
    expect(html).toContain('Unmapped')
    expect(html).toContain('mystery')
  })
})
