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
  codex: {
    title: 'Codex device login',
    steps: ['Try Start Codex device login first. If OpenAI Cloudflare blocks your Docker/server IP, use Start browser login instead.', 'Browser login opens OpenAI in your browser, then asks you to paste the localhost callback URL from the failed browser redirect.', 'Tokens are exchanged and encrypted by the backend only; access_token and refresh_token are never exposed to browser JavaScript.'],
    url: 'https://chatgpt.com/codex/settings/general#settings/Security',
    linkLabel: 'Open Codex security settings',
    keyPlaceholder: '{"access_token":"…","refresh_token":"…","expires_at":"…","account_id":"…"}',
  },
  openai: {
    title: 'OpenAI organization admin key',
    steps: ['Open your organization settings as an organization owner.', 'Create an Admin API key -- not a project, standard model, or Codex key.', 'Paste the admin key below; organization-level access is required by the Costs API. Personal Codex usage has no API and is not trackable here.'],
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
  const [saving, setSaving] = useState(false)
  const [codexDeviceFlow, setCodexDeviceFlow] = useState(null)
  const [codexBrowserFlow, setCodexBrowserFlow] = useState(null)
  const [codexCallback, setCodexCallback] = useState('')
  const [codexDeviceStatus, setCodexDeviceStatus] = useState('')
  const [codexDeviceBusy, setCodexDeviceBusy] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [testError, setTestError] = useState('')
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
  async function toggleApi(config) { await api.updateConfig(config.id, { is_enabled: !config.is_enabled }); await load() }
  async function toggleUi(config) { await api.updateConfig(config.id, { is_visible: !config.is_visible }); await load() }
  async function moveConfig(configId, direction) {
    const currentIndex = configs.findIndex((config) => config.id === configId)
    const nextIndex = currentIndex + direction
    if (currentIndex < 0 || nextIndex < 0 || nextIndex >= configs.length) return
    const nextConfigs = [...configs]
    const [moved] = nextConfigs.splice(currentIndex, 1)
    nextConfigs.splice(nextIndex, 0, moved)
    setConfigs(nextConfigs)
    try { setConfigs(await api.reorderConfigs(nextConfigs.map((config) => config.id))) }
    catch (err) { setError(err.message); await load() }
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
