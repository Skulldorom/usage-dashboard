import { describe, expect, it } from 'vitest'
import {
  auditRows,
  confidenceLabel,
  hasAuditData,
  reconciliationWarnings,
  sourceLabel,
} from '../lib/auditFormat.js'

const provider = {
  provider: 'anthropic',
  label: 'main',
  confidence: 'medium',
  audit: {
    capacity: {
      value: 128.0,
      unit: '%',
      authoritative_source: 'native',
      window_end: '2026-08-25T10:00:00Z',
      reset_at: '2026-08-28T00:00:00Z',
      confidence: 'medium',
      reconciliation: { has_disagreement: false, stale_authoritative: false, disagreements: [] },
    },
    activity: {
      value: 54200000,
      unit: 'tokens',
      authoritative_source: 'native',
      estimated_cost: 4.5,
      estimated_cost_source: 'pricing 2026-08-25.1',
      reconciliation: { has_disagreement: false, stale_authoritative: false, disagreements: [] },
    },
    corroborating_sources: ['hermes'],
  },
}

describe('sourceLabel', () => {
  it('maps source ids to readable labels', () => {
    expect(sourceLabel('native')).toBe('Provider-native')
    expect(sourceLabel('snapshot')).toBe('Snapshot-derived')
    expect(sourceLabel('hermes')).toBe('Hermes-observed')
    expect(sourceLabel('estimated')).toBe('Estimated')
    expect(sourceLabel('unknown-thing')).toBe('unknown-thing')
    expect(sourceLabel(null)).toBe('-')
  })
})

describe('confidenceLabel', () => {
  it('capitalizes confidence levels', () => {
    expect(confidenceLabel('high')).toBe('High')
    expect(confidenceLabel('medium')).toBe('Medium')
    expect(confidenceLabel(null)).toBe('-')
  })
})

describe('auditRows', () => {
  it('builds capacity, activity, and corroborating rows', () => {
    const rows = auditRows(provider)
    const labels = rows.map((row) => `${row.section}:${row.label}`)
    expect(labels).toContain('Capacity:Value')
    expect(labels).toContain('Capacity:Authoritative source')
    expect(labels).toContain('Activity:Value')
    expect(labels).toContain('Activity:Estimated cost')
    expect(labels).toContain('Sources:Corroborated by')

    const capacityValue = rows.find((row) => row.section === 'Capacity' && row.label === 'Value')
    expect(capacityValue.value).toBe('128%')
    const activityValue = rows.find((row) => row.section === 'Activity' && row.label === 'Value')
    expect(activityValue.value).toBe('54200000 tokens')
    const estimated = rows.find((row) => row.label === 'Estimated cost')
    expect(estimated.value).toContain('$4.50')
  })

  it('omits sections with no value', () => {
    const minimal = {
      audit: {
        capacity: {},
        activity: {},
        corroborating_sources: [],
      },
    }
    expect(auditRows(minimal)).toEqual([])
  })

  it('surfaces quota-impact correlation rows', () => {
    const withImpact = {
      audit: {
        capacity: {},
        activity: {},
        corroborating_sources: [],
        quota_impact: { estimated_impact_per_token: 0.01, sample_size: 4, confidence: 'high', unattributed_pct: 0.0 },
      },
    }
    const rows = auditRows(withImpact)
    const labels = rows.map((row) => `${row.section}:${row.label}`)
    expect(labels).toContain('Correlation:Quota impact')
    expect(labels).toContain('Correlation:Sample')
    expect(labels).toContain('Correlation:Unattributed')
  })
})

describe('reconciliationWarnings', () => {
  it('returns disagreement detail and staleness warnings', () => {
    const withConflict = {
      audit: {
        capacity: { reconciliation: { disagreements: [], stale_authoritative: true } },
        activity: {
          reconciliation: {
            disagreements: [{ source: 'hermes', detail: 'hermes reports 2000 vs authoritative 1000' }],
            stale_authoritative: false,
          },
        },
      },
    }
    const warnings = reconciliationWarnings(withConflict)
    expect(warnings).toContain('hermes reports 2000 vs authoritative 1000')
    expect(warnings.some((w) => w.includes('stale'))).toBe(true)
  })

  it('returns no warnings for clean data', () => {
    expect(reconciliationWarnings(provider)).toEqual([])
  })
})

describe('hasAuditData', () => {
  it('detects providers with audit content', () => {
    expect(hasAuditData(provider)).toBe(true)
    expect(hasAuditData({})).toBe(false)
    expect(hasAuditData(null)).toBe(false)
  })
})
