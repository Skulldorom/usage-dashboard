import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import AddRoundedIcon from '@mui/icons-material/AddRounded'
import BoltRoundedIcon from '@mui/icons-material/BoltRounded'
import CloudSyncRoundedIcon from '@mui/icons-material/CloudSyncRounded'
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded'
import HubRoundedIcon from '@mui/icons-material/HubRounded'
import VisibilityRoundedIcon from '@mui/icons-material/VisibilityRounded'
import { api } from '../api.js'
import {
  HERMES_SIDECAR_DOCS_URL,
  HERMES_SIDECAR_INSTALL_PROMPT,
  HERMES_SIDECAR_REPO_URL,
} from '../lib/hermesSidecarInstallPrompt.js'

const STATUS_COLOR = { healthy: 'success', error: 'error', never_connected: 'default' }

function parseMappings(text) {
  const result = {}
  for (const part of (text || '').split(',')) {
    const [from, to] = part.split('=').map((value) => value.trim())
    if (from && to) result[from] = to
  }
  return result
}

function parseProfiles(text) {
  return (text || '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)
}

function formatSyncResult(result) {
  const fetched = result.records_fetched ?? 0
  const produced = result.observations_produced ?? result.observed ?? 0
  const inserted = result.inserted ?? 0
  const duplicates = result.duplicates_skipped ?? 0
  const skipped = (result.records_skipped_invalid_timestamp ?? 0)
    + (result.records_skipped_no_supported_metrics ?? 0)
  const parts = [
    `${fetched} records fetched`,
    `${produced} observations`,
    `${inserted} new`,
    `${duplicates} already imported`,
  ]
  if (result.observations_skipped_profile_filter) {
    parts.push(`${result.observations_skipped_profile_filter} filtered by profile`)
  }
  if (skipped) parts.push(`${skipped} record(s) skipped`)
  if (result.unmapped_providers?.length) {
    parts.push(`unmapped: ${result.unmapped_providers.join(', ')}`)
  }
  return parts.join(' · ')
}

function formatObservationValue(row) {
  const value = Number(row.value)
  if (row.metric === 'cost') return `$${value.toFixed(4)}`
  const text = Math.abs(value) >= 1000 ? value.toLocaleString(undefined, { maximumFractionDigits: 0 }) : String(Math.round(value * 100) / 100)
  return row.unit ? `${text} ${row.unit}` : text
}

export function InstallWithHermesSection({ onCopyInstallPrompt }) {
  return (
    <Box
      sx={{
        border: 1,
        borderColor: 'divider',
        borderRadius: 2,
        p: 2,
        bgcolor: 'background.default',
      }}
    >
      <Stack spacing={1}>
        <Typography variant="subtitle2" component="h3">
          Install with Hermes
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Using Hermes Agent? Copy this prompt and send it to Hermes to install
          and configure the Usage Sidecar automatically. The prompt only asks
          Hermes to install the sidecar; it does not configure Usage Dashboard,
          providers, mappings, or this data source form.
        </Typography>
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }} useFlexGap>
          <Button size="small" variant="contained" onClick={onCopyInstallPrompt}>
            Copy installation prompt
          </Button>
          <Button
            component="a"
            href={HERMES_SIDECAR_DOCS_URL}
            target="_blank"
            rel="noreferrer"
            size="small"
            variant="outlined"
          >
            Manual installation
          </Button>
          <Button
            component="a"
            href={HERMES_SIDECAR_REPO_URL}
            target="_blank"
            rel="noreferrer"
            size="small"
            variant="text"
          >
            Sidecar repository
          </Button>
        </Stack>
      </Stack>
    </Box>
  )
}

