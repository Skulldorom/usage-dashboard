import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from '@mui/material'
import InsightsRoundedIcon from '@mui/icons-material/InsightsRounded'
import { api } from '../api.js'
import ProviderIcon from '../components/ProviderIcon.jsx'
import { AttributionPanel, HermesBreakdownPanel } from '../components/HermesPanels.jsx'
import {
  DEFAULT_RANGE,
  RANGE_OPTIONS,
  bucketWallClock,
  changeStatus,
  chartPoints,
  confidenceColor,
  formatMetricValue,
  formatPercent,
  formatTrend,
  isDeltaMetric,
  overviewTotalCards,
  peakLabel,
  pressureSummaryCards,
  primaryValue,
  qualityLabel,
  rangeToParams,
  riskRows,
  sortedCapacityProviders,
  unmeasurableProviders,
} from '../lib/analyticsFormat.js'

const TIMEZONE = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'

function formatAxis(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(date)
}

function TimeSeriesChart({ points, metricType, unit }) {
  const [hoverIndex, setHoverIndex] = useState(null)
  const width = 720
  const height = 220
  const pad = { top: 12, right: 12, bottom: 26, left: 8 }

  const values = points
    .map((point) => point.value)
    .filter((value) => typeof value === 'number')

  if (values.length === 0) {
    return (
      <Box className="usage-chart-empty">
        <Typography variant="body2" color="text.secondary">
          Not enough data to draw a chart yet.
        </Typography>
      </Box>
    )
  }

  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const innerW = width - pad.left - pad.right
  const innerH = height - pad.top - pad.bottom

  const x = (index) => pad.left + (points.length > 1 ? (index / (points.length - 1)) * innerW : innerW / 2)
  const y = (value) => pad.top + (1 - (value - min) / span) * innerH

  // Split the polyline into segments on gaps (missing samples read as gaps, not zero).
  const segments = []
  let current = []
  points.forEach((point, index) => {
    const hasValue = typeof point.value === 'number'
    if (!hasValue) {
      if (current.length) {
        segments.push(current)
        current = []
      }
      return
    }
    current.push({ index, value: point.value })
  })
  if (current.length) segments.push(current)

  const ticks = points.length > 1 ? [0, Math.floor((points.length - 1) / 2), points.length - 1] : [0]
  const hoveredPoint = hoverIndex === null ? null : points[hoverIndex]
  const hoveredValue = hoveredPoint ? primaryValue(hoveredPoint.raw, metricType) : null
  const hoverX = hoverIndex === null ? null : x(hoverIndex)
  const hoverY = typeof hoveredValue === 'number' ? y(hoveredValue) : null

  function handlePointerMove(event) {
    const rect = event.currentTarget.getBoundingClientRect()
    const relativeX = ((event.clientX - rect.left) / rect.width) * width
    const clamped = Math.max(pad.left, Math.min(width - pad.right, relativeX))
    const index = points.length > 1 ? Math.round(((clamped - pad.left) / innerW) * (points.length - 1)) : 0
    setHoverIndex(Math.max(0, Math.min(points.length - 1, index)))
  }

  const hoverLabel = hoveredPoint && typeof hoveredValue === 'number'
    ? `${formatAxis(hoveredPoint.x)} · ${formatMetricValue(hoveredValue, unit)}`
    : ''

  return (
    <Box className="usage-chart-wrap">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="usage-chart"
        role="img"
        aria-label="Historical usage chart"
        preserveAspectRatio="none"
        onPointerMove={handlePointerMove}
        onPointerLeave={() => setHoverIndex(null)}
        onFocus={() => setHoverIndex(points.length - 1)}
        onBlur={() => setHoverIndex(null)}
        tabIndex={0}
      >
      <defs>
        <linearGradient id="usage-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#06c8ff" stopOpacity="0.28" />
          <stop offset="100%" stopColor="#06c8ff" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map((fraction) => (
        <line key={fraction} x1={pad.left} x2={width - pad.right} y1={pad.top + innerH * fraction} y2={pad.top + innerH * fraction} stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
      ))}
      {segments.map((segment, segmentIndex) => {
        const first = segment[0]
        const last = segment[segment.length - 1]
        const areaPath = `M ${x(first.index)} ${y(first.value)} ` + segment.map((p) => `L ${x(p.index)} ${y(p.value)}`).join(' ') + ` L ${x(last.index)} ${height - pad.bottom} L ${x(first.index)} ${height - pad.bottom} Z`
        const linePath = segment.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(p.index)} ${y(p.value)}`).join(' ')
        return (
          <g key={segmentIndex}>
            <path d={areaPath} fill="url(#usage-area)" />
            <path d={linePath} fill="none" stroke="#06c8ff" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
          </g>
        )
      })}
      {ticks.map((index) => (
        <text key={index} x={x(index)} y={height - 6} textAnchor={index === 0 ? 'start' : index === points.length - 1 ? 'end' : 'middle'} className="usage-axis-label">
          {formatAxis(points[index]?.x)}
        </text>
      ))}
      <text x={pad.left} y={pad.top + 10} className="usage-axis-label">
        {metricType === 'counter' || metricType === 'rate_limit' ? `usage (${unit || ''})`.trim() : unit || ''}
      </text>
      {hoverX !== null && hoverY !== null && (
        <g className="usage-chart-hover">
          <line x1={hoverX} x2={hoverX} y1={pad.top} y2={height - pad.bottom} />
          <circle cx={hoverX} cy={hoverY} r="4" />
          <rect x={Math.min(width - 174, Math.max(10, hoverX - 82))} y={Math.max(10, hoverY - 34)} width="164" height="24" rx="6" />
          <text x={Math.min(width - 92, Math.max(92, hoverX))} y={Math.max(27, hoverY - 17)} textAnchor="middle">{hoverLabel}</text>
        </g>
      )}
    </svg>
    {hoverLabel && <div className="usage-chart-tooltip" aria-live="polite">{hoverLabel}</div>}
    </Box>
  )
}

function UsageHeatmap({ buckets, metricType }) {
  // Aggregate hourly buckets into day-of-week x hour intensity.
  const grid = Array.from({ length: 7 }, () => Array(24).fill(0))
  let max = 0
  for (const bucket of buckets || []) {
    const value = isDeltaMetric(metricType) ? bucket.total : bucket.value
    if (typeof value !== 'number') continue
    const { hour, weekday } = bucketWallClock(bucket.start)
    grid[weekday][hour] += value
    if (grid[weekday][hour] > max) max = grid[weekday][hour]
  }
  const hasData = max > 0

  if (!hasData) return <Typography variant="body2" color="text.secondary">Insufficient data for a heatmap.</Typography>

  const dayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
  const cellW = 20
  const cellH = 14
  const gap = 2
  const hourLabelW = 26
  const width = hourLabelW + 24 * (cellW + gap)
  const height = 7 * (cellH + gap) + 4

  return (
    <svg viewBox={`0 0 ${width} ${height + 16}`} className="usage-heatmap" role="img" aria-label="Time-of-day usage heatmap">
      {dayLabels.map((label, day) => (
        <text key={label} x={0} y={day * (cellH + gap) + cellH / 2 + 4} className="usage-axis-label">
          {label}
        </text>
      ))}
      {grid.map((row, day) =>
        row.map((value, hour) => (
          <rect
            key={`${day}-${hour}`}
            x={hourLabelW + hour * (cellW + gap)}
            y={day * (cellH + gap)}
            width={cellW}
            height={cellH}
            rx={2}
            fill="#06c8ff"
            fillOpacity={max ? 0.08 + 0.85 * (value / max) : 0.08}
          />
        ))
      )}
      {[0, 6, 12, 18, 23].map((hour) => (
        <text key={hour} x={hourLabelW + hour * (cellW + gap)} y={height + 14} className="usage-axis-label" textAnchor={hour === 0 ? 'start' : hour === 23 ? 'end' : 'middle'}>
          {String(hour).padStart(2, '0')}
        </text>
      ))}
    </svg>
  )
}

function ForecastPanel({ forecast, unit }) {
  if (!forecast) return null
  const { confidence, rates, metric_type: metricType } = forecast

  const rows = []
  if (metricType === 'rate_limit' || metricType === 'remaining') {
    if (forecast.remaining !== undefined) rows.push({ label: 'Remaining', value: formatMetricValue(forecast.remaining, unit) })
    if (forecast.projected_at_reset !== undefined) rows.push({ label: 'Projected at reset', value: formatMetricValue(forecast.projected_at_reset, unit) })
    if (forecast.projected_at_reset_pct !== undefined) rows.push({ label: 'Projected %', value: formatMetricValue(forecast.projected_at_reset_pct * 100, '%') })
    if (forecast.exhaustion_at) rows.push({ label: 'Est. exhaustion', value: new Date(forecast.exhaustion_at).toLocaleString() })
    if (forecast.sustainable_per_day !== undefined) rows.push({ label: 'Sustainable / day', value: formatMetricValue(forecast.sustainable_per_day, unit) })
  }
  if (metricType === 'balance') {
    if (forecast.balance !== undefined) rows.push({ label: 'Balance', value: formatMetricValue(forecast.balance, unit) })
    if (forecast.estimated_remaining_days !== undefined) rows.push({ label: 'Est. remaining', value: `${forecast.estimated_remaining_days} days` })
    if (forecast.exhaustion_date) rows.push({ label: 'Exhaustion date', value: new Date(forecast.exhaustion_date).toLocaleDateString() })
  }
  if (metricType === 'counter') {
    if (forecast.spent_this_window !== undefined) rows.push({ label: 'Spent this window', value: formatMetricValue(forecast.spent_this_window, unit) })
    if (forecast.projected_window_end !== undefined) rows.push({ label: 'Projected window end', value: formatMetricValue(forecast.projected_window_end, unit) })
  }
  if (metricType === 'rolling_total') {
    if (forecast.value !== undefined) rows.push({ label: 'Current', value: formatMetricValue(forecast.value, unit) })
  }

  if (rates?.avg_7d !== null && rates?.avg_7d !== undefined) rows.push({ label: '7-day rate', value: formatMetricValue(rates.avg_7d, unit) + '/day' })
  if (rates?.current_24h !== null && rates?.current_24h !== undefined) rows.push({ label: '24h rate', value: formatMetricValue(rates.current_24h, unit) + '/day' })

  return (
    <Card variant="outlined" className="glass-panel">
      <CardContent>
        <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="overline" color="primary.main">Forecast</Typography>
          {confidence && <Chip size="small" color={confidenceColor(confidence.level)} label={`${confidence.level} confidence`} />}
        </Stack>
        {rows.length === 0 ? (
          <Typography variant="body2" color="text.secondary">Not enough data to forecast this metric.</Typography>
        ) : (
          <Stack spacing={1}>
            {rows.map((row) => (
              <Box key={row.label} className="usage-stat-row">
                <Typography variant="body2" color="text.secondary">{row.label}</Typography>
                <Typography variant="body2">{row.value}</Typography>
              </Box>
            ))}
          </Stack>
        )}
        {confidence?.reason && <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>{confidence.reason}</Typography>}
      </CardContent>
    </Card>
  )
}

function ComparisonPanel({ comparison, unit }) {
  if (!comparison || (comparison.current === null && comparison.previous === null)) return null
  return (
    <Card variant="outlined" className="glass-panel">
      <CardContent>
        <Typography variant="overline" color="primary.main">Previous period</Typography>
        <Stack spacing={1} sx={{ mt: 1 }}>
          <Box className="usage-stat-row">
            <Typography variant="body2" color="text.secondary">Current</Typography>
            <Typography variant="body2">{formatMetricValue(comparison.current, unit)}</Typography>
          </Box>
          <Box className="usage-stat-row">
            <Typography variant="body2" color="text.secondary">Previous</Typography>
            <Typography variant="body2">{formatMetricValue(comparison.previous, unit)}</Typography>
          </Box>
          <Box className="usage-stat-row">
            <Typography variant="body2" color="text.secondary">Change</Typography>
            <Typography variant="body2" color={comparison.change_pct >= 0 ? 'error' : 'success'}>
              {comparison.change_pct === null || comparison.change_pct === undefined ? '—' : `${comparison.change_pct > 0 ? '+' : ''}${comparison.change_pct}%`}
            </Typography>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  )
}

function DailyTable({ rows, metricType, unit }) {
  if (!rows || rows.length === 0) {
    return <Typography variant="body2" color="text.secondary">No daily breakdown available.</Typography>
  }
  return (
    <Box className="usage-table" component="table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Usage</th>
          <th>Peak hour</th>
          <th>Change</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {rows.slice().reverse().map((row) => {
          const primary = isDeltaMetric(metricType) ? row.usage : row.value
          return (
            <tr key={row.date}>
              <td>{row.date}</td>
              <td>{formatMetricValue(primary, unit)}</td>
              <td>{peakLabel(row.peak_hour)}</td>
              <td>{row.change_pct === null || row.change_pct === undefined ? '—' : `${row.change_pct > 0 ? '+' : ''}${row.change_pct}%`}</td>
              <td><Chip size="small" label={changeStatus(row.change_pct)} /></td>
            </tr>
          )
        })}
      </tbody>
    </Box>
  )
}

function OverviewTotalsCards({ totals }) {
  const cards = overviewTotalCards(totals)
  if (cards.length === 0) return null
  return (
    <Grid container spacing={2}>
      {cards.map((card) => (
        <Grid size={{ xs: 6, md: 3 }} key={card.unit}>
          <Box className="summary-card glass-panel">
            <div className="summary-label">{card.label}</div>
            <div className="summary-value">{formatMetricValue(card.value, card.unit)}</div>
          </Box>
        </Grid>
      ))}
    </Grid>
  )
}

function OverviewSummaryCards({ overview }) {
  const cards = pressureSummaryCards(overview)
  return (
    <Grid container spacing={2}>
      {cards.map((card) => (
        <Grid size={{ xs: 12, sm: 6, lg: 3 }} key={card.key}>
          <Box className="summary-card glass-panel">
            <div className="summary-label">{card.label}</div>
            <div className="summary-value">{card.value}</div>
            <Typography variant="caption" color="text.secondary">{card.detail}</Typography>
          </Box>
        </Grid>
      ))}
    </Grid>
  )
}

function CapacityBars({ providers }) {
  const measurable = sortedCapacityProviders(providers)
  const unavailable = unmeasurableProviders(providers)
  return (
    <Stack spacing={1.5}>
      {measurable.length === 0 && <Typography variant="body2" color="text.secondary">No providers expose normalizable quota data yet.</Typography>}
      {measurable.map((row) => (
        <Box key={row.config_id}>
          <Stack direction="row" sx={{ justifyContent: 'space-between', gap: 2, mb: 0.5 }}>
            <Typography variant="body2">{row.provider}{row.label && row.label !== 'main' ? ` · ${row.label}` : ''}</Typography>
            <Typography variant="body2" color="text.secondary">{formatPercent(row.utilization_pct)} used</Typography>
          </Stack>
          <Box className={`capacity-bar capacity-bar-${row.utilization_pct >= 85 ? 'critical' : row.utilization_pct >= 70 ? 'warning' : 'normal'}`}>
            <Box sx={{ width: `${Math.max(0, Math.min(100, row.utilization_pct))}%` }} />
          </Box>
          <Typography variant="caption" color="text.secondary">
            {formatPercent(row.remaining_pct)} remaining{row.reset_at ? ` · resets ${new Date(row.reset_at).toLocaleString()}` : ''}
          </Typography>
        </Box>
      ))}
      {unavailable.length > 0 && (
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', pt: 1 }}>
          {unavailable.map((row) => (
            <Chip key={row.config_id} size="small" variant="outlined" label={`${row.provider}: ${row.exclusion_reason || 'No quota available'}`} />
          ))}
        </Stack>
      )}
    </Stack>
  )
}

function AttentionRisks({ overview }) {
  const rows = riskRows(overview)
  if (rows.length === 0) {
    return <Typography variant="body2" color="text.secondary">No provider currently crosses the attention threshold.</Typography>
  }
  return (
    <Grid container spacing={2}>
      {rows.map((row) => (
        <Grid size={{ xs: 12, md: 6 }} key={row.config_id}>
          <Box className={`risk-card risk-card-${row.state || 'warning'}`}>
            <Stack direction="row" sx={{ justifyContent: 'space-between', gap: 1 }}>
              <Typography variant="subtitle2">{row.provider}{row.label && row.label !== 'main' ? ` · ${row.label}` : ''}</Typography>
              <Chip size="small" color={(row.state === 'critical' || row.state === 'exhausted') ? 'error' : 'warning'} label={row.state || 'warning'} />
            </Stack>
            <Typography variant="body2" sx={{ mt: 0.75 }}>{formatPercent(row.utilization_pct)} used</Typography>
            <Typography variant="caption" color="text.secondary">
              {row.reason || `${formatPercent(row.remaining_pct)} remaining`}{row.forecast_pct ? ` · projected ${formatPercent(row.forecast_pct)}` : ''}
            </Typography>
          </Box>
        </Grid>
      ))}
    </Grid>
  )
}

function ProviderComparisonTable({ providers }) {
  if (!providers || providers.length === 0) {
    return <Typography variant="body2" color="text.secondary">No provider data to compare yet.</Typography>
  }
  return (
    <Box className="usage-table" component="table">
      <thead>
        <tr>
          <th>Provider</th>
          <th>Current usage</th>
          <th>Capacity</th>
          <th>Burn/Trend</th>
          <th>Forecast/Reset</th>
          <th>Data</th>
        </tr>
      </thead>
      <tbody>
        {providers.map((row) => (
          <tr key={row.config_id}>
            <td>{row.provider}{row.label && row.label !== 'main' ? ` · ${row.label}` : ''}</td>
            <td>{formatMetricValue(row.value, row.unit)}{row.share_pct !== null && row.share_pct !== undefined ? ` · ${row.share_pct}% of ${row.unit}` : ''}</td>
            <td>{row.utilization_pct === null || row.utilization_pct === undefined ? (row.exclusion_reason || 'No quota available') : `${formatPercent(row.utilization_pct)} used`}</td>
            <td>{row.utilization_trend_pct !== null && row.utilization_trend_pct !== undefined ? formatTrend(row.utilization_trend_pct, ' pts') : formatTrend(row.trend_pct)}</td>
            <td>{row.forecast_pct ? `Projected ${formatPercent(row.forecast_pct)}` : row.reset_at ? new Date(row.reset_at).toLocaleString() : '—'}</td>
            <td><Chip size="small" variant="outlined" label={qualityLabel(row.quality)} /></td>
          </tr>
        ))}
      </tbody>
    </Box>
  )
}

const SERIES_COLORS = ['#06c8ff', '#8b5cf6', '#38e6a1', '#ffbf69', '#ff6685', '#a78bfa', '#63e3ff', '#f0abfc']

function UtilizationChart({ comparison }) {
  if (!comparison || comparison.length === 0) {
    return <Typography variant="body2" color="text.secondary">No quota-tracking providers to overlay.</Typography>
  }
  const width = 720
  const height = 220
  const pad = { top: 12, right: 12, bottom: 26, left: 34 }
  const innerW = width - pad.left - pad.right
  const innerH = height - pad.top - pad.bottom
  const maxLen = Math.max(...comparison.map((series) => (series.buckets || []).length))
  const x = (index) => pad.left + (maxLen > 1 ? (index / (maxLen - 1)) * innerW : innerW / 2)
  const y = (value) => pad.top + (1 - Math.max(0, Math.min(100, Number(value))) / 100) * innerH

  return (
    <Box>
      <svg viewBox={`0 0 ${width} ${height}`} className="usage-chart" role="img" aria-label="Provider utilization overlay" preserveAspectRatio="none">
        {[0, 25, 50, 75, 100].map((tick) => (
          <g key={tick}>
            <line x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
            <text x={pad.left - 6} y={y(tick) + 3} textAnchor="end" className="usage-axis-label">{tick}%</text>
          </g>
        ))}
        {comparison.map((series, seriesIndex) => {
          const color = SERIES_COLORS[seriesIndex % SERIES_COLORS.length]
          const points = (series.buckets || []).map((bucket, index) => ({ index, value: bucket.value })).filter((point) => typeof point.value === 'number')
          if (points.length < 2) return null
          const d = points.map((point, i) => `${i === 0 ? 'M' : 'L'} ${x(point.index)} ${y(point.value)}`).join(' ')
          return <path key={series.config_id} d={d} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        })}
      </svg>
      <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap', mt: 1 }}>
        {comparison.map((series, seriesIndex) => (
          <Stack key={series.config_id} direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
            <Box sx={{ width: 10, height: 10, borderRadius: '50%', backgroundColor: SERIES_COLORS[seriesIndex % SERIES_COLORS.length] }} />
            <Typography variant="caption" color="text.secondary">{series.provider}{series.label && series.label !== 'main' ? ` · ${series.label}` : ''}</Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  )
}

export default function UsagePage() {
  const [configs, setConfigs] = useState([])
  const [overview, setOverview] = useState(null)
  const [selectedId, setSelectedId] = useState('all')
  const [providerInfo, setProviderInfo] = useState(null)
  const [metric, setMetric] = useState('')
  const [interval, setInterval] = useState('day')
  const [range, setRange] = useState(DEFAULT_RANGE)
  const [timeseries, setTimeseries] = useState(null)
  const [hourly, setHourly] = useState(null)
  const [daily, setDaily] = useState(null)
  const [comparison, setComparison] = useState(null)
  const [forecast, setForecast] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      try {
        const usage = await api.usage()
        if (cancelled) return
        setConfigs(usage)
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (selectedId !== 'all') return
    let cancelled = false
    const { from, to } = rangeToParams(range)
    async function loadOverview() {
      setError('')
      try {
        const data = await api.analyticsOverview({ interval, timezone: TIMEZONE, from, to })
        if (!cancelled) setOverview(data)
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }
    loadOverview()
    return () => { cancelled = true }
  }, [selectedId, interval, range])

  useEffect(() => {
    if (!selectedId || selectedId === 'all') return
    let cancelled = false
    async function loadProvider() {
      setError('')
      setProviderInfo(null)
      setMetric('')
      setTimeseries(null)
      setHourly(null)
      setDaily(null)
      setComparison(null)
      setForecast(null)
      try {
        const info = await api.analyticsProvider(selectedId)
        if (cancelled) return
        setProviderInfo(info)
        setMetric(info.preferred_metric || info.metrics[0]?.label || '')
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }
    loadProvider()
    return () => { cancelled = true }
  }, [selectedId])

  useEffect(() => {
    if (!selectedId || selectedId === 'all' || !metric) return
    let cancelled = false
    const { from, to } = rangeToParams(range)
    async function loadData() {
      setError('')
      try {
        const comparisonWindow = range === '24h' ? 'day' : range === '7d' ? 'week' : 'month'
        const [ts, hourlyData, dailyData, comparisonData, forecastData] = await Promise.all([
          api.analyticsTimeseries(selectedId, { metric, interval, timezone: TIMEZONE, from, to }),
          api.analyticsTimeseries(selectedId, { metric, interval: 'hour', timezone: TIMEZONE, from, to }),
          api.analyticsDaily(selectedId, { metric, timezone: TIMEZONE, from, to }),
          api.analyticsComparison(selectedId, { metric, timezone: TIMEZONE, window: comparisonWindow }),
          api.analyticsForecast(selectedId, { metric, timezone: TIMEZONE }),
        ])
        if (cancelled) return
        setTimeseries(ts)
        setHourly(hourlyData)
        setDaily(dailyData)
        setComparison(comparisonData)
        setForecast(forecastData)
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }
    loadData()
    return () => { cancelled = true }
  }, [selectedId, metric, interval, range])

  const metricType = useMemo(() => {
    if (!providerInfo) return 'gauge'
    const selected = providerInfo.metrics.find((m) => m.label === metric)
    return selected?.type || 'gauge'
  }, [providerInfo, metric])
  const unit = useMemo(() => {
    if (!providerInfo) return null
    const selected = providerInfo.metrics.find((m) => m.label === metric)
    return selected?.unit || null
  }, [providerInfo, metric])

  const points = useMemo(() => chartPoints(timeseries?.buckets, metricType), [timeseries, metricType])

  return (
    <>
      <header className="page-heading">
        <Box>
          <div className="page-kicker">Usage analytics</div>
          <Typography component="h1" variant="h2">Usage</Typography>
          <Typography component="p">Historical trends, peak-usage windows, and pace-based forecasts derived from your provider snapshots.</Typography>
        </Box>
      </header>

      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}
      {loading && <Box className="loading-state"><Stack spacing={2} sx={{ alignItems: 'center' }}><CircularProgress /><Typography color="text.secondary">Loading usage analytics…</Typography></Stack></Box>}

      {!loading && configs.length === 0 && (
        <Box className="empty-state">
          <div className="empty-state-icon"><InsightsRoundedIcon /></div>
          <Typography variant="h6">No providers connected</Typography>
          <Typography color="text.secondary" sx={{ mt: 1 }}>Connect a provider in Settings to begin collecting usage history.</Typography>
        </Box>
      )}

      {!loading && configs.length > 0 && (
        <Stack spacing={3}>
          <Card variant="outlined" className="glass-panel">
            <CardContent>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ flexWrap: 'wrap' }}>
                <FormControl size="small" sx={{ minWidth: 200 }}>
                  <InputLabel>Provider</InputLabel>
                  <Select value={selectedId} label="Provider" onChange={(event) => setSelectedId(event.target.value)}>
                    <MenuItem value="all">All providers</MenuItem>
                    {configs.map((item) => (
                      <MenuItem key={item.config.id} value={String(item.config.id)}>{item.config.provider} · {item.config.label}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
                {providerInfo && (
                  <FormControl size="small" sx={{ minWidth: 200 }}>
                    <InputLabel>Metric</InputLabel>
                    <Select value={metric} label="Metric" onChange={(event) => setMetric(event.target.value)}>
                      {providerInfo.metrics.map((m) => (
                        <MenuItem key={m.label} value={m.label}>{m.label.replaceAll('_', ' ')}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                )}
                <FormControl size="small" sx={{ minWidth: 140 }}>
                  <InputLabel>Range</InputLabel>
                  <Select value={range} label="Range" onChange={(event) => setRange(event.target.value)}>
                    {RANGE_OPTIONS.map((option) => (
                      <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <FormControl size="small" sx={{ minWidth: 130 }}>
                  <InputLabel>Aggregation</InputLabel>
                  <Select value={interval} label="Aggregation" onChange={(event) => setInterval(event.target.value)}>
                    <MenuItem value="hour">Hourly</MenuItem>
                    <MenuItem value="day">Daily</MenuItem>
                    <MenuItem value="week">Weekly</MenuItem>
                  </Select>
                </FormControl>
              </Stack>
            </CardContent>
          </Card>

          {selectedId === 'all' && overview && (
            <Stack spacing={2.5}>
              <OverviewSummaryCards overview={overview} />
              <Card variant="outlined" className="glass-panel">
                <CardContent>
                  <Typography variant="overline" color="primary.main">Current capacity across providers</Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>Sorted by normalized quota utilization. Providers without a known quota are excluded rather than treated as 0%.</Typography>
                  <CapacityBars providers={overview.providers} />
                </CardContent>
              </Card>
              <Card variant="outlined" className="glass-panel">
                <CardContent>
                  <Typography variant="overline" color="primary.main">Capacity over time</Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>Historical 0–100% utilization overlay. Gaps remain missing data, not zero.</Typography>
                  <UtilizationChart comparison={overview.comparison} />
                </CardContent>
              </Card>
              <Card variant="outlined" className="glass-panel">
                <CardContent>
                  <Typography variant="overline" color="primary.main">Attention / Risks</Typography>
                  <Box sx={{ mt: 1 }}><AttentionRisks overview={overview} /></Box>
                </CardContent>
              </Card>
              <Box>
                <Typography variant="overline" color="primary.main">Native totals</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>Measured usage grouped by compatible unit. Unlike units are never added together.</Typography>
                <OverviewTotalsCards totals={overview.totals} />
              </Box>
              <Card variant="outlined" className="glass-panel">
                <CardContent>
                  <Typography variant="overline" color="primary.main">Provider comparison</Typography>
                  <Box sx={{ mt: 1 }}><ProviderComparisonTable providers={overview.providers} /></Box>
                </CardContent>
              </Card>
              <HermesBreakdownPanel range={range} />
            </Stack>
          )}

          {providerInfo && !providerInfo.supported && (
            <Alert severity="info">This provider exposes generic point history only — advanced analytics (forecasts, pacing) are unavailable.</Alert>
          )}

          {providerInfo && (
            <Grid container spacing={2.5}>
              <Grid size={{ xs: 12, lg: 8 }}>
                <Card variant="outlined" className="glass-panel">
                  <CardContent>
                    <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                      <Typography variant="overline" color="primary.main">Historical usage</Typography>
                      {providerInfo.native_history && <Chip size="small" label="native history" color="primary" variant="outlined" />}
                    </Stack>
                    <TimeSeriesChart points={points} metricType={metricType} unit={unit} />
                  </CardContent>
                </Card>
              </Grid>
              <Grid size={{ xs: 12, lg: 4 }}>
                <Stack spacing={2.5}>
                  <ForecastPanel forecast={forecast} unit={unit} />
                  <ComparisonPanel comparison={comparison} unit={unit} />
                </Stack>
              </Grid>
            </Grid>
          )}

          {providerInfo && (
            <Grid container spacing={2.5}>
              <Grid size={{ xs: 12, md: 6 }}>
                <Card variant="outlined" className="glass-panel">
                  <CardContent>
                    <Typography variant="overline" color="primary.main">Daily breakdown</Typography>
                    <Box sx={{ mt: 1 }}><DailyTable rows={daily} metricType={metricType} unit={unit} /></Box>
                  </CardContent>
                </Card>
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                <Card variant="outlined" className="glass-panel">
                  <CardContent>
                    <Typography variant="overline" color="primary.main">Time-of-day heatmap</Typography>
                    <Box sx={{ mt: 1 }} className="usage-heatmap-wrap"><UsageHeatmap buckets={hourly?.buckets} metricType={metricType} /></Box>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          )}

          {providerInfo && <AttributionPanel configId={selectedId} />}
        </Stack>
      )}
    </>
  )
}
