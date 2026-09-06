import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Alert, Box, Card, CardContent, Chip, CircularProgress, Collapse, FormControl, Grid,
  InputLabel, LinearProgress, MenuItem, Select, Stack, Tab, Tabs, Table, TableBody,
  TableCell, TableHead, TableRow, Tooltip, Typography,
} from '@mui/material'
import ExpandMoreRoundedIcon from '@mui/icons-material/ExpandMoreRounded'
import InsightsRoundedIcon from '@mui/icons-material/InsightsRounded'
import { api } from '../api.js'
import ProviderIcon from '../components/ProviderIcon.jsx'
import { DEFAULT_RANGE, RANGE_OPTIONS, compactNumber, formatMoney, providerNameWithLabel, rangeToParams } from '../lib/analyticsFormat.js'
import {
  WORKLOAD_METRICS, economicsRows, metricDisplay, pricingQuality, providerUsageRows,
  quotaStatus, quotaTooltipLabel, selectedUsageSummary, usageSummary, workloadChartData, workloadTooltipLabel,
} from '../lib/usageDashboardFormat.js'

const TIMEZONE = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
const STATUS_COLORS = { healthy: 'success', warning: 'warning', exhausted: 'error', stale: 'warning', unavailable: 'default' }
const CHART_COLORS = ['#7c6cff', '#21c8a3', '#f59e0b', '#ec4899', '#38bdf8', '#a3e635']

function dateTime(value) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function SummaryCard({ label, value, detail, source }) {
  return (
    <Card variant="outlined" className="glass-panel usage-summary-card">
      <CardContent>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
        <Typography variant="h4" sx={{ mt: 0.5 }}>{value}</Typography>
        {detail && <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>{detail}</Typography>}
        {source && <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>{source}</Typography>}
      </CardContent>
    </Card>
  )
}

export function Overview({ hermes, economics, overview, selectedProvider }) {
  const summary = selectedUsageSummary(usageSummary(hermes, economics, overview), selectedProvider, hermes, economics)
  const costDetail = summary.cost === null
    ? 'No authoritative cost is available'
    : [summary.commitment ? `${formatMoney(summary.commitment, summary.currency)} subscriptions` : null, summary.payg ? `${formatMoney(summary.payg, summary.currency)} PAYG` : null].filter(Boolean).join(' · ')
  return (
    <Grid container spacing={1.5} className="usage-summary-grid">
      <Grid size={{ xs: 6, lg: 3 }}><SummaryCard label="Cost" value={summary.cost === null ? '—' : formatMoney(summary.cost, summary.currency)} detail={costDetail} source={summary.hasUnknownPayg ? 'Some PAYG spend is unavailable' : 'Commitment + reported spend'} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><SummaryCard label="Tokens" value={metricDisplay(summary.tokens, 'tokens')} source="Hermes observed" /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><SummaryCard label="Requests" value={metricDisplay(summary.requests, 'requests')} source="Hermes observed" /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><SummaryCard label="Sessions" value={metricDisplay(summary.sessions, 'sessions')} source="Hermes observed" /></Grid>
      {summary.sharedWorkload && <Grid size={{ xs: 12 }}><Alert severity="info">Shared provider workload cannot be attributed to this config. Select All providers to view the provider-level totals.</Alert></Grid>}
    </Grid>
  )
}

