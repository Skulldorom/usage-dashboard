import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormHelperText,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import AddRoundedIcon from '@mui/icons-material/AddRounded'
import CheckRoundedIcon from '@mui/icons-material/CheckRounded'
import ContentCopyRoundedIcon from '@mui/icons-material/ContentCopyRounded'
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded'
import DragIndicatorRoundedIcon from '@mui/icons-material/DragIndicatorRounded'
import HubRoundedIcon from '@mui/icons-material/HubRounded'
import KeyRoundedIcon from '@mui/icons-material/KeyRounded'
import LaunchRoundedIcon from '@mui/icons-material/LaunchRounded'
import { api } from '../api.js'

const PROVIDER_SETUP = {
  firecrawl: {
    title: 'Firecrawl API key',
    steps: ['Sign in to the Firecrawl dashboard.', 'Open API Keys and create or copy a key beginning with fc-.', 'Paste that key below; it can read the team token and credit usage endpoints.'],
    url: 'https://www.firecrawl.dev/app/api-keys',
    linkLabel: 'Open Firecrawl API Keys',
    keyPlaceholder: 'fc-…',
  },
  deepseek: {
    title: 'DeepSeek API key',
    steps: ['Sign in to the DeepSeek Platform.', 'Create an API key from the API Keys page.', 'Make sure the account has billing credit; the dashboard reads the balance attached to this key.'],
    url: 'https://platform.deepseek.com/api_keys',
    linkLabel: 'Open DeepSeek API Keys',
    keyPlaceholder: 'sk-…',
  },
  codex: {
    title: 'Codex device login',
    steps: ['Try Start Codex device login first. If OpenAI Cloudflare blocks your Docker/server IP, use Start browser login instead.', 'Browser login opens OpenAI in your browser, then asks you to paste the localhost callback URL from the failed browser redirect.', 'Tokens are exchanged and encrypted by the backend only; access_token and refresh_token are never exposed to browser JavaScript.'],
    url: 'https://chatgpt.com/codex/settings/general#settings/Security',
    linkLabel: 'Open Codex security settings',
    keyPlaceholder: '{"access_token":"…","refresh_token":"…","expires_at":"…","account_id":"…"}',
  },
  openai: {
    title: 'OpenAI organization admin key',
    steps: ['Open your organization settings as an organization owner.', 'Create an Admin API key - not a project, standard model, or Codex key.', 'Paste the admin key below; organization-level access is required by the Costs API. Personal Codex usage has no API and is not trackable here.'],
    url: 'https://platform.openai.com/settings/organization/admin-keys',
    linkLabel: 'Open OpenAI Admin Keys',
    keyPlaceholder: 'sk-admin-…',
  },
  anthropic: {
    title: 'Anthropic Admin API key',
    steps: ['Use a Claude Platform organization account; the Admin API is unavailable to individual accounts.', 'As an organization admin, open Settings > Admin keys.', 'Create and paste an Admin API key beginning with sk-ant-admin. A normal inference key cannot read usage reports.'],
    url: 'https://platform.claude.com/settings/admin-keys',
    linkLabel: 'Open Anthropic Admin keys',
    keyPlaceholder: 'sk-ant-admin…',
  },
  openrouter: {
    title: 'OpenRouter API key',
    steps: ['Sign in to OpenRouter and open Keys.', 'Create a standard API key and optionally give it a credit limit.', 'Paste the key below; the dashboard reports usage and the remaining configured limit.'],
    url: 'https://openrouter.ai/keys',
    linkLabel: 'Open OpenRouter Keys',
    keyPlaceholder: 'sk-or-v1-…',
  },
  custom_http: {
    title: 'Custom JSON endpoint',
    steps: ['Choose an HTTP endpoint that returns JSON.', 'Enter its base URL and relative path, then configure the required authentication header.', 'Provide a JSON path for the metric to display. Use Test connection before saving.'],
    keyPlaceholder: 'Secret inserted into the auth header',
  },
}


