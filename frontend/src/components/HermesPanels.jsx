import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material'
import HubRoundedIcon from '@mui/icons-material/HubRounded'
import { api } from '../api.js'
import { rangeToParams } from '../lib/analyticsFormat.js'
import { fmt, hasHermesData, hermesHeadlineCards, money, estimatedCostCards, estimatedCostNote } from '../lib/hermesFormat.js'

const TIMEZONE = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
const SOURCE_STATUS_COLOR = { healthy: 'success', error: 'error', never_connected: 'default' }

function GroupTable({ title, rows }) {
  if (!rows?.length) return null
  const showEstimated = rows.some((row) => row.estimated_cost !== null && row.estimated_cost !== undefined)
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
              {showEstimated && <TableCell align="right">Est. cost</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.key}>
                <TableCell>{row.key.replaceAll('_', ' ')}</TableCell>
                <TableCell align="right">{money(row.cost)}</TableCell>
                <TableCell align="right">{fmt(row.tokens)}</TableCell>
                <TableCell align="right">{fmt(row.requests)}</TableCell>
                {showEstimated && <TableCell align="right">{money(row.estimated_cost)}</TableCell>}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

function HermesDailyChart({ daily }) {
  const rows = daily || []
  const values = rows.map((row) => Number(row.tokens || row.requests || row.cost || 0))
  const max = Math.max(...values, 0)
  if (!rows.length || max <= 0) {
    return <Typography variant="body2" color="text.secondary">No daily Hermes points in this range.</Typography>
  }
  return (
    <Box className="hermes-daily-chart" role="img" aria-label="Hermes observed usage over time">
      {rows.map((row, index) => {
        const value = values[index]
        const height = Math.max(6, Math.round((value / max) * 100))
        const tooltip = `${row.date}: ${fmt(row.tokens, 'tokens')} · ${fmt(row.requests, 'requests')} · ${money(row.cost)}`
        return (
          <Tooltip key={row.date} title={tooltip} arrow placement="top" enterDelay={0}>
            <Box className="hermes-daily-bar-wrap">
              <Box className="hermes-daily-bar" sx={{ height: `${height}%` }} />
              <Typography variant="caption" color="text.secondary">{row.date.slice(5)}</Typography>
            </Box>
          </Tooltip>
        )
      })}
    </Box>
  )
}

export function HermesSourceCard({ source, compact = false }) {
  const latest = source.latest_observation_at ? new Date(source.latest_observation_at).toLocaleString() : 'No stored observations'
  return (
    <Card variant="outlined" className="glass-panel data-source-card">
      <CardActionArea component="a" href="/usage" aria-label={`Open Hermes telemetry for ${source.name}`}>
        <CardContent>
          <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 1 }}>
            <Box>
              <Typography variant="overline" color="primary.main">Data source</Typography>
              <Typography variant={compact ? 'subtitle1' : 'h6'}>{source.name}</Typography>
            </Box>
            <Chip size="small" color={SOURCE_STATUS_COLOR[source.status] || 'default'} label={(source.status || 'unknown').replaceAll('_', ' ')} />
          </Stack>
          <Stack spacing={0.75} sx={{ mt: 1.5 }}>
            <Typography variant="body2">{source.observations_in_range || 0} observations in selected range</Typography>
            <Typography variant="body2" color="text.secondary">{source.total_observations || 0} stored total · latest {latest}</Typography>
            {source.providers_observed?.length > 0 && (
              <Typography variant="caption" color="text.secondary">Providers: {source.providers_observed.slice(0, 4).join(', ')}{source.providers_observed.length > 4 ? '…' : ''}</Typography>
            )}
            {source.providers_unmapped?.length > 0 && (
              <Alert
                severity="warning"
                sx={{ mt: 0.5 }}
                action={
                  <Button component="a" href="/settings#data-sources" size="small" color="inherit">
                    Manage mappings
                  </Button>
                }
              >
                Unmapped: {source.providers_unmapped.join(', ')}
              </Alert>
            )}
            {source.latest_error && <Alert severity="error" sx={{ mt: 0.5 }}>{source.latest_error}</Alert>}
          </Stack>
        </CardContent>
      </CardActionArea>
    </Card>
  )
}

export function HermesDataSourcesCards({ data, compact = false }) {
  const sources = data?.sources || []
  if (!sources.length) return null
  return (
    <Box>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1 }}>
        <HubRoundedIcon color="primary" fontSize="small" />
        <Typography variant="overline" color="primary.main">Data Sources</Typography>
      </Stack>
      <Grid container spacing={2}>
        {sources.map((source) => (
          <Grid size={{ xs: 12, md: compact ? 6 : 4 }} key={source.id}>
            <HermesSourceCard source={source} compact={compact} />
          </Grid>
        ))}
      </Grid>
    </Box>
  )
}