function QuotaWindow({ window, quality }) {
  const status = quotaStatus(window, quality)
  const used = window.used_pct
  const tooltip = quotaTooltipLabel(window, quality)
  return (
    <Box className="usage-quota-window">
      <Stack direction="row" spacing={1} sx={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="body2" sx={{ textTransform: 'capitalize', fontWeight: 600 }}>{window.label}</Typography>
        <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
          <Typography variant="body2">{used === null || used === undefined ? 'Unavailable' : `${Math.round(used)}% used`}</Typography>
          <Chip size="small" color={STATUS_COLORS[status]} label={status} />
        </Stack>
      </Stack>
      {used !== null && used !== undefined && <Tooltip arrow enterDelay={100} title={tooltip}><LinearProgress tabIndex={0} aria-label={tooltip} variant="determinate" value={Math.min(100, Math.max(0, used))} color={STATUS_COLORS[status] === 'default' ? 'primary' : STATUS_COLORS[status]} sx={{ mt: 0.75, height: 7, borderRadius: 4 }} /></Tooltip>}
      {window.reset_at && <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>Resets {dateTime(window.reset_at)}</Typography>}
    </Box>
  )
}

function ProviderCard({ row, icon }) {
  const costValue = row.cost.value === null || row.cost.value === undefined ? '—' : formatMoney(row.cost.value, row.cost.currency)
  const status = row.quality === 'stale' || row.quality === 'unavailable' ? row.quality : null
  return (
    <Card variant="outlined" className="glass-panel usage-provider-card">
      <CardContent>
        <Stack direction="row" spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <Stack direction="row" spacing={1.25} sx={{ minWidth: 0 }}>
            <Box sx={{ fontSize: 34, lineHeight: 1 }}><ProviderIcon icon={icon} /></Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="h6">{row.displayName}</Typography>
              <Typography variant="body2" color="text.secondary">{row.billing}</Typography>
            </Box>
          </Stack>
          {status && <Chip size="small" color={STATUS_COLORS[status]} label={status} />}
        </Stack>
        <Grid container spacing={1.5} sx={{ mt: 1 }}>
          <Grid size={{ xs: 4 }}><Typography variant="caption" color="text.secondary">Tokens</Typography><Typography variant="body1">{metricDisplay(row.tokens, 'tokens')}</Typography></Grid>
          <Grid size={{ xs: 4 }}><Typography variant="caption" color="text.secondary">Requests</Typography><Typography variant="body1">{metricDisplay(row.requests, 'requests')}</Typography></Grid>
          <Grid size={{ xs: 4 }}><Typography variant="caption" color="text.secondary">Cost</Typography><Typography variant="body1">{costValue}</Typography></Grid>
        </Grid>
        {row.attributionAmbiguous && <Alert severity="info" sx={{ mt: 1.5 }}>Workload is shared across multiple {row.displayName.split(' - ')[0]} configs and is not guessed per config.</Alert>}
        {row.quotaWindows.length > 0 ? (
          <Grid container spacing={1.5} sx={{ mt: 0.5 }}>
            {row.quotaWindows.map((window) => <Grid key={window.metric} size={{ xs: 12, md: row.quotaWindows.length > 1 ? 6 : 12 }}><QuotaWindow window={window} quality={row.quality} /></Grid>)}
          </Grid>
        ) : row.pricingModel === 'payg' ? (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>{row.cost.value === null ? 'Provider spend is unavailable for this range.' : `${costValue} provider-reported spend in this range.`}</Typography>
        ) : (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>This provider does not expose a normalizable quota.</Typography>
        )}
      </CardContent>
    </Card>
  )
}

function ProviderSection({ rows, icons }) {
  return (
    <Box component="section">
      <Typography variant="h5" sx={{ mb: 0.5 }}>Provider usage & quota</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>Workload, billing, and every provider-native quota window in one place.</Typography>
      <Grid container spacing={2}>{rows.map((row) => <Grid key={row.config_id} size={{ xs: 12, lg: 6 }}><ProviderCard row={row} icon={icons.get(row.provider)} /></Grid>)}</Grid>
    </Box>
  )
}

export function WorkloadChart({ hermes, metric, grouping }) {
  const chart = workloadChartData(hermes, metric, grouping)
  const totals = chart.points.map((point) => point.total).filter((value) => typeof value === 'number')
  const max = Math.max(...totals, 0)
  if (!chart.series.length || !chart.points.length || !totals.length) return <Typography variant="body2" color="text.secondary">No {metric} history is available for this range.</Typography>
  const scaleMax = max || 1
  return (
    <Box>
      <Box className="usage-workload-chart" role="img" aria-label={`${metric} over time grouped by ${grouping}`}>
        {chart.points.map((point) => (
          <Box className={`usage-workload-column${point.total === null ? ' usage-workload-gap' : ''}`} key={point.date}>
            {point.total === null ? (
              <Tooltip arrow enterDelay={100} title={workloadTooltipLabel({ date: point.date, total: null, metric, grouping })}>
                <Box className="usage-workload-missing" tabIndex={0} aria-label={workloadTooltipLabel({ date: point.date, total: null, metric, grouping })} />
              </Tooltip>
            ) : point.total === 0 ? (
              <Tooltip arrow enterDelay={100} title={workloadTooltipLabel({ date: point.date, key: chart.series[0]?.key, value: 0, total: 0, metric, grouping })}>
                <Box className="usage-workload-zero" tabIndex={0} aria-label={workloadTooltipLabel({ date: point.date, key: chart.series[0]?.key, value: 0, total: 0, metric, grouping })} />
              </Tooltip>
            ) : (
              <Box className="usage-workload-stack" sx={{ height: `${point.total / scaleMax * 100}%` }}>
                {chart.series.map((item, seriesIndex) => {
                  const value = point.values[seriesIndex]
                  if (value === null || value === undefined || Number(value) <= 0) return null
                  const tooltip = workloadTooltipLabel({ date: point.date, key: item.key, value: Number(value), total: point.total, metric, grouping })
                  return <Tooltip key={item.key} arrow enterDelay={100} title={tooltip}><Box tabIndex={0} aria-label={tooltip} sx={{ height: `${Number(value) / point.total * 100}%`, background: CHART_COLORS[seriesIndex % CHART_COLORS.length] }} /></Tooltip>
                })}
              </Box>
            )}
            <Typography variant="caption" color="text.secondary">{point.date.slice(5)}</Typography>
          </Box>
        ))}
      </Box>
      <Stack direction="row" spacing={1.5} sx={{ flexWrap: 'wrap', mt: 1.5 }}>
        {chart.series.slice(0, 8).map((item, index) => <Stack key={item.key} direction="row" spacing={0.5} sx={{ alignItems: 'center' }}><Box sx={{ width: 9, height: 9, borderRadius: '50%', background: CHART_COLORS[index % CHART_COLORS.length] }} /><Typography variant="caption">{item.key}</Typography></Stack>)}
      </Stack>
    </Box>
  )
}

function UsageOverTime({ hermes }) {
  const [metric, setMetric] = useState('tokens')
  const [grouping, setGrouping] = useState('provider')
  return (
    <Card component="section" variant="outlined" className="glass-panel">
      <CardContent>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', mb: 2 }}>
          <Box><Typography variant="h5">Usage over time</Typography><Typography variant="body2" color="text.secondary">Daily Hermes-observed workload. Observed cost is telemetry reported by Hermes—not subscription commitment or provider-reported spend. Missing samples remain gaps.</Typography></Box>
          <FormControl size="small" sx={{ minWidth: 145 }}><InputLabel>Group</InputLabel><Select label="Group" value={grouping} onChange={(event) => setGrouping(event.target.value)}><MenuItem value="provider">By provider</MenuItem><MenuItem value="model">By model</MenuItem></Select></FormControl>
        </Stack>
        <Tabs value={metric} onChange={(_, value) => setMetric(value)} variant="scrollable" allowScrollButtonsMobile sx={{ mb: 2 }}>{WORKLOAD_METRICS.map((item) => <Tab key={item.value} value={item.value} label={item.label} />)}</Tabs>
        <WorkloadChart hermes={hermes} metric={metric} grouping={grouping} />
      </CardContent>
    </Card>
  )
}

function ValueTable({ economics, hermes }) {
  const rows = economicsRows(economics, hermes)
  const quality = pricingQuality(hermes)
  const totalTokens = rows.reduce((sum, row) => sum + Number(row.tokens || 0), 0)
  return (
    <Card component="section" variant="outlined" className="glass-panel">
      <CardContent>
        <Typography variant="h5">Cost & value</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>Efficiency uses subscription commitment or provider-reported PAYG spend—not an unexplained proration.</Typography>
        <Box className="usage-table-scroll"><Table size="small"><TableHead><TableRow><TableCell>Provider</TableCell><TableCell>Billing</TableCell><TableCell align="right">Cost</TableCell><TableCell align="right">Tokens</TableCell><TableCell align="right">Requests</TableCell><TableCell align="right">Tokens / $</TableCell><TableCell align="right">Requests / $</TableCell><TableCell align="right">Cost / 1M</TableCell><TableCell align="right">Share</TableCell></TableRow></TableHead><TableBody>
          {rows.map((row) => <TableRow key={row.config_id}><TableCell>{row.displayName}</TableCell><TableCell>{row.pricing_model === 'subscription' ? 'Subscription' : row.pricing_model === 'free' ? 'Free' : 'PAYG'}</TableCell><TableCell align="right">{row.cost.value === null ? '—' : formatMoney(row.cost.value, row.cost.currency)}</TableCell><TableCell align="right">{metricDisplay(row.tokens, 'tokens')}</TableCell><TableCell align="right">{metricDisplay(row.requests, 'requests')}</TableCell><TableCell align="right">{metricDisplay(row.tokensPerDollar, 'tokens')}</TableCell><TableCell align="right">{metricDisplay(row.requestsPerDollar, 'requests')}</TableCell><TableCell align="right">{row.costPerMillion === null ? '—' : formatMoney(row.costPerMillion, row.cost.currency)}</TableCell><TableCell align="right">{row.tokens !== null && totalTokens > 0 ? `${(row.tokens / totalTokens * 100).toFixed(1)}%` : '—'}</TableCell></TableRow>)}
        </TableBody></Table></Box>
        {quality.coverage !== null && quality.coverage >= 80 ? <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>API-equivalent estimate: {formatMoney(hermes.cost_estimate?.total_cost)} · {Math.round(quality.coverage)}% pricing coverage.</Typography> : <Alert severity="info" sx={{ mt: 1.5 }}>API-equivalent estimate unavailable — pricing coverage is insufficient.</Alert>}
      </CardContent>
    </Card>
  )
}

function Breakdown({ hermes }) {
  const [tab, setTab] = useState('provider')
  const rows = tab === 'provider' ? hermes?.by_provider || [] : tab === 'model' ? hermes?.by_model || [] : hermes?.by_profile || []
  const totalTokens = rows.reduce((sum, row) => sum + Number(row.tokens || 0), 0)
  return (
    <Card component="section" variant="outlined" className="glass-panel"><CardContent>
      <Typography variant="h5">Breakdown</Typography>
      <Tabs value={tab} onChange={(_, value) => setTab(value)} sx={{ mb: 1 }}><Tab value="provider" label="Providers" /><Tab value="model" label="Models" /><Tab value="profile" label="Profiles" /></Tabs>
      {!rows.length ? <Typography variant="body2" color="text.secondary">No {tab} attribution is available for this range.</Typography> : <Box className="usage-table-scroll"><Table size="small"><TableHead><TableRow><TableCell>{tab[0].toUpperCase() + tab.slice(1)}</TableCell><TableCell align="right">Cost</TableCell><TableCell align="right">Tokens</TableCell><TableCell align="right">Requests</TableCell><TableCell align="right">Sessions</TableCell><TableCell align="right">Share</TableCell></TableRow></TableHead><TableBody>{rows.map((row) => <TableRow key={row.key}><TableCell>{tab === 'provider' ? providerNameWithLabel(row.key) : row.key}</TableCell><TableCell align="right">{row.cost === null || row.cost === undefined ? '—' : formatMoney(row.cost)}</TableCell><TableCell align="right">{metricDisplay(row.tokens, 'tokens')}</TableCell><TableCell align="right">{metricDisplay(row.requests, 'requests')}</TableCell><TableCell align="right">{metricDisplay(row.sessions, 'sessions')}</TableCell><TableCell align="right">{row.tokens !== null && totalTokens > 0 ? `${(row.tokens / totalTokens * 100).toFixed(1)}%` : '—'}</TableCell></TableRow>)}</TableBody></Table></Box>}
    </CardContent></Card>
  )
}

function DataQuality({ hermes, overview }) {
  const [open, setOpen] = useState(false)
  const quality = pricingQuality(hermes)
  const healthy = (hermes?.sources || []).filter((source) => source.status === 'healthy').length
  const stale = overview?.coverage?.stale_or_unavailable_provider_count || 0
  const summary = [`${healthy}/${hermes?.sources?.length || 0} Hermes sources healthy`, stale ? `${stale} stale/unavailable providers` : 'provider snapshots current', quality.coverage === null ? 'pricing coverage unavailable' : `${Math.round(quality.coverage)}% priced`, `${quality.unpricedModels.length} unpriced models`].join(' · ')
  return (
    <Card component="section" variant="outlined" className="glass-panel"><CardContent>
      <Stack direction="row" spacing={1} sx={{ justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }} onClick={() => setOpen(!open)} role="button" aria-expanded={open}><Box><Typography variant="h6">Data sources & quality</Typography><Typography variant="body2" color="text.secondary">{summary}</Typography></Box><ExpandMoreRoundedIcon sx={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }} /></Stack>
      <Collapse in={open}><Stack spacing={1.25} sx={{ mt: 2 }}>
        {(hermes?.sources || []).map((source) => <Box key={source.id}><Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}><Typography variant="body2" sx={{ fontWeight: 600 }}>{source.name}</Typography><Chip size="small" color={STATUS_COLORS[source.status] || 'default'} label={source.status.replaceAll('_', ' ')} /></Stack><Typography variant="caption" color="text.secondary">Latest observation: {dateTime(source.latest_observation_at) || 'unavailable'} · {source.observations_in_range} observations in range</Typography>{source.providers_unmapped?.length > 0 && <Typography variant="caption" color="warning.main" sx={{ display: 'block' }}>Unresolved providers: {source.providers_unmapped.join(', ')}</Typography>}</Box>)}
        {quality.version && <Typography variant="body2">Pricing catalogue: {quality.version} · unpriced tokens: {compactNumber(quality.unpricedTokens) || 0}</Typography>}
        {(hermes?.diagnostics || []).map((item, index) => <Alert key={index} severity={item.severity}>{item.message}</Alert>)}
      </Stack></Collapse>
    </CardContent></Card>
  )
}