const HOMEPAGE_WIDGET_FIELDS = [
  ['summary', 'Summary'],
  ['configured_providers', 'Configured'],
  ['healthy_providers', 'Healthy'],
  ['degraded_providers', 'Degraded'],
]

const initialHomepageForm = {
  dashboardUrl: '',
  refreshInterval: '300000',
  displayMode: 'dynamic-list',
  authMode: 'bearer',
  token: '',
  includeToken: false,
}

function yamlQuote(value) {
  const text = String(value ?? '').trim()
  if (!text) return '""'
  if (/^[A-Za-z0-9_./:@-]+$/.test(text)) return text
  return JSON.stringify(text)
}

function joinUrl(base, path) {
  const safeBase = (base || 'https://usage-dashboard.example.com').trim().replace(/\/+$/, '')
  const safePath = (path || '/api/v1/homepage').trim()
  return `${safeBase}${safePath.startsWith('/') ? safePath : `/${safePath}`}`
}

function homepageYaml(form) {
  const dashboardUrl = (form.dashboardUrl || 'https://usage-dashboard.example.com').trim().replace(/\/+$/, '')
  const apiUrl = joinUrl(dashboardUrl, '/api/v1/homepage')
  const tokenValue = form.includeToken && form.token.trim() ? form.token.trim() : 'REPLACE_WITH_ADMIN_OR_HOMEPAGE_TOKEN'
  const refreshInterval = String(form.refreshInterval || '').trim()
  const lines = [
    '- Usage Dashboard:',
    `    href: ${yamlQuote(dashboardUrl)}`,
    '    widget:',
    '      type: customapi',
    `      url: ${yamlQuote(apiUrl)}`,
    '      method: GET',
  ]
  if (refreshInterval) lines.push(`      refreshInterval: ${yamlQuote(refreshInterval)}`)
  if (form.displayMode === 'dynamic-list') lines.push('      display: dynamic-list')
  if (form.authMode === 'bearer') {
    lines.push('      headers:')
    lines.push(`        Authorization: ${yamlQuote(`Bearer ${tokenValue}`)}`)
  }
  lines.push('      mappings:')
  if (form.displayMode === 'dynamic-list') {
    lines.push('        items: list')
    lines.push('        name: label')
    lines.push('        label: value')
    lines.push('        format: text')
  } else {
    HOMEPAGE_WIDGET_FIELDS.forEach(([field, label]) => {
      lines.push(`        - field: ${field}`)
      lines.push(`          label: ${label}`)
    })
  }
  return `${lines.join('\n')}\n`
}

const initialForm = {
  provider: 'firecrawl',
  label: '',
  api_key: '',
  base_url: '',
  custom_method: 'GET',
  custom_path: '',
  custom_auth_header_name: 'Authorization',
  custom_auth_header_template: 'Bearer {api_key}',
  custom_metric_label: 'remaining',
  custom_metric_path: '$.credits.remaining',
  custom_metric_unit: 'credits',
  custom_metric_maximum_path: '',
}

export default function SettingsPage() {
  const [providers, setProviders] = useState([])
  const [configs, setConfigs] = useState([])
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(initialForm)
  const [error, setError] = useState('')
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [codexDeviceFlow, setCodexDeviceFlow] = useState(null)
  const [codexBrowserFlow, setCodexBrowserFlow] = useState(null)
  const [codexCallback, setCodexCallback] = useState('')
  const [codexDeviceStatus, setCodexDeviceStatus] = useState('')
  const [codexDeviceBusy, setCodexDeviceBusy] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [testError, setTestError] = useState('')
  const [homepageForm, setHomepageForm] = useState(() => ({
    ...initialHomepageForm,
    dashboardUrl: typeof window !== 'undefined' ? window.location.origin : '',
  }))
  const [homepageCopied, setHomepageCopied] = useState(false)
  const [draggingConfigId, setDraggingConfigId] = useState(null)
  const [dragOverConfigId, setDragOverConfigId] = useState(null)
  const dragCommitRef = useRef(null)
  const homepagePreview = useMemo(() => homepageYaml(homepageForm), [homepageForm])
  const selectedProvider = useMemo(() => providers.find((provider) => provider.id === form.provider), [providers, form.provider])
  const isCustom = form.provider === 'custom_http'
  const isCodex = form.provider === 'codex'
  const setup = PROVIDER_SETUP[form.provider]

  const load = useCallback(async () => {
    setError('')
    try {
      const providerRows = await api.providers()
      setProviders(providerRows)
      setForm((current) => {
        if (providerRows.length && !providerRows.some((provider) => provider.id === current.provider)) return { ...initialForm, provider: providerRows[0].id }
        return current
      })
    } catch (err) {
      setProviders([])
      setError(err.message)
      return
    }
    try {
      setConfigs(await api.configs())
    } catch (err) {
      setConfigs([])
      setError(err.message)
    }
  }, [])

  useEffect(() => { load() }, [load])

  function payloadFromForm() {
    const payload = { provider: form.provider, label: form.label.trim() || null, api_key: form.api_key.trim(), base_url: form.base_url.trim() || null, is_enabled: true, extra: {} }
    if (isCustom) {
      payload.extra = {
        method: form.custom_method,
        path: form.custom_path.trim(),
        auth_header_name: form.custom_auth_header_name.trim() || 'Authorization',
        auth_header_template: form.custom_auth_header_template.trim() || 'Bearer {api_key}',
        metrics: [{ label: form.custom_metric_label.trim(), path: form.custom_metric_path.trim(), unit: form.custom_metric_unit.trim() || null, maximum_path: form.custom_metric_maximum_path.trim() || null }],
      }
    }
    return payload
  }

  async function submit() {
    setError('')
    setSaving(true)
    try {
      await api.createConfig(payloadFromForm())
      setOpen(false)
      setForm(initialForm)
      await load()
    } catch (err) { setError(err.message) }
    finally { setSaving(false) }
  }

  async function testConnection() {
    setError('')
    setTestError('')
    setTestResult(null)
    setTesting(true)
    try { setTestResult(await api.testConfig(payloadFromForm())) }
    catch (err) { setTestError(err.message) }
    finally { setTesting(false) }
  }

  async function remove(id) { await api.deleteConfig(id); await load() }
  function updateHomepageForm(patch) {
    setHomepageCopied(false)
    setHomepageForm((current) => ({ ...current, ...patch }))
  }
  async function copyHomepageYaml() {
    setHomepageCopied(false)
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(homepagePreview)
      else window.prompt('Copy Homepage YAML', homepagePreview)
      setHomepageCopied(true)
      window.setTimeout(() => setHomepageCopied(false), 2200)
    } catch {
      window.prompt('Copy Homepage YAML', homepagePreview)
    }
  }
  async function toggleApi(config) { await api.updateConfig(config.id, { is_enabled: !config.is_enabled }); await load() }
  async function toggleUi(config) { await api.updateConfig(config.id, { is_visible: !config.is_visible }); await load() }
  async function persistConfigOrder(nextConfigs) {
    setConfigs(nextConfigs)
    try { setConfigs(await api.reorderConfigs(nextConfigs.map((config) => config.id))) }
    catch (err) { setError(err.message); await load() }
  }
  async function moveConfig(configId, direction) {
    const currentIndex = configs.findIndex((config) => config.id === configId)
    const nextIndex = currentIndex + direction
    if (currentIndex < 0 || nextIndex < 0 || nextIndex >= configs.length) return
    const nextConfigs = [...configs]
    const [moved] = nextConfigs.splice(currentIndex, 1)
    nextConfigs.splice(nextIndex, 0, moved)
    await persistConfigOrder(nextConfigs)
  }
  function reorderConfigToTarget(sourceId, targetId) {
    if (!sourceId || !targetId || sourceId === targetId) return
    const sourceIndex = configs.findIndex((config) => config.id === sourceId)
    const targetIndex = configs.findIndex((config) => config.id === targetId)
    if (sourceIndex < 0 || targetIndex < 0) return
    const nextConfigs = [...configs]
    const [moved] = nextConfigs.splice(sourceIndex, 1)
    nextConfigs.splice(targetIndex, 0, moved)
    persistConfigOrder(nextConfigs)
  }
  function scheduleDragReorder(sourceId, targetId) {
    window.clearTimeout(dragCommitRef.current)
    if (!sourceId || !targetId || sourceId === targetId) return
    dragCommitRef.current = window.setTimeout(() => reorderConfigToTarget(sourceId, targetId), 90)
  }
  function endConfigDrag() {
    window.clearTimeout(dragCommitRef.current)
    setDraggingConfigId(null)
    setDragOverConfigId(null)
  }
  async function startCodexDeviceLogin() {
    setError('')
    setTestError('')
    setTestResult(null)
    setCodexDeviceStatus('Requesting device code…')
    setCodexDeviceBusy(true)
    try {
      const flow = await api.startCodexDeviceOAuth()
      setCodexDeviceFlow(flow)
      setCodexBrowserFlow(null)
      setCodexCallback('')
      setCodexDeviceStatus('Open the link, enter the code, then leave this dialog open while polling completes.')
      if (flow.verification_uri_complete) window.open(flow.verification_uri_complete, '_blank', 'noopener,noreferrer')
    } catch (err) {
      setCodexDeviceStatus('')
      setTestError(err.message)
    } finally {
      setCodexDeviceBusy(false)
    }
  }

  async function startCodexBrowserLogin() {
    setError('')
    setTestError('')
    setTestResult(null)
    setCodexDeviceStatus('Creating browser login link…')
    setCodexDeviceBusy(true)
    try {
      const flow = await api.startCodexBrowserOAuth()
      setCodexBrowserFlow(flow)
      setCodexDeviceFlow(null)
      setCodexCallback('')
      setCodexDeviceStatus('Open the login link. After OpenAI redirects to localhost, copy the full browser URL and paste it below.')
      window.open(flow.authorization_url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      setCodexDeviceStatus('')
      setTestError(err.message)
    } finally {
      setCodexDeviceBusy(false)
    }
  }

  async function completeCodexBrowserLogin() {
    if (!codexBrowserFlow?.flow_id || !codexCallback.trim()) return
    setError('')
    setTestError('')
    setCodexDeviceBusy(true)
    try {
      const result = await api.completeCodexBrowserOAuth(codexBrowserFlow.flow_id, { label: form.label.trim() || null, callback: codexCallback.trim() })
      if (result.status === 'completed') {
        setCodexDeviceStatus(`Codex connected as ${result.config?.label || 'codex'}.`)
        setCodexBrowserFlow(null)
        setCodexCallback('')
        setOpen(false)
        setForm(initialForm)
        await load()
      } else {
        setCodexDeviceStatus('')
        setTestError(result.error || 'Codex browser authorization did not complete.')
      }
    } catch (err) {
      setTestError(err.message)
    } finally {
      setCodexDeviceBusy(false)
    }
  }

  async function pollCodexDeviceLogin() {
    if (!codexDeviceFlow?.flow_id) return
    setError('')
    setTestError('')
    setCodexDeviceBusy(true)
    try {
      const result = await api.pollCodexDeviceOAuth(codexDeviceFlow.flow_id, { label: form.label.trim() || null })
      if (result.status === 'completed') {
        setCodexDeviceStatus(`Codex connected as ${result.config?.label || 'codex'}.`)
        setCodexDeviceFlow(null)
        setOpen(false)
        setForm(initialForm)
        await load()
      } else if (result.status === 'pending' || result.status === 'slow_down') {
        setCodexDeviceStatus(`Still waiting for OpenAI authorization. Try again in ${result.interval_seconds || codexDeviceFlow.interval_seconds || 5}s.`)
      } else {
        setCodexDeviceStatus('')
        setTestError(result.error || 'Codex device authorization did not complete.')
      }
    } catch (err) {
      setTestError(err.message)
    } finally {
      setCodexDeviceBusy(false)
    }
  }

  const missingRequired = (!isCodex && !form.api_key.trim()) || (isCustom && (!form.base_url.trim() || !form.custom_path.trim() || !form.custom_metric_label.trim() || !form.custom_metric_path.trim()))
  const testDisabled = testing || saving || missingRequired
  const saveDisabled = testing || saving || missingRequired || (isCodex && !form.api_key.trim())

  return <>
    <header className="page-heading">
      <Box><div className="page-kicker">Connections</div><Typography component="h1" variant="h2">Provider settings</Typography><Typography component="p">Manage credentials and custom endpoints. Secrets are encrypted before storage and never returned in full.</Typography></Box>
      <Button variant="contained" startIcon={<AddRoundedIcon />} onClick={() => { setOpen(true); setTestResult(null); setTestError(''); setCodexDeviceFlow(null); setCodexBrowserFlow(null); setCodexCallback(''); setCodexDeviceStatus('') }}>Add provider</Button>
    </header>
    {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}
    <Paper className="settings-panel glass-panel" variant="outlined">
      <div className="settings-panel-header"><Box><Typography variant="h6">Connected providers</Typography><Typography variant="body2" color="text.secondary">{configs.length} connection{configs.length === 1 ? '' : 's'} configured</Typography></Box><KeyRoundedIcon color="primary" /></div>
      {configs.length === 0 ? <Box className="empty-state" sx={{ m: 2 }}><div className="empty-state-icon"><HubRoundedIcon /></div><Typography variant="h6">Nothing connected yet</Typography><Typography color="text.secondary" sx={{ mt: 1 }}>Add a provider to start collecting usage telemetry.</Typography></Box> : <div className="config-list">{configs.map((config, index) => {
        const initials = config.provider.split('_').map((word) => word[0]).join('').slice(0, 2)
        const dragging = draggingConfigId === config.id
        const dragOver = dragOverConfigId === config.id && draggingConfigId !== config.id
        return <div
          className={`config-row${dragging ? ' is-dragging' : ''}${dragOver ? ' is-drag-over' : ''}`}
          key={config.id}
          draggable
          onDragStart={(event) => { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', String(config.id)); setDraggingConfigId(config.id) }}
          onDragEnter={(event) => { event.preventDefault(); setDragOverConfigId(config.id); scheduleDragReorder(draggingConfigId, config.id) }}
          onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'move' }}
          onDrop={(event) => { event.preventDefault(); reorderConfigToTarget(Number(event.dataTransfer.getData('text/plain')), config.id); endConfigDrag() }}
          onDragEnd={endConfigDrag}
        >
          <div className="config-order-controls" aria-label={`Reorder ${config.label}`}>
            <Tooltip title="Drag to reorder"><button type="button" className="config-drag-handle" aria-label={`Drag ${config.label} to reorder`}><DragIndicatorRoundedIcon /></button></Tooltip>
            <IconButton size="small" onClick={() => moveConfig(config.id, -1)} disabled={index === 0} aria-label={`Move ${config.label} up`}>↑</IconButton>
            <IconButton size="small" onClick={() => moveConfig(config.id, 1)} disabled={index === configs.length - 1} aria-label={`Move ${config.label} down`}>↓</IconButton>
          </div>
          <div className="config-identity"><div className="config-avatar" aria-hidden="true">{initials}</div><div><span>Provider</span><strong>{config.label}</strong><Typography variant="caption" color="text.secondary">{config.provider}</Typography></div></div>
          <div className="config-detail"><span>Credential</span>{config.api_key_masked}</div>
          <div className="config-detail"><span>Endpoint</span>{config.base_url || 'Provider default'}</div>
          <div className="config-actions">
            <label className="config-switch"><span>API</span><Tooltip title={config.is_enabled ? 'Disable API polling and Homepage output' : 'Enable API polling and Homepage output'}><Switch checked={config.is_enabled} onChange={() => toggleApi(config)} color="success" inputProps={{ 'aria-label': `${config.is_enabled ? 'Disable' : 'Enable'} API for ${config.label}` }} /></Tooltip></label>
            <label className="config-switch"><span>UI</span><Tooltip title={config.is_visible ? 'Hide from main dashboard' : 'Show on main dashboard'}><Switch checked={config.is_visible} onChange={() => toggleUi(config)} color="primary" inputProps={{ 'aria-label': `${config.is_visible ? 'Hide' : 'Show'} ${config.label} on main dashboard` }} /></Tooltip></label>
            <Tooltip title="Remove provider"><IconButton color="error" onClick={() => remove(config.id)} aria-label={`Remove ${config.label}`}><DeleteOutlineRoundedIcon /></IconButton></Tooltip>
          </div>
        </div>
      })}</div>}
    </Paper>
    <Paper className="settings-panel homepage-integration-panel glass-panel" variant="outlined">
      <div className="settings-panel-header"><Box><Typography variant="h6">Homepage integration</Typography><Typography variant="body2" color="text.secondary">Generate a paste-ready services.yaml entry for gethomepage.dev.</Typography></Box><ContentCopyRoundedIcon color="primary" /></div>
      <Box className="homepage-guide">
        <Typography component="h3" variant="subtitle1">Where this YAML goes</Typography>
        <Typography variant="body2" color="text.secondary">Paste the generated service block into the Homepage group you want inside <code>services.yaml</code>. The generator always creates a single <strong>Usage Dashboard</strong> service pointed at the existing <code>/api/v1/homepage</code> endpoint. Dynamic provider list is the default because it renders one row per enabled API. Switch to summary cards only when you want top-level stats.</Typography>
        <Typography variant="caption" color="text.secondary">Tip: if you set <code>HOMEPAGE_ALLOWED_HOSTS</code> for the Homepage host, choose “No auth header”. Otherwise keep the bearer header and use an admin/homepage token.</Typography>
      </Box>
      <Box className="homepage-config-grid">
        <Stack spacing={2}>
          <TextField label="Usage Dashboard URL / hostname" value={homepageForm.dashboardUrl} onChange={(event) => updateHomepageForm({ dashboardUrl: event.target.value })} placeholder="https://usage.example.com" helperText="The public URL Homepage can reach. The API path is fixed to /api/v1/homepage." />
          <TextField label="Refresh interval (ms)" value={homepageForm.refreshInterval} onChange={(event) => updateHomepageForm({ refreshInterval: event.target.value })} placeholder="300000" helperText="Homepage refresh interval in milliseconds. Leave blank to omit." />
          <FormControl fullWidth><InputLabel>Homepage display</InputLabel><Select label="Homepage display" value={homepageForm.displayMode} onChange={(event) => updateHomepageForm({ displayMode: event.target.value })}><MenuItem value="dynamic-list">Dynamic provider list</MenuItem><MenuItem value="summary">Summary cards</MenuItem></Select><FormHelperText>Dynamic list renders each enabled provider row from the API's list payload.</FormHelperText></FormControl>
          <FormControl fullWidth><InputLabel>Authentication</InputLabel><Select label="Authentication" value={homepageForm.authMode} onChange={(event) => updateHomepageForm({ authMode: event.target.value })}><MenuItem value="bearer">Bearer Authorization header</MenuItem><MenuItem value="none">No auth header / allowed host</MenuItem></Select><FormHelperText>Use no auth only when Homepage is allowed by host or protected by your network.</FormHelperText></FormControl>
          {homepageForm.authMode === 'bearer' && <>
            <TextField label="Token (optional)" type="password" value={homepageForm.token} onChange={(event) => updateHomepageForm({ token: event.target.value })} helperText="Left blank, the YAML keeps a safe placeholder instead of exposing a secret." />
            <label className="config-switch homepage-token-switch"><span>Include token in YAML</span><Tooltip title="Off keeps a placeholder so copied YAML does not leak secrets on screen."><Switch checked={homepageForm.includeToken} onChange={(event) => updateHomepageForm({ includeToken: event.target.checked })} color="warning" inputProps={{ 'aria-label': 'Include token in generated YAML' }} /></Tooltip></label>
          </>}
        </Stack>
        <Box className="homepage-yaml-preview">
          <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2} sx={{ mb: 1.5 }}>
            <Box><Typography variant="overline" color="primary.main">Live YAML preview</Typography><Typography variant="caption" color="text.secondary" display="block">Updates as you type; copy, paste, done.</Typography></Box>
            <Button variant="contained" size="small" onClick={copyHomepageYaml} startIcon={homepageCopied ? <CheckRoundedIcon /> : <ContentCopyRoundedIcon />}>{homepageCopied ? 'Copied' : 'Copy YAML'}</Button>
          </Stack>
          <pre><code>{homepagePreview}</code></pre>
        </Box>
      </Box>
    </Paper>
    <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
      <DialogTitle><Stack spacing={0.75}><Typography component="span" display="block" variant="overline" color="primary.main">New connection</Typography><Typography component="span" display="block" variant="h5">Add API provider</Typography></Stack></DialogTitle>
      <DialogContent>
        <Stack spacing={2.25} sx={{ mt: 1 }}>
          <FormControl fullWidth><InputLabel>Provider</InputLabel><Select label="Provider" value={form.provider} onChange={(event) => setForm({ ...initialForm, provider: event.target.value })}>{providers.map((provider) => <MenuItem key={provider.id} value={provider.id}>{provider.name}</MenuItem>)}</Select>{selectedProvider && <FormHelperText>{selectedProvider.description}</FormHelperText>}</FormControl>
          {setup && <Box className="provider-setup-guide">
            <Typography component="h3" variant="subtitle2">How to connect {selectedProvider?.name || 'this provider'}</Typography>
            <Typography variant="caption" color="text.secondary">{setup.title}</Typography>
            <ol>{setup.steps.map((step) => <li key={step}>{step}</li>)}</ol>
            {setup.url && <Button component="a" href={setup.url} target="_blank" rel="noreferrer" size="small" variant="outlined" endIcon={<LaunchRoundedIcon />} aria-label={`${setup.linkLabel} (opens in a new tab)`}>{setup.linkLabel}</Button>}
          </Box>}
          <TextField label="Connection label (optional)" value={form.label} onChange={(event) => setForm({ ...form, label: event.target.value })} placeholder="Auto-filled when blank" helperText="Leave blank to auto-fill a unique label." />
          {isCodex && <Box className="provider-setup-guide">
            <Typography component="h3" variant="subtitle2">Connect without Codex CLI</Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Button variant="contained" onClick={startCodexDeviceLogin} disabled={codexDeviceBusy} startIcon={codexDeviceBusy ? <CircularProgress size={16} color="inherit" /> : null}>Start Codex device login</Button>
              <Button variant="outlined" onClick={startCodexBrowserLogin} disabled={codexDeviceBusy}>Start browser login fallback</Button>
              {codexDeviceFlow && <Button variant="outlined" onClick={pollCodexDeviceLogin} disabled={codexDeviceBusy}>I authorized it - check now</Button>}
            </Stack>
            {codexDeviceFlow && <Stack spacing={1} sx={{ mt: 1.5 }}>
              <Typography variant="body2">Open <a href={codexDeviceFlow.verification_uri_complete || codexDeviceFlow.verification_uri} target="_blank" rel="noreferrer">{codexDeviceFlow.verification_uri}</a> and enter:</Typography>
              <Typography variant="h5" component="code" sx={{ letterSpacing: '.08em' }}>{codexDeviceFlow.user_code}</Typography>
              <Typography variant="caption" color="text.secondary">Expires at {new Date(codexDeviceFlow.expires_at).toLocaleString()}.</Typography>
            </Stack>}
            {codexBrowserFlow && <Stack spacing={1} sx={{ mt: 1.5 }}>
              <Button component="a" href={codexBrowserFlow.authorization_url} target="_blank" rel="noreferrer" size="small" variant="outlined" endIcon={<LaunchRoundedIcon />}>Open OpenAI browser login</Button>
              <Typography variant="caption" color="text.secondary">When your browser lands on a localhost error page, copy the full address bar URL and paste it here. The one-time code is exchanged server-side.</Typography>
              <TextField label="OpenAI localhost callback URL" value={codexCallback} onChange={(event) => setCodexCallback(event.target.value)} placeholder="http://localhost:1455/auth/callback?code=…&state=…" multiline minRows={2} />
              <Button variant="contained" onClick={completeCodexBrowserLogin} disabled={codexDeviceBusy || !codexCallback.trim()}>Complete browser login</Button>
            </Stack>}
            {codexDeviceStatus && <Alert severity="info" sx={{ mt: 1.5 }}>{codexDeviceStatus}</Alert>}
          </Box>}
          <TextField label={isCodex ? 'Manual OAuth token bundle fallback' : isCustom ? 'Secret / API key' : 'API key'} value={form.api_key} type="password" multiline={isCodex} minRows={isCodex ? 3 : undefined} onChange={(event) => setForm({ ...form, api_key: event.target.value })} placeholder={setup?.keyPlaceholder} helperText={isCustom ? 'Inserted into the auth header template as {api_key}; never put secrets in URLs.' : isCodex ? 'Optional fallback only. Prefer device login above; pasted JSON is still encrypted at rest.' : `Use the ${setup?.title || 'key'} described above.`} />
          <TextField label="Base URL override" value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} placeholder={isCustom ? 'https://api.example.com' : 'Optional -- provider default will be used'} required={isCustom} />
          {isCustom && <Stack spacing={2.25}>
            <Typography className="dialog-section-label">Custom request</Typography>
            <FormControl fullWidth><InputLabel>HTTP method</InputLabel><Select label="HTTP method" value={form.custom_method} onChange={(event) => setForm({ ...form, custom_method: event.target.value })}><MenuItem value="GET">GET</MenuItem><MenuItem value="POST">POST</MenuItem></Select></FormControl>
            <TextField label="Path" value={form.custom_path} onChange={(event) => setForm({ ...form, custom_path: event.target.value })} placeholder="/v1/billing" required />
            <TextField label="Auth header name" value={form.custom_auth_header_name} onChange={(event) => setForm({ ...form, custom_auth_header_name: event.target.value })} />
            <TextField label="Auth header template" value={form.custom_auth_header_template} onChange={(event) => setForm({ ...form, custom_auth_header_template: event.target.value })} helperText="Use {api_key} where the encrypted secret should be inserted." />
            <Typography className="dialog-section-label">Metric extraction</Typography>
            <TextField label="Metric label" value={form.custom_metric_label} onChange={(event) => setForm({ ...form, custom_metric_label: event.target.value })} />
            <TextField label="JSON path" value={form.custom_metric_path} onChange={(event) => setForm({ ...form, custom_metric_path: event.target.value })} helperText="Supports simple paths such as $.credits.remaining and $.items[0].usage." />
            <TextField label="Unit" value={form.custom_metric_unit} onChange={(event) => setForm({ ...form, custom_metric_unit: event.target.value })} />
            <TextField label="Maximum JSON path (optional)" value={form.custom_metric_maximum_path} onChange={(event) => setForm({ ...form, custom_metric_maximum_path: event.target.value })} />
          </Stack>}
          {testError && <Alert severity="error">Test failed: {testError}</Alert>}
          {testResult && <Alert severity="success">Test succeeded: {testResult.summary}<br />{(testResult.metrics || []).map((metric) => `${metric.label}: ${metric.value ?? '-'}${metric.unit ? ` ${metric.unit}` : ''}`).join(' · ')}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 3, flexWrap: 'wrap' }}><Button color="inherit" onClick={() => setOpen(false)} disabled={testing || saving}>Cancel</Button><Button onClick={testConnection} disabled={testDisabled} startIcon={testing ? <CircularProgress size={16} /> : null}>{testing ? 'Testing…' : 'Test connection'}</Button><Button variant="contained" onClick={submit} disabled={saveDisabled} startIcon={saving ? <CircularProgress size={16} color="inherit" /> : null}>{saving ? 'Saving…' : 'Save provider'}</Button></DialogActions>
    </Dialog>
  </>
}
