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
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import AddRoundedIcon from '@mui/icons-material/AddRounded'
import BoltRoundedIcon from '@mui/icons-material/BoltRounded'
import CloudSyncRoundedIcon from '@mui/icons-material/CloudSyncRounded'
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded'
import HubRoundedIcon from '@mui/icons-material/HubRounded'
import { api } from '../api.js'

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

export default function DataSourcesSection() {
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [actionResult, setActionResult] = useState(null)
  const [actionBusyId, setActionBusyId] = useState(null)
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
      setActionResult({ type: 'success', text: action === 'test' ? `Connection OK — ${result.records} record(s) returned` : `Sync complete — ${result.inserted} new observation(s)` })
      await load()
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
        <Stack direction="row" spacing={1} alignItems="center">
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
          <Box className="loading-state"><Stack alignItems="center" spacing={1}><CircularProgress size={22} /></Stack></Box>
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
                      <Stack direction="row" spacing={1} alignItems="center">
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
                        <Typography variant="caption" color="text.secondary" display="block">
                          Last sync: {source.status.last_success_at}
                        </Typography>
                      )}
                      {source.status?.latest_error && (
                        <Typography variant="caption" color="error.main" display="block">
                          {source.status.latest_error}
                        </Typography>
                      )}
                    </Box>
                    <Stack direction="row" spacing={1} alignItems="center">
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

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Connect Hermes Agent</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Usage Dashboard polls a read-only Hermes usage endpoint
              (<code>/usage</code>) for observed usage metadata. No prompts,
              responses, or message contents are collected.
            </Typography>
            <TextField label="Name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="hermes" helperText="Defaults to the source kind." />
            <TextField label="Hermes base URL" value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} placeholder="http://hermes-host:8080" fullWidth required />
            <TextField label="API token" type="password" value={form.token} onChange={(event) => setForm({ ...form, token: event.target.value })} helperText="Optional bearer token. Stored encrypted." />
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