export default function UsageDashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = searchParams.get('provider') || 'all'
  const [range, setRange] = useState(DEFAULT_RANGE)
  const [data, setData] = useState({ configs: [], providerCatalog: [], overview: null, economics: null, hermes: null })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    const { from, to } = rangeToParams(range)
    setLoading(true)
    setError('')
    Promise.all([api.usage(), api.providers()]).then(async ([configs, providerCatalog]) => {
      const selected = selectedId === 'all' ? null : configs.find((item) => String(item.config.id) === selectedId)?.config
      const scope = selected ? { provider: selected.provider } : {}
      const [overview, economics, hermes] = await Promise.all([
        api.analyticsOverview({ from, to, interval: 'day', timezone: TIMEZONE }),
        api.analyticsEconomics({ from, to, ...(selected ? { config_id: selected.id } : {}) }),
        api.hermesBreakdown({ from, to, timezone: TIMEZONE, ...scope }),
      ])
      if (!cancelled) setData({ configs, providerCatalog, overview, economics, hermes })
    }).catch((err) => { if (!cancelled) setError(err.message) }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [range, selectedId])

  const providerRows = useMemo(() => providerUsageRows(data.overview, data.economics, data.hermes), [data])
  const visibleRows = selectedId === 'all' ? providerRows : providerRows.filter((row) => String(row.config_id) === selectedId)
  const selectedProvider = visibleRows.length === 1 && selectedId !== 'all' ? visibleRows[0] : null
  const providerIcons = useMemo(() => new Map(data.providerCatalog.map((provider) => [provider.id, provider.icon])), [data.providerCatalog])

  return <>
    <header className="page-heading usage-page-heading"><Box><div className="page-kicker">Usage</div><Typography component="h1" variant="h2">Usage</Typography><Typography component="p">Understand your AI workload, provider quotas, costs, and usage trends.</Typography></Box>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25} className="usage-header-controls">
        <FormControl size="small" sx={{ minWidth: 190 }}><InputLabel>Provider</InputLabel><Select label="Provider" value={selectedId} onChange={(event) => setSearchParams(event.target.value === 'all' ? {} : { provider: event.target.value })}><MenuItem value="all">All providers</MenuItem>{providerRows.map((row) => <MenuItem key={row.config_id} value={String(row.config_id)}>{row.displayName}</MenuItem>)}</Select></FormControl>
        <FormControl size="small" sx={{ minWidth: 135 }}><InputLabel>Range</InputLabel><Select label="Range" value={range} onChange={(event) => setRange(event.target.value)}>{RANGE_OPTIONS.map((option) => <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>)}</Select></FormControl>
      </Stack>
    </header>
    {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}
    {loading && <Box className="loading-state"><CircularProgress /></Box>}
    {!loading && !error && data.configs.length === 0 && <Box className="empty-state"><div className="empty-state-icon"><InsightsRoundedIcon /></div><Typography variant="h6">No providers connected</Typography><Typography color="text.secondary">Connect a provider in Settings to begin collecting usage.</Typography></Box>}
    {!loading && !error && data.configs.length > 0 && <Stack spacing={3}>
      <Overview hermes={data.hermes} economics={data.economics} overview={data.overview} selectedProvider={selectedProvider} />
      <ProviderSection rows={visibleRows} icons={providerIcons} />
      <UsageOverTime hermes={data.hermes} />
      <ValueTable economics={data.economics} hermes={data.hermes} />
      <Breakdown hermes={data.hermes} />
      <DataQuality hermes={data.hermes} overview={data.overview} />
    </Stack>}
  </>
}
