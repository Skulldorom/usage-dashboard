// Pure formatting helpers for the "Why this number?" audit view, extracted so
// they are unit-testable without rendering React components.

const SOURCE_LABELS = {
  native: 'Provider-native',
  snapshot: 'Snapshot-derived',
  hermes: 'Hermes-observed',
  estimated: 'Estimated',
}

export function sourceLabel(source) {
  if (!source) return '-'
  return SOURCE_LABELS[source] || source
}

export function confidenceLabel(level) {
  if (!level) return '-'
  return `${level.charAt(0).toUpperCase()}${level.slice(1)}`
}

export function auditRows(provider) {
  // Build the human-readable rows shown in the "Why this number?" panel.
  const audit = provider?.audit || {}
  const capacity = audit.capacity || {}
  const activity = audit.activity || {}
  const rows = []

  // Capacity section.
  if (capacity.value !== null && capacity.value !== undefined) {
    rows.push({
      section: 'Capacity',
      label: 'Value',
      value: `${capacity.value}${capacity.unit === '%' ? '%' : ` ${capacity.unit || ''}`}`.trim(),
    })
    rows.push({
      section: 'Capacity',
      label: 'Authoritative source',
      value: sourceLabel(capacity.authoritative_source),
    })
    if (capacity.window_end) {
      rows.push({
        section: 'Capacity',
        label: 'Window',
        value: new Date(capacity.window_end).toLocaleString(),
      })
    }
    if (capacity.reset_at) {
      rows.push({
        section: 'Capacity',
        label: 'Resets',
        value: new Date(capacity.reset_at).toLocaleString(),
      })
    }
  }

  // Activity section.
  if (activity.value !== null && activity.value !== undefined) {
    rows.push({
      section: 'Activity',
      label: 'Value',
      value: `${activity.value}${activity.unit ? ` ${activity.unit}` : ''}`.trim(),
    })
    rows.push({
      section: 'Activity',
      label: 'Authoritative source',
      value: sourceLabel(activity.authoritative_source),
    })
    if (activity.estimated_cost !== null && activity.estimated_cost !== undefined) {
      rows.push({
        section: 'Activity',
        label: 'Estimated cost',
        value: `$${Number(activity.estimated_cost).toFixed(2)} (${activity.estimated_cost_source || 'pricing catalogue'})`,
      })
    }
  }

  // Corroborating sources (applies to the whole provider).
  const corroborating = audit.corroborating_sources || []
  if (corroborating.length) {
    rows.push({
      section: 'Sources',
      label: 'Corroborated by',
      value: corroborating.map(sourceLabel).join(', '),
    })
  }

  // Quota-impact correlation estimate.
  const impact = audit.quota_impact
  if (impact && typeof impact.estimated_impact_per_token === 'number') {
    rows.push({
      section: 'Correlation',
      label: 'Quota impact',
      value: `~${impact.estimated_impact_per_token.toFixed(6)} quota pts/token`,
    })
    rows.push({
      section: 'Correlation',
      label: 'Sample',
      value: `${impact.sample_size} reset windows (${impact.confidence} confidence)`,
    })
    if (impact.unattributed_pct !== null && impact.unattributed_pct !== undefined) {
      rows.push({
        section: 'Correlation',
        label: 'Unattributed',
        value: `${impact.unattributed_pct}% of quota movement unexplained by Hermes activity`,
      })
    }
  }

  return rows
}

export function reconciliationWarnings(provider) {
  // Return a list of warning strings for any disagreement/staleness flags.
  const audit = provider?.audit || {}
  const warnings = []
  for (const section of ['capacity', 'activity']) {
    const recon = audit[section]?.reconciliation || {}
    for (const disagreement of recon.disagreements || []) {
      warnings.push(disagreement.detail || `${disagreement.source} disagrees with authoritative value`)
    }
    if (recon.stale_authoritative) {
      warnings.push(`${section === 'capacity' ? 'Capacity' : 'Activity'} authoritative data may be stale; corroborating telemetry is fresher`)
    }
  }
  return warnings
}

export function hasAuditData(provider) {
  return auditRows(provider).length > 0
}