function HermesDiagnostics({ diagnostics }) {
  if (!diagnostics?.length) return null
  return (
    <Stack spacing={1}>
      {diagnostics.map((item, index) => (
        <Alert key={`${item.message}-${index}`} severity={item.severity || 'info'}>{item.message}</Alert>
      ))}
    </Stack>
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
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <CircularProgress size={16} />
            <Typography variant="overline" color="primary.main">Hermes telemetry</Typography>
          </Stack>
        </CardContent>
      </Card>
    )
  }

  const hasData = hasHermesData(data)
  const totalCards = hermesHeadlineCards(data)

  return (
    <Stack spacing={2.5}>
      <Card variant="outlined" className="glass-panel">
        <CardContent>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', mb: 1 }}>
            <Box>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                <HubRoundedIcon color="primary" fontSize="small" />
                <Typography variant="overline" color="primary.main">Hermes telemetry</Typography>
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                Observed usage flowing through Hermes Agent. Supplemental to provider-reported totals; never double-counted.
              </Typography>
            </Box>
            <Button href="/settings#data-sources" size="small" variant="outlined">Manage sources</Button>
          </Stack>
          <Grid container spacing={1.5} sx={{ mt: 0.5 }}>
            {totalCards.map((card) => (
              <Grid size={{ xs: 6, sm: 4, lg: 2 }} key={card.key}>
                <Box className="summary-card glass-panel">
                  <div className="summary-label">{card.label}</div>
                  <div className="summary-value">{card.value}</div>
                </Box>
              </Grid>
            ))}
          </Grid>
          {!hasData && (
            <Box sx={{ mt: 2 }}>
              <HermesDiagnostics diagnostics={data.diagnostics} />
            </Box>
          )}
          {estimatedCostCards(data.cost_estimate).length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1 }}>
                <Typography variant="overline" color="primary.main">Estimated cost</Typography>
                <Typography variant="caption" color="text.secondary">{estimatedCostNote(data.cost_estimate)}</Typography>
              </Stack>
              <Grid container spacing={1.5}>
                {estimatedCostCards(data.cost_estimate).map((card) => (
                  <Grid size={{ xs: 6, sm: 4, lg: 3 }} key={card.key}>
                    <Box className="summary-card glass-panel">
                      <div className="summary-label">{card.label}</div>
                      <div className="summary-value">{card.value}</div>
                    </Box>
                  </Grid>
                ))}
              </Grid>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                Estimated from Hermes-observed model + token usage against a maintained pricing catalogue. Separate from provider-reported cost and never added to it.
              </Typography>
            </Box>
          )}
        </CardContent>
      </Card>
      {hasData && <HermesDiagnostics diagnostics={data.diagnostics} />}
      <HermesDataSourcesCards data={data} />
      <Card variant="outlined" className="glass-panel">
        <CardContent>
          <Typography variant="overline" color="primary.main">Observed usage over time</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>Daily Hermes-observed tokens, requests, and cost for the selected Usage range.</Typography>
          <HermesDailyChart daily={data.daily} />
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
      return `${fmt(m.provider_total, m.unit)} provider-reported · ${fmt(m.hermes_observed, m.unit)} observed · fully attributed`
    case 'partial':
      return `${fmt(m.provider_total, m.unit)} provider-reported · ${fmt(m.hermes_observed, m.unit)} observed · ${m.attribution_pct}% attributed · ${fmt(m.unattributed, m.unit)} unattributed`
    case 'over_observed':
      return `${fmt(m.provider_total, m.unit)} provider-reported · ${fmt(m.hermes_observed, m.unit)} observed through Hermes`
    case 'hermes_only':
      return `Hermes-only ${fmt(m.hermes_observed, m.unit)} observed (provider total unavailable)`
    case 'provider_only':
      return `Provider-only ${fmt(m.provider_total, m.unit)} authoritative (no Hermes observation)`
    default:
      return 'No provider or Hermes data'
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
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1 }}>
          <HubRoundedIcon color="primary" fontSize="small" />
          <Typography variant="overline" color="primary.main">Hermes attribution</Typography>
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
          Provider-reported values are authoritative. Hermes values are observed/supplemental and show how much provider usage passed through Hermes.
        </Typography>
        <Stack spacing={1.2}>
          {data.metrics.map((m) => (
            <Box key={m.metric} className="attribution-row">
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ justifyContent: 'space-between' }}>
                <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>{m.metric.replaceAll('_', ' ')}</Typography>
                <Typography variant="body2" color="text.secondary">{attributionLine(m)}</Typography>
              </Stack>
            </Box>
          ))}
        </Stack>
        {hasOverage && (
          <Alert severity="warning" sx={{ mt: 1.5 }}>
            Hermes observed more usage than the provider reported for this period. This can happen with reporting delays, different windows, or estimated telemetry.
          </Alert>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          Hermes observations are never added to provider totals.
        </Typography>
      </CardContent>
    </Card>
  )
}
