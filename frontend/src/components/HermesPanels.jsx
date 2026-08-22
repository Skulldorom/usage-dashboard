import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Card,
  CardContent,
  CircularProgress,
  Grid,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import HubRoundedIcon from '@mui/icons-material/HubRounded'
import { api } from '../api.js'
import { rangeToParams } from '../lib/analyticsFormat.js'

const TIMEZONE = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'

function fmt(value, unit) {
  if (value === null || value === undefined) return '—'
  const n = Number(value)
  const text = Math.abs(n) >= 1000 ? n.toLocaleString(undefined, { maximumFractionDigits: 0 }) : String(Math.round(n * 100) / 100)
  return unit ? `${text} ${unit}` : text
}

function GroupTable({ title, rows }) {
  if (!rows?.length) return null
  return (
    <Card variant="outlined" className="glass-panel">
      <CardContent>
        <Typography variant="overline" color="primary.main">{title}</Typography>
        <Table size="small" sx={{ mt: 1 }}>
          <TableHead>
            <TableRow>
              <TableCell>{title.replace('By ', '')}</TableCell>
              <TableCell align="right">Cost</TableCell>
              <TableCell align="right">Tokens</TableCell>
              <TableCell align="right">Requests</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.key}>
                <TableCell>{row.key.replaceAll('_', ' ')}</TableCell>
                <TableCell align="right">{row.cost !== null && row.cost !== undefined ? `$${Number(row.cost).toFixed(2)}` : '—'}</TableCell>
                <TableCell align="right">{fmt(row.tokens)}</TableCell>
                <TableCell align="right">{fmt(row.requests)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

export function HermesBreakdownPanel({ range }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    const { from, to } = rangeToParams(range)
    async function load() {
      setError('')
      try {
        const result = await api.hermesBreakdown({ timezone: TIMEZONE, from, to })
        if (!cancelled) setData(result)
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }
    load()
    return () => { cancelled = true }
  }, [range])

  if (error) {
    return (
      <Card variant="outlined" className="glass-panel">
        <CardContent>
          <Typography variant="overline" color="primary.main">Hermes telemetry</Typography>
          <Alert severity="info" sx={{ mt: 1 }}>{error}</Alert>
        </CardContent>
      </Card>
    )
  }

  if (!data) {
    return (
      <Card variant="outlined" className="glass-panel">
        <CardContent>
          <Stack direction="row" spacing={1} alignItems="center">
            <CircularProgress size={16} />
            <Typography variant="overline" color="primary.main">Hermes telemetry</Typography>
          </Stack>
        </CardContent>
      </Card>
    )
  }

  const totals = data.totals || []
  const hasData = totals.some((t) => t.value !== null && t.value !== undefined)
  if (!hasData) {
    return (
      <Card variant="outlined" className="glass-panel">
        <CardContent>
          <Typography variant="overline" color="primary.main">Hermes telemetry</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            No Hermes usage observed in this range. Connect Hermes Agent in
            Settings → Data sources.
          </Typography>
        </CardContent>
      </Card>
    )
  }

  const totalCards = [
    ...totals.filter((t) => t.value !== null && t.value !== undefined),
    { metric: 'sessions', unit: 'sessions', value: data.sessions },
  ]

  return (
    <Stack spacing={2.5}>
      <Card variant="outlined" className="glass-panel">
        <CardContent>
          <Stack direction="row" spacing={1} alignItems="center" mb={1}>
            <HubRoundedIcon color="primary" fontSize="small" />
            <Typography variant="overline" color="primary.main">Hermes telemetry</Typography>
          </Stack>
          <Typography variant="caption" color="text.secondary" display="block">
            Observed usage flowing through Hermes Agent. Supplemental to provider-reported totals.
          </Typography>
          <Grid container spacing={1.5} sx={{ mt: 0.5 }}>
            {totalCards.map((t) => (
              <Grid size={{ xs: 6, sm: 3 }} key={t.metric}>
                <Box className="summary-card glass-panel">
                  <div className="summary-label">{t.metric.replaceAll('_', ' ')}</div>
                  <div className="summary-value">{t.metric === 'cost' && t.value ? `$${Number(t.value).toFixed(2)}` : fmt(t.value)}</div>
                </Box>
              </Grid>
            ))}
          </Grid>
        </CardContent>
      </Card>
      <GroupTable title="By provider" rows={data.by_provider} />
      <GroupTable title="By model" rows={data.by_model} />
      <GroupTable title="By profile" rows={data.by_profile} />
    </Stack>
  )
}

function attributionLine(m) {
  switch (m.status) {
    case 'matched':
      return `${fmt(m.attributed, m.unit)} via Hermes · fully matched`
    case 'partial':
      return `${m.attribution_pct}% via Hermes · ${fmt(m.unattributed, m.unit)} unattributed`
    case 'over_observed':
      return `Hermes observed ${fmt(m.hermes_observed, m.unit)} vs provider ${fmt(m.provider_total, m.unit)}`
    case 'hermes_only':
      return `Hermes-observed ${fmt(m.hermes_observed, m.unit)} (provider total unavailable)`
    case 'provider_only':
      return `Provider-reported ${fmt(m.provider_total, m.unit)} (no Hermes data)`
    default:
      return 'No data'
  }
}

export function AttributionPanel({ configId }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const result = await api.analyticsAttribution(configId, { timezone: TIMEZONE })
        if (!cancelled) setData(result)
      } catch {
        if (!cancelled) setData({ metrics: [] })
      }
    }
    load()
    return () => { cancelled = true }
  }, [configId])

  if (!data || data.metrics.length === 0) return null

  const hasOverage = data.metrics.some((m) => m.status === 'over_observed')

  return (
    <Card variant="outlined" className="glass-panel">
      <CardContent>
        <Stack direction="row" spacing={1} alignItems="center" mb={1}>
          <HubRoundedIcon color="primary" fontSize="small" />
          <Typography variant="overline" color="primary.main">Hermes attribution</Typography>
        </Stack>
        <Stack spacing={1}>
          {data.metrics.map((m) => (
            <Box key={m.metric}>
              <Stack direction="row" justifyContent="space-between" gap={2}>
                <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>{m.metric.replaceAll('_', ' ')}</Typography>
                <Typography variant="body2" color="text.secondary">{attributionLine(m)}</Typography>
              </Stack>
            </Box>
          ))}
        </Stack>
        {hasOverage && (
          <Alert severity="warning" sx={{ mt: 1.5 }}>
            Hermes observed more usage than the provider reported for this period.
            This can occur because of reporting delays, different measurement
            windows, or estimated telemetry.
          </Alert>
        )}
        <Typography variant="caption" color="text.secondary" display="block" mt={1}>
          Hermes usage is an observed subset and is never added to provider totals.
        </Typography>
      </CardContent>
    </Card>
  )
}
