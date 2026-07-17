import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Collapse,
  Grid,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material'
import ApiRoundedIcon from '@mui/icons-material/ApiRounded'
import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded'
import CloudSyncRoundedIcon from '@mui/icons-material/CloudSyncRounded'
import DataUsageRoundedIcon from '@mui/icons-material/DataUsageRounded'
import RefreshRoundedIcon from '@mui/icons-material/RefreshRounded'
import WarningAmberRoundedIcon from '@mui/icons-material/WarningAmberRounded'
import { api } from '../api.js'

const PREFERRED_METRICS = {
  anthropic: ['input_tokens', 'output_tokens', 'num_requests'],
  deepseek: ['total_balance', 'granted_balance', 'topped_up_balance'],
  firecrawl: ['credits_remaining', 'credits_used', 'usage_percent', 'plan_credits'],
  openai: ['cost_30d'],
  openrouter: ['limit_remaining', 'usage_monthly', 'usage_weekly'],
}

function metricPercent(metric) {
  return typeof metric.maximum === 'number' && metric.maximum > 0 && typeof metric.value === 'number'
    ? Math.min(100, Math.max(0, (metric.value / metric.maximum) * 100))
    : null
}
function formatPercent(value) { return `${Math.round(value)}%` }
function formatMetricLabel(label) { return label.replaceAll('_', ' ') }
function formatDateTime(value) {
  if (!value) return 'Not scheduled'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}
function numericMetric(metrics, label) {
  const metric = metrics.find((item) => item.label === label)
  return typeof metric?.value === 'number' ? metric : null
}
function selectHistoryMetric(provider, snapshots) {
  const preferred = PREFERRED_METRICS[provider] || []
  const labels = [...preferred, ...new Set(snapshots.flatMap((snapshot) => (snapshot.metrics || []).map((metric) => metric.label)))]
  return labels
    .map((label) => ({ label, values: snapshots.map((snapshot) => numericMetric(snapshot.metrics || [], label)?.value).filter((value) => typeof value === 'number') }))
    .find((candidate) => candidate.values.length > 1) || null
}

function Sparkline({ points }) {
  const canvasRef = useRef(null)
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const width = canvas.clientWidth || 320
    const height = 120
    const ratio = window.devicePixelRatio || 1
    canvas.width = width * ratio
    canvas.height = height * ratio
    const ctx = canvas.getContext('2d')
    ctx.scale(ratio, ratio)
    ctx.clearRect(0, 0, width, height)
    ctx.strokeStyle = 'rgba(168, 85, 247, 0.16)'
    ctx.lineWidth = 1
    for (let index = 0; index < 4; index += 1) {
      const y = 16 + index * 28
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(width, y)
      ctx.stroke()
    }
    if (points.length < 2) return
    const values = points.map((point) => point.value)
    const min = Math.min(...values)
    const max = Math.max(...values)
    const span = max - min || 1
    const gradient = ctx.createLinearGradient(0, 0, width, 0)
    gradient.addColorStop(0, '#a855f7')
    gradient.addColorStop(1, '#06c8ff')
    ctx.strokeStyle = gradient
    ctx.shadowColor = 'rgba(6, 200, 255, .45)'
    ctx.shadowBlur = 8
    ctx.lineWidth = 2.5
    ctx.beginPath()
    points.forEach((point, index) => {
      const x = (index / (points.length - 1)) * width
      const y = height - 18 - ((point.value - min) / span) * (height - 36)
      if (index === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.stroke()
  }, [points])
  const first = points[0]?.value
  const last = points[points.length - 1]?.value
  return <canvas ref={canvasRef} style={{ width: '100%', height: 120, display: 'block' }} role="img" aria-label={`Usage history trend with ${points.length} points${points.length ? `, from ${first} to ${last}` : ''}.`} />
}

function UsageHistory({ config, latest }) {
  const [expanded, setExpanded] = useState(false)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!expanded) return
    let cancelled = false
    async function loadHistory() {
      setLoading(true)
      setError('')
      try {
        const rows = await api.history(config.id, { hours: 168, limit: 500 })
        if (!cancelled) setHistory(rows)
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    loadHistory()
    return () => { cancelled = true }
  }, [config.id, expanded, latest?.id])

  const selected = useMemo(() => selectHistoryMetric(config.provider, history), [config.provider, history])
  const points = useMemo(() => selected ? history
    .map((snapshot) => ({ checked_at: snapshot.checked_at, value: numericMetric(snapshot.metrics || [], selected.label)?.value }))
    .filter((point) => typeof point.value === 'number') : [], [history, selected])
  const first = points[0]
  const last = points[points.length - 1]

  return (
    <Box sx={{ mt: 2 }}>
      <Button size="small" variant="outlined" onClick={() => setExpanded((value) => !value)}>{expanded ? 'Hide history' : 'View 7-day history'}</Button>
      <Collapse in={expanded}>
        <Box className="history-panel">
          {loading && <CircularProgress size={20} />}
          {error && <Alert severity="error">{error}</Alert>}
          {!loading && !error && !selected && <Typography variant="body2" color="text.secondary">Two numeric snapshots are required before the graph develops opinions.</Typography>}
          {selected && <Stack spacing={1}>
            <Stack direction="row" justifyContent="space-between"><Typography variant="body2" sx={{ textTransform: 'capitalize' }}>{formatMetricLabel(selected.label)}</Typography><Typography variant="caption" color="text.secondary">{points.length} snapshots</Typography></Stack>
            <Sparkline points={points} />
            {first && last && <Typography variant="caption" color="text.secondary">{String(first.value)} → {String(last.value)}</Typography>}
          </Stack>}
        </Box>
      </Collapse>
    </Box>
  )
}

