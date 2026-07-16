import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Box, Button, Card, CardContent, Chip, CircularProgress, Collapse, Grid, LinearProgress, Stack, Typography } from '@mui/material'
import RefreshIcon from '@mui/icons-material/Refresh'
import { api } from '../api.js'

const PREFERRED_METRICS = {
  anthropic: ['input_tokens', 'output_tokens', 'num_requests'],
  deepseek: ['total_balance', 'granted_balance', 'topped_up_balance'],
  firecrawl: ['remaining_tokens', 'used_tokens', 'credits_this_period'],
  openai: ['cost_30d'],
  openrouter: ['limit_remaining', 'usage_monthly', 'usage_weekly'],
}

function metricPercent(metric) { return typeof metric.maximum === 'number' && metric.maximum > 0 && typeof metric.value === 'number' ? Math.min(100, Math.max(0, (metric.value / metric.maximum) * 100)) : null }
function formatMetricLabel(label) { return label.replaceAll('_', ' ') }
function numericMetric(metrics, label) { const metric = metrics.find((item) => item.label === label); return typeof metric?.value === 'number' ? metric : null }
function selectHistoryMetric(provider, snapshots) {
  const preferred = PREFERRED_METRICS[provider] || []
  const labels = [...preferred, ...new Set(snapshots.flatMap((snapshot) => (snapshot.metrics || []).map((metric) => metric.label)))]
  return labels.map((label) => ({ label, values: snapshots.map((snapshot) => numericMetric(snapshot.metrics || [], label)?.value).filter((value) => typeof value === 'number') })).find((candidate) => candidate.values.length > 1) || null
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
    ctx.strokeStyle = 'rgba(138, 180, 255, 0.25)'
    ctx.lineWidth = 1
    for (let i = 0; i < 4; i += 1) { const y = 16 + i * 28; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke() }
    if (points.length < 2) return
    const values = points.map((point) => point.value)
    const min = Math.min(...values)
    const max = Math.max(...values)
    const span = max - min || 1
    ctx.strokeStyle = '#8ab4ff'
    ctx.lineWidth = 2
    ctx.beginPath()
    points.forEach((point, index) => {
      const x = (index / (points.length - 1)) * width
      const y = height - 18 - ((point.value - min) / span) * (height - 36)
      if (index === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.stroke()
  }, [points])
  return <canvas ref={canvasRef} style={{ width: '100%', height: 120, display: 'block' }} aria-label="usage history sparkline" />
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
  const points = useMemo(() => selected ? history.map((snapshot) => ({ checked_at: snapshot.checked_at, value: numericMetric(snapshot.metrics || [], selected.label)?.value })).filter((point) => typeof point.value === 'number') : [], [history, selected])
  const first = points[0]
  const last = points[points.length - 1]
  return <Box sx={{ mt: 2 }}><Button size="small" variant="outlined" onClick={() => setExpanded((value) => !value)}>{expanded ? 'Hide history' : 'Show history'}</Button><Collapse in={expanded}><Box sx={{ mt: 2, p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>{loading && <CircularProgress size={20} />}{error && <Alert severity="error">{error}</Alert>}{!loading && !error && !selected && <Typography variant="body2" color="text.secondary">Need at least two numeric snapshots before this graph grows legs.</Typography>}{selected && <Stack gap={1}><Stack direction="row" justifyContent="space-between"><Typography variant="body2">{formatMetricLabel(selected.label)}</Typography><Typography variant="caption" color="text.secondary">{points.length} snapshots</Typography></Stack><Sparkline points={points} />{first && last && <Typography variant="caption" color="text.secondary">{String(first.value)} → {String(last.value)}</Typography>}</Stack>}</Box></Collapse></Box>
}

function UsageCard({ item }) {
  const { config, latest } = item
  const color = latest?.status === 'healthy' ? 'success' : latest?.status === 'error' ? 'error' : 'warning'
  return <Card variant="outlined" sx={{ height: '100%' }}><CardContent><Stack direction="row" justifyContent="space-between" alignItems="center" gap={2}><Box><Typography variant="overline" color="text.secondary">{config.provider}</Typography><Typography variant="h6">{config.label}</Typography></Box><Chip color={color} label={latest?.status || 'not polled'} size="small" /></Stack><Typography sx={{ mt: 2, mb: 2 }} color="text.secondary">{latest?.summary || 'No usage snapshot yet. Hit refresh; summon data from the void.'}</Typography><Stack gap={2}>{(latest?.metrics || []).map((metric) => { const percent = metricPercent(metric); return <Box key={metric.label}><Stack direction="row" justifyContent="space-between"><Typography variant="body2">{formatMetricLabel(metric.label)}</Typography><Typography variant="body2" color="text.secondary">{String(metric.value ?? '—')} {metric.unit || ''}</Typography></Stack>{percent !== null && <LinearProgress variant="determinate" value={percent} sx={{ mt: 0.75 }} />}</Box> })}</Stack>{latest?.error && <Alert severity="error" sx={{ mt: 2 }}>{latest.error}</Alert>}<UsageHistory config={config} latest={latest} /></CardContent></Card>
}
export default function DashboardPage() {
  const [items, setItems] = useState([]); const [homepage, setHomepage] = useState(null); const [loading, setLoading] = useState(true); const [error, setError] = useState('')
  async function load(poll = false) { setLoading(true); setError(''); try { if (poll) await api.pollAll(); const [usage, hp] = await Promise.all([api.usage(), api.homepage()]); setItems(usage); setHomepage(hp) } catch (err) { setError(err.message) } finally { setLoading(false) } }
  useEffect(() => { load() }, [])
  return <Stack gap={3}><Stack direction="row" alignItems="center" justifyContent="space-between"><Box><Typography variant="h4">Dashboard</Typography><Typography color="text.secondary">At-a-glance API balances, usage, and provider status.</Typography></Box><Button variant="contained" startIcon={<RefreshIcon />} onClick={() => load(true)} disabled={loading}>Poll providers</Button></Stack>{homepage && <Grid container spacing={2}>{[['Configured', homepage.configured_providers], ['Healthy', homepage.healthy_providers], ['Degraded', homepage.degraded_providers], ['Summary', homepage.summary]].map(([k, v]) => <Grid size={{ xs: 12, md: 3 }} key={k}><Card><CardContent><Typography color="text.secondary" variant="overline">{k}</Typography><Typography variant="h5">{v}</Typography></CardContent></Card></Grid>)}</Grid>}{error && <Alert severity="error">{error}</Alert>}{loading && <CircularProgress />}{!loading && items.length === 0 && <Alert severity="info">No providers configured. Settings awaits, ominously.</Alert>}<Grid container spacing={2}>{items.map((item) => <Grid size={{ xs: 12, md: 6, xl: 4 }} key={item.config.id}><UsageCard item={item} /></Grid>)}</Grid></Stack>
}