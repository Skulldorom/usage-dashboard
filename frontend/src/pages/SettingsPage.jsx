import { useCallback, useEffect, useMemo, useState } from 'react'
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
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded'
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
  openai: {
    title: 'OpenAI organization admin key',
    steps: ['Open your organization settings as an organization owner.', 'Create an Admin API key—not a project or standard model API key.', 'Paste the admin key below; organization-level access is required by the Costs API.'],
    url: 'https://platform.openai.com/settings/organization/admin-keys',
    linkLabel: 'Open OpenAI Admin Keys',
    keyPlaceholder: 'sk-admin-…',
  },
  anthropic: {
    title: 'Anthropic Admin API key',
    steps: ['Use a Claude Platform organization account; the Admin API is unavailable to individual accounts.', 'As an organization admin, open Settings → Admin keys.', 'Create and paste an Admin API key beginning with sk-ant-admin. A normal inference key cannot read usage reports.'],
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
  const [testResult, setTestResult] = useState(null)
  const [testError, setTestError] = useState('')
  const selectedProvider = useMemo(() => providers.find((provider) => provider.id === form.provider), [providers, form.provider])
  const isCustom = form.provider === 'custom_http'
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
    const payload = { provider: form.provider, label: form.label, api_key: form.api_key, base_url: form.base_url || null, is_enabled: true, extra: {} }
    if (isCustom) {
      payload.extra = {
        method: form.custom_method,
        path: form.custom_path,
        auth_header_name: form.custom_auth_header_name || 'Authorization',
        auth_header_template: form.custom_auth_header_template || 'Bearer {api_key}',
        metrics: [{ label: form.custom_metric_label, path: form.custom_metric_path, unit: form.custom_metric_unit || null, maximum_path: form.custom_metric_maximum_path || null }],
      }
    }
    return payload
  }

  async function submit() {
    setError('')
    try {
      await api.createConfig(payloadFromForm())
      setOpen(false)
      setForm(initialForm)
      await load()
    } catch (err) { setError(err.message) }
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
  async function toggle(config) { await api.updateConfig(config.id, { is_enabled: !config.is_enabled }); await load() }
  const testDisabled = testing || !form.label || !form.api_key || (isCustom && (!form.base_url || !form.custom_path))

  return <>
    <header className="page-heading">
      <Box><div className="page-kicker">Connections</div><Typography component="h1" variant="h2">Provider settings</Typography><Typography component="p">Manage credentials and custom endpoints. Secrets are encrypted before storage and never returned in full.</Typography></Box>
      <Button variant="contained" startIcon={<AddRoundedIcon />} onClick={() => { setOpen(true); setTestResult(null); setTestError('') }}>Add provider</Button>
    </header>
    {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}
    <Paper className="settings-panel glass-panel" variant="outlined">
      <div className="settings-panel-header"><Box><Typography variant="h6">Connected providers</Typography><Typography variant="body2" color="text.secondary">{configs.length} connection{configs.length === 1 ? '' : 's'} configured</Typography></Box><KeyRoundedIcon color="primary" /></div>
      {configs.length === 0 ? <Box className="empty-state" sx={{ m: 2 }}><div className="empty-state-icon"><HubRoundedIcon /></div><Typography variant="h6">Nothing connected yet</Typography><Typography color="text.secondary" sx={{ mt: 1 }}>Add a provider to start collecting usage telemetry.</Typography></Box> : <div className="config-list">{configs.map((config) => {
        const initials = config.provider.split('_').map((word) => word[0]).join('').slice(0, 2)
        return <div className="config-row" key={config.id}>
          <div className="config-identity"><div className="config-avatar" aria-hidden="true">{initials}</div><div><span>Provider</span><strong>{config.label}</strong><Typography variant="caption" color="text.secondary">{config.provider}</Typography></div></div>
          <div className="config-detail"><span>Credential</span>{config.api_key_masked}</div>
          <div className="config-detail"><span>Endpoint</span>{config.base_url || 'Provider default'}</div>
          <div className="config-actions"><Tooltip title={config.is_enabled ? 'Disable provider' : 'Enable provider'}><Switch checked={config.is_enabled} onChange={() => toggle(config)} color="success" inputProps={{ 'aria-label': `${config.is_enabled ? 'Disable' : 'Enable'} ${config.label}` }} /></Tooltip><Tooltip title="Remove provider"><IconButton color="error" onClick={() => remove(config.id)} aria-label={`Remove ${config.label}`}><DeleteOutlineRoundedIcon /></IconButton></Tooltip></div>
        </div>
      })}</div>}
    </Paper>
    <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
      <DialogTitle><Typography component="span" display="block" variant="overline" color="primary.main">New connection</Typography><Typography component="span" display="block" variant="h5">Add API provider</Typography></DialogTitle>
      <DialogContent>
        <Stack spacing={2.25} sx={{ mt: 1 }}>
          <FormControl fullWidth><InputLabel>Provider</InputLabel><Select label="Provider" value={form.provider} onChange={(event) => setForm({ ...initialForm, provider: event.target.value })}>{providers.map((provider) => <MenuItem key={provider.id} value={provider.id}>{provider.name}</MenuItem>)}</Select>{selectedProvider && <FormHelperText>{selectedProvider.description}</FormHelperText>}</FormControl>
          {setup && <Box className="provider-setup-guide">
            <Typography component="h3" variant="subtitle2">How to connect {selectedProvider?.name || 'this provider'}</Typography>
            <Typography variant="caption" color="text.secondary">{setup.title}</Typography>
            <ol>{setup.steps.map((step) => <li key={step}>{step}</li>)}</ol>
            {setup.url && <Button component="a" href={setup.url} target="_blank" rel="noreferrer" size="small" variant="outlined" endIcon={<LaunchRoundedIcon />} aria-label={`${setup.linkLabel} (opens in a new tab)`}>{setup.linkLabel}</Button>}
          </Box>}
          <TextField label="Connection label" value={form.label} onChange={(event) => setForm({ ...form, label: event.target.value })} placeholder="Production" />
          <TextField label={isCustom ? 'Secret / API key' : 'API key'} value={form.api_key} type="password" onChange={(event) => setForm({ ...form, api_key: event.target.value })} placeholder={setup?.keyPlaceholder} helperText={isCustom ? 'Inserted into the auth header template as {api_key}; never put secrets in URLs.' : `Use the ${setup?.title || 'key'} described above.`} />
          <TextField label="Base URL override" value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} placeholder={isCustom ? 'https://api.example.com' : 'Optional — provider default will be used'} required={isCustom} />
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
          {testResult && <Alert severity="success">Test succeeded: {testResult.summary}<br />{(testResult.metrics || []).map((metric) => `${metric.label}: ${metric.value ?? '—'}${metric.unit ? ` ${metric.unit}` : ''}`).join(' · ')}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 3, flexWrap: 'wrap' }}><Button color="inherit" onClick={() => setOpen(false)}>Cancel</Button><Button onClick={testConnection} disabled={testDisabled} startIcon={testing ? <CircularProgress size={16} /> : null}>{testing ? 'Testing…' : 'Test connection'}</Button><Button variant="contained" onClick={submit}>Save provider</Button></DialogActions>
    </Dialog>
  </>
}