export default function DataSourcesSection() {
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [actionResult, setActionResult] = useState(null)
  const [actionBusyId, setActionBusyId] = useState(null)
  const [inspection, setInspection] = useState(null)
  const [inspectionOpen, setInspectionOpen] = useState(false)
  const [form, setForm] = useState({
    name: '',
    base_url: '',
    token: '',
    profiles: '',
    provider_mappings: '',
    poll_interval_minutes: 60,
  })

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setSources(await api.dataSourceConfigs())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  function openAdd() {
    setForm({ name: '', base_url: '', token: '', profiles: '', provider_mappings: '', poll_interval_minutes: 60 })
    setActionResult(null)
    setOpen(true)
  }

  async function handleSave() {
    setSaving(true)
    setError('')
    try {
      const payload = {
        kind: 'hermes',
        name: form.name || undefined,
        base_url: form.base_url || undefined,
        token: form.token || undefined,
        profiles: parseProfiles(form.profiles).length ? parseProfiles(form.profiles) : undefined,
        provider_mappings: Object.keys(parseMappings(form.provider_mappings)).length ? parseMappings(form.provider_mappings) : undefined,
        poll_interval_minutes: Number(form.poll_interval_minutes) || 60,
      }
      await api.createDataSourceConfig(payload)
      setOpen(false)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function runAction(id, action) {
    setActionBusyId(id)
    setActionResult(null)
    try {
      const result = action === 'test' ? await api.testDataSource(id) : await api.syncDataSource(id)
      setActionResult({ type: 'success', text: action === 'test' ? `Connection OK — ${result.records} record(s) returned` : formatSyncResult(result) })
      await load()
    } catch (err) {
      setActionResult({ type: 'error', text: err.message })
    } finally {
      setActionBusyId(null)
    }
  }



  async function inspect(id) {
    setActionBusyId(id)
    setActionResult(null)
    try {
      const result = await api.inspectDataSource(id, { limit: 50 })
      setInspection(result)
      setInspectionOpen(true)
    } catch (err) {
      setActionResult({ type: 'error', text: err.message })
    } finally {
      setActionBusyId(null)
    }
  }

  async function remove(id) {
    setError('')
    try {
      await api.deleteDataSourceConfig(id)
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  async function copyInstallPrompt() {
    setActionResult(null)
    try {
      if (typeof navigator === 'undefined' || !navigator.clipboard?.writeText) {
        throw new Error('Clipboard copy is not available in this browser.')
      }
      await navigator.clipboard.writeText(HERMES_SIDECAR_INSTALL_PROMPT)
      setActionResult({ type: 'success', text: 'Hermes installation prompt copied.' })
    } catch (err) {
      setActionResult({ type: 'error', text: err.message })
    }
  }

  return (
    <Paper id="data-sources" className="settings-panel glass-panel" variant="outlined">
      <div className="settings-panel-header">
        <Box>
          <Typography variant="h6">Data sources</Typography>
          <Typography variant="body2" color="text.secondary">
            Connect applications that provide additional usage telemetry. Data
            sources supplement provider-reported metrics and are not counted as
            separate usage.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <Button variant="outlined" size="small" startIcon={<AddRoundedIcon />} onClick={openAdd}>
            Add Hermes source
          </Button>
          <HubRoundedIcon color="primary" />
        </Stack>
      </div>

      <Box sx={{ p: 2 }}>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {actionResult && (
          <Alert severity={actionResult.type} sx={{ mb: 2 }}>{actionResult.text}</Alert>
        )}
        {loading ? (
          <Box className="loading-state"><Stack spacing={1} sx={{ alignItems: 'center' }}><CircularProgress size={22} /></Stack></Box>
        ) : sources.length === 0 ? (
          <Box className="empty-state">
            <div className="empty-state-icon"><HubRoundedIcon /></div>
            <Typography variant="h6">No data sources connected</Typography>
            <Typography color="text.secondary" sx={{ mt: 1 }}>
              Connect Hermes Agent to attribute provider usage to it and fill in
              gaps where providers report incomplete metrics.
            </Typography>
          </Box>
        ) : (
          <Stack spacing={1.5}>
            {sources.map((source) => {
              const status = source.status?.status || 'never_connected'
              return (
                <Box key={source.id} className="integration-card">
                  <div className="integration-card-header">
                    <Box>
                      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                        <Typography component="h3" variant="subtitle1">{source.name}</Typography>
                        <Chip size="small" color={STATUS_COLOR[status]} label={status.replace('_', ' ')} />
                      </Stack>
                      <Typography variant="body2" color="text.secondary">
                        {source.base_url || 'No URL configured'}
                        {source.poll_interval_minutes ? ` · polls every ${source.poll_interval_minutes} min` : ''}
                      </Typography>
                      {source.profiles?.length > 0 && (
                        <Typography variant="caption" color="text.secondary">
                          Profiles: {source.profiles.join(', ')}
                        </Typography>
                      )}
                      {source.status?.last_success_at && (
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          Last sync: {source.status.last_success_at}
                        </Typography>
                      )}
                      {source.status?.latest_error && (
                        <Typography variant="caption" color="error.main" sx={{ display: 'block' }}>
                          {source.status.latest_error}
                        </Typography>
                      )}
                    </Box>
                    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                      <Tooltip title="Test connection">
                        <span>
                          <IconButton size="small" disabled={actionBusyId === source.id} onClick={() => runAction(source.id, 'test')} aria-label={`Test ${source.name}`}>
                            <BoltRoundedIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>
                      <Tooltip title="Sync now">
                        <span>
                          <IconButton size="small" color="primary" disabled={actionBusyId === source.id} onClick={() => runAction(source.id, 'sync')} aria-label={`Sync ${source.name}`}>
                            <CloudSyncRoundedIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>

                      <Tooltip title="View recent observations">
                        <span>
                          <IconButton size="small" disabled={actionBusyId === source.id} onClick={() => inspect(source.id)} aria-label={`Inspect ${source.name}`}>
                            <VisibilityRoundedIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>
                      <Tooltip title="Remove data source">
                        <IconButton size="small" color="error" onClick={() => remove(source.id)} aria-label={`Remove ${source.name}`}>
                          <DeleteOutlineRoundedIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Stack>
                  </div>
                </Box>
              )
            })}
          </Stack>
        )}
      </Box>


      <Dialog open={inspectionOpen} onClose={() => setInspectionOpen(false)} fullWidth maxWidth="lg">
        <DialogTitle>Recent Hermes observations</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="info">
              Showing normalized telemetry metadata only: timestamps, provider/model/profile/session, metrics, values, and source event IDs. Prompt/response content and secrets are not exposed.
            </Alert>
            {inspection?.observations?.length ? (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Timestamp</TableCell>
                    <TableCell>Provider</TableCell>
                    <TableCell>Model</TableCell>
                    <TableCell>Profile</TableCell>
                    <TableCell>Session</TableCell>
                    <TableCell>Metric</TableCell>
                    <TableCell align="right">Value</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {inspection.observations.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell>{row.observed_at}</TableCell>
                      <TableCell>{row.provider_mapping && row.provider_mapping !== row.provider ? `${row.provider} → ${row.provider_mapping}` : row.provider}</TableCell>
                      <TableCell>{row.model || '—'}</TableCell>
                      <TableCell>{row.profile || '—'}</TableCell>
                      <TableCell>{row.session_id || '—'}</TableCell>
                      <TableCell>{row.metric.replaceAll('_', ' ')}</TableCell>
                      <TableCell align="right">{formatObservationValue(row)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <Box className="empty-state">
                <Typography variant="h6">No stored Hermes observations yet</Typography>
                <Typography color="text.secondary" sx={{ mt: 1 }}>
                  Run a sync to fetch telemetry, then inspect again. If sync fetched records but stored none, the sync diagnostics above will explain why.
                </Typography>
              </Box>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={() => setInspectionOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Connect Hermes Agent</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Usage Dashboard polls the read-only Hermes Usage Sidecar for
              observed usage metadata. No prompts, responses, or message contents
              are collected.
            </Typography>
            <Alert severity="info">
              <Stack spacing={1}>
                <Typography variant="subtitle2" component="p">
                  Hermes Usage Sidecar required
                </Typography>
                <Typography variant="body2" component="p">
                  Stock Hermes Agent does not expose the Usage Dashboard{' '}
                  <code>/usage</code> contract directly. Install the sidecar on
                  the machine running Hermes, then enter its URL and bearer token
                  here. Hermes telemetry is supplemental and observational; it
                  does not replace provider-reported authoritative usage.
                </Typography>
                <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }} useFlexGap>
                  <Button
                    component="a"
                    href={HERMES_SIDECAR_DOCS_URL}
                    target="_blank"
                    rel="noreferrer"
                    size="small"
                    variant="outlined"
                  >
                    Installation guide
                  </Button>
                  <Button
                    component="a"
                    href={HERMES_SIDECAR_REPO_URL}
                    target="_blank"
                    rel="noreferrer"
                    size="small"
                    variant="text"
                  >
                    GitHub repository
                  </Button>
                </Stack>
              </Stack>
            </Alert>
            <InstallWithHermesSection onCopyInstallPrompt={copyInstallPrompt} />
            <TextField label="Name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="hermes" helperText="Defaults to the source kind." />
            <TextField label="Hermes sidecar base URL" value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} placeholder="http://127.0.0.1:8799" fullWidth required />
            <TextField label="Bearer token" type="password" value={form.token} onChange={(event) => setForm({ ...form, token: event.target.value })} helperText="Token configured in USAGE_SIDECAR_TOKEN. Stored encrypted." />
            <TextField label="Profiles" value={form.profiles} onChange={(event) => setForm({ ...form, profiles: event.target.value })} placeholder="coder, default" helperText="Comma-separated. Leave blank for all profiles." />
            <TextField label="Provider mappings" value={form.provider_mappings} onChange={(event) => setForm({ ...form, provider_mappings: event.target.value })} placeholder="anthropic=anthropic, openrouter=openrouter" helperText="Optional overrides: hermes-provider=dashboard-provider, comma-separated." />
            <TextField label="Poll interval (minutes)" type="number" value={form.poll_interval_minutes} onChange={(event) => setForm({ ...form, poll_interval_minutes: event.target.value })} />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button color="inherit" onClick={() => setOpen(false)} disabled={saving}>Cancel</Button>
          <Button variant="contained" onClick={handleSave} disabled={saving || !form.base_url}>
            {saving ? 'Saving…' : 'Connect'}
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  )
}
