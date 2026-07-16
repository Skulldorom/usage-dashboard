import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, FormHelperText, InputLabel, MenuItem, Select, Stack, Switch, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography } from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import { api } from '../api.js'

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
  const selectedProvider = useMemo(() => providers.find((p) => p.id === form.provider), [providers, form.provider])
  const isCustom = form.provider === 'custom_http'
  const isAnthropic = form.provider === 'anthropic'

  const load = useCallback(async () => {
    try {
      const [p, c] = await Promise.all([api.providers(), api.configs()])
      setProviders(p)
      setConfigs(c)
      setForm((current) => {
        if (p.length && !p.some((provider) => provider.id === current.provider)) return { ...initialForm, provider: p[0].id }
        return current
      })
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => { load() }, [load])

  function payloadFromForm() {
    const payload = {
      provider: form.provider,
      label: form.label,
      api_key: form.api_key,
      base_url: form.base_url || null,
      is_enabled: true,
      extra: {},
    }
    if (isCustom) {
      payload.extra = {
        method: form.custom_method,
        path: form.custom_path,
        auth_header_name: form.custom_auth_header_name || 'Authorization',
        auth_header_template: form.custom_auth_header_template || 'Bearer {api_key}',
        metrics: [{
          label: form.custom_metric_label,
          path: form.custom_metric_path,
          unit: form.custom_metric_unit || null,
          maximum_path: form.custom_metric_maximum_path || null,
        }],
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
    } catch (err) {
      setError(err.message)
    }
  }

  async function remove(id) { await api.deleteConfig(id); await load() }
  async function toggle(cfg) { await api.updateConfig(cfg.id, { is_enabled: !cfg.is_enabled }); await load() }

  return (
    <Stack gap={3}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Box>
          <Typography variant="h4">Settings</Typography>
          <Typography color="text.secondary">Add Firecrawl, DeepSeek, OpenAI/Codex, Anthropic, OpenRouter, or custom HTTP credentials. Keys are encrypted before storage.</Typography>
        </Box>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpen(true)}>Add provider</Button>
      </Stack>
      {error && <Alert severity="error">{error}</Alert>}
      <Table>
        <TableHead><TableRow><TableCell>Enabled</TableCell><TableCell>Provider</TableCell><TableCell>Label</TableCell><TableCell>API key</TableCell><TableCell>Base URL</TableCell><TableCell align="right">Actions</TableCell></TableRow></TableHead>
        <TableBody>{configs.map((cfg) => <TableRow key={cfg.id}><TableCell><Switch checked={cfg.is_enabled} onChange={() => toggle(cfg)} /></TableCell><TableCell>{cfg.provider}</TableCell><TableCell>{cfg.label}</TableCell><TableCell>{cfg.api_key_masked}</TableCell><TableCell>{cfg.base_url || 'default'}</TableCell><TableCell align="right"><Button color="error" startIcon={<DeleteIcon />} onClick={() => remove(cfg.id)}>Remove</Button></TableCell></TableRow>)}</TableBody>
      </Table>
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Add API provider</DialogTitle>
        <DialogContent>
          <Stack gap={2} sx={{ mt: 1 }}>
            <FormControl fullWidth>
              <InputLabel>Provider</InputLabel>
              <Select label="Provider" value={form.provider} onChange={(e) => setForm({ ...initialForm, provider: e.target.value })}>
                {providers.map((p) => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}
              </Select>
              {selectedProvider && <FormHelperText>{selectedProvider.description}</FormHelperText>}
            </FormControl>
            {isAnthropic && <Alert severity="info">Anthropic usage requires an Admin API key from Console → Settings → Organization → Admin API Keys. A regular Claude inference key will just sit there and sulk.</Alert>}
            <TextField label="Label" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="main" />
            <TextField label={isCustom ? 'Secret / API key' : 'API key'} value={form.api_key} type="password" onChange={(e) => setForm({ ...form, api_key: e.target.value })} helperText={isCustom ? 'Inserted into the auth header template as {api_key}; do not put secrets in URLs.' : ''} />
            <TextField label="Base URL override" value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder={isCustom ? 'https://api.example.com' : 'Optional'} required={isCustom} />
            {isCustom && (
              <Stack gap={2}>
                <FormControl fullWidth>
                  <InputLabel>HTTP method</InputLabel>
                  <Select label="HTTP method" value={form.custom_method} onChange={(e) => setForm({ ...form, custom_method: e.target.value })}>
                    <MenuItem value="GET">GET</MenuItem>
                    <MenuItem value="POST">POST</MenuItem>
                  </Select>
                </FormControl>
                <TextField label="Path" value={form.custom_path} onChange={(e) => setForm({ ...form, custom_path: e.target.value })} placeholder="/v1/billing" required />
                <TextField label="Auth header name" value={form.custom_auth_header_name} onChange={(e) => setForm({ ...form, custom_auth_header_name: e.target.value })} />
                <TextField label="Auth header template" value={form.custom_auth_header_template} onChange={(e) => setForm({ ...form, custom_auth_header_template: e.target.value })} helperText="Use {api_key} where the encrypted secret should be inserted." />
                <Typography variant="subtitle2">Metric extraction</Typography>
                <TextField label="Metric label" value={form.custom_metric_label} onChange={(e) => setForm({ ...form, custom_metric_label: e.target.value })} />
                <TextField label="JSON path" value={form.custom_metric_path} onChange={(e) => setForm({ ...form, custom_metric_path: e.target.value })} helperText="Supports simple paths like $.credits.remaining and $.items[0].usage." />
                <TextField label="Unit" value={form.custom_metric_unit} onChange={(e) => setForm({ ...form, custom_metric_unit: e.target.value })} />
                <TextField label="Maximum JSON path (optional)" value={form.custom_metric_maximum_path} onChange={(e) => setForm({ ...form, custom_metric_maximum_path: e.target.value })} />
              </Stack>
            )}
          </Stack>
        </DialogContent>
        <DialogActions><Button onClick={() => setOpen(false)}>Cancel</Button><Button variant="contained" onClick={submit}>Save</Button></DialogActions>
      </Dialog>
    </Stack>
  )
}