function UsageCard({ item }) {
  const { config, latest } = item
  const color = latest?.status === 'healthy' ? 'success' : latest?.status === 'error' ? 'error' : 'warning'
  const providerInitials = config.provider.split('_').map((word) => word[0]).join('').slice(0, 2)

  return (
    <Card className="provider-card glass-panel" variant="outlined">
      <CardContent>
        <Stack className="provider-header" direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
          <Stack direction="row" spacing={1.5} alignItems="center" minWidth={0}>
            <div className="provider-logo" aria-hidden="true">{providerInitials}</div>
            <Box minWidth={0}><div className="provider-name">{config.provider}</div><Typography variant="h6" noWrap>{config.label}</Typography></Box>
          </Stack>
          <Chip className={`provider-status status-${color}`} color={color} label={latest?.status || 'not polled'} size="small" />
        </Stack>
        <Typography className="provider-summary" variant="body2">{latest?.summary || 'No usage snapshot yet. Poll the provider to invite some data in.'}</Typography>
        <Stack>{(latest?.metrics || []).map((metric) => {
          const percent = metricPercent(metric)
          return <Box className="metric-row" key={metric.label}>
            <Stack className="metric-header" direction="row" justifyContent="space-between" gap={2}><Typography className="metric-label" variant="body2">{formatMetricLabel(metric.label)}</Typography><Typography className="metric-value" variant="body2">{String(metric.value ?? '—')} {metric.unit || ''}{percent !== null ? ` (${formatPercent(percent)})` : ''}</Typography></Stack>
            {percent !== null && <LinearProgress variant="determinate" value={percent} sx={{ mt: 1 }} />}
          </Box>
        })}</Stack>
        {latest?.error && <Alert severity="error" sx={{ mt: 2 }}>{latest.error}</Alert>}
        <UsageHistory config={config} latest={latest} />
      </CardContent>
    </Card>
  )
}

export default function DashboardPage() {
  const [items, setItems] = useState([])
  const [homepage, setHomepage] = useState(null)
  const [pollStatus, setPollStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function load(poll = false) {
    setLoading(true)
    setError('')
    try {
      if (poll) await api.pollAll()
      const [usage, hp, status] = await Promise.all([api.usage(), api.homepage(), api.pollStatus()])
      setItems(usage)
      setHomepage(hp)
      setPollStatus(status)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  const summaries = homepage ? [
    { label: 'Configured', value: homepage.configured_providers, icon: <ApiRoundedIcon /> },
    { label: 'Healthy', value: homepage.healthy_providers, className: 'highlight', icon: <CheckCircleRoundedIcon /> },
    { label: 'Degraded', value: homepage.degraded_providers, className: homepage.degraded_providers ? 'warning' : '', icon: <WarningAmberRoundedIcon /> },
    { label: 'Network summary', value: homepage.summary, icon: <DataUsageRoundedIcon /> },
  ] : []

  return <>
    <header className="page-heading">
      <Box><div className="page-kicker">Provider telemetry</div><Typography component="h1" variant="h2">Command center</Typography><Typography component="p">Balances, usage, and provider health—one sharp view, no spreadsheet séance required.</Typography></Box>
      <Button variant="contained" startIcon={loading ? <CircularProgress size={17} color="inherit" /> : <RefreshRoundedIcon />} onClick={() => load(true)} disabled={loading}>{loading ? 'Polling…' : 'Poll providers'}</Button>
    </header>
    {pollStatus && <Box className="poll-status glass-panel"><Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={1.5}><Box><Typography variant="overline" color="primary.main">Automatic polling</Typography><Typography variant="body2" color="text.secondary">{pollStatus.auto_poll_enabled ? `Next auto poll: ${formatDateTime(pollStatus.next_poll_at)}` : 'Auto polling disabled'}</Typography></Box><Typography variant="body2" color="text.secondary">{pollStatus.is_polling ? 'Polling now…' : pollStatus.last_polled_at ? `Last auto poll: ${formatDateTime(pollStatus.last_polled_at)}` : 'No automatic poll has run yet'}</Typography></Stack></Box>}
    {homepage && <Grid className="summary-grid" container spacing={2}>{summaries.map((summary) => <Grid size={{ xs: summary.label === 'Network summary' ? 12 : 6, sm: 6, md: 3 }} key={summary.label}><Box className={`summary-card glass-panel ${summary.className || ''}`}><div className="summary-label">{summary.label}</div><div className="summary-value">{summary.value}</div><div className="summary-icon" aria-hidden="true">{summary.icon}</div></Box></Grid>)}</Grid>}
    {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}
    {loading && !homepage && <Box className="loading-state"><Stack alignItems="center" spacing={2}><CircularProgress /><Typography color="text.secondary">Contacting the provider fleet…</Typography></Stack></Box>}
    {!loading && items.length === 0 && <Box className="empty-state"><div className="empty-state-icon"><CloudSyncRoundedIcon /></div><Typography variant="h6">No providers connected</Typography><Typography color="text.secondary" sx={{ mt: 1 }}>Head to Settings and connect your first API provider.</Typography></Box>}
    <Grid container spacing={2.5}>{items.map((item) => <Grid size={{ xs: 12, md: 6, xl: 4 }} key={item.config.id}><UsageCard item={item} /></Grid>)}</Grid>
  </>
}
