import { useEffect, useState } from 'react'
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
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { api } from '../api.js'
import { LEAVE_UNMAPPED, mappingSummary, observedMetrics, selectValue } from '../lib/providerMappingsFormat.js'

function statusChip(row) {
  if (row.status === 'mapped') return <Chip size="small" color="success" label="Mapped" />
  if (row.status === 'invalid') return <Chip size="small" color="error" label="Invalid" />
  return <Chip size="small" color="warning" variant="outlined" label="Unmapped" />
}

export function ProviderMappingsTable({ data, savingKey, onChange }) {
  if (!data) return null
  if (data.observed.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        No Hermes observations stored yet. Sync the source to discover raw providers.
      </Typography>
    )
  }
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Hermes provider</TableCell>
          <TableCell>Observed metrics</TableCell>
          <TableCell>Last observed</TableCell>
          <TableCell>Maps to</TableCell>
          <TableCell>Status</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {data.observed.map((row) => {
          const hasInvalidTarget =
            row.status === 'invalid' &&
            !data.configured_providers.some((option) => option.provider === row.mapped_to)
          return (
            <TableRow key={row.raw_provider}>
              <TableCell><code>{row.raw_provider}</code></TableCell>
              <TableCell>{observedMetrics(row)}</TableCell>
              <TableCell>{row.last_observed_at ? new Date(row.last_observed_at).toLocaleString() : '—'}</TableCell>
              <TableCell>
                <FormControl size="small" sx={{ minWidth: 190 }} disabled={savingKey === row.raw_provider}>
                  <InputLabel>Provider</InputLabel>
                  <Select
                    value={selectValue(row)}
                    label="Provider"
                    onChange={(event) => onChange(row.raw_provider, event.target.value)}
                  >
                    <MenuItem value={LEAVE_UNMAPPED}>Leave unmapped</MenuItem>
                    {hasInvalidTarget && (
                      <MenuItem value={row.mapped_to} disabled>{row.mapped_to} (unavailable)</MenuItem>
                    )}
                    {data.configured_providers.map((option) => (
                      <MenuItem key={option.provider} value={option.provider}>
                        {option.provider}{option.label && option.label !== 'main' ? ` · ${option.label}` : ''}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </TableCell>
              <TableCell>
                {statusChip(row)}
                {row.reason && (
                  <Typography variant="caption" color="error.main" sx={{ display: 'block' }}>
                    {row.reason}
                  </Typography>
                )}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

export default function ProviderMappingsDialog({ source, onClose }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [savingKey, setSavingKey] = useState(null)
  const [saveError, setSaveError] = useState('')

  useEffect(() => {
    if (!source) return
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      try {
        const result = await api.dataSourceProviderMappings(source.id)
        if (!cancelled) setData(result)
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [source])

  async function handleChange(rawProvider, value) {
    const target = value === LEAVE_UNMAPPED ? null : value
    setSavingKey(rawProvider)
    setSaveError('')
    try {
      const updated = await api.updateDataSourceProviderMappings(source.id, {
        mappings: { [rawProvider]: target },
      })
      setData(updated)
    } catch (err) {
      setSaveError(err.message)
    } finally {
      setSavingKey(null)
    }
  }

  return (
    <Dialog open={Boolean(source)} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Provider mapping — {source?.name || ''}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Map raw Hermes provider identifiers to providers configured in Usage Dashboard. Mapping is an attribution layer — raw identifiers are never rewritten in stored observations.
          </Typography>
          {loading && (
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <CircularProgress size={16} />
              <Typography variant="body2" color="text.secondary">Loading observed providers…</Typography>
            </Stack>
          )}
          {error && <Alert severity="error">{error}</Alert>}
          {data && !error && (
            <>
              <Alert severity={data.unmapped_count ? 'warning' : 'success'}>
                Provider mapping: {mappingSummary(data)}
              </Alert>
              {saveError && <Alert severity="error">{saveError}</Alert>}
              <ProviderMappingsTable data={data} savingKey={savingKey} onChange={handleChange} />
            </>
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 3 }}>
        <Box component="span" sx={{ flexGrow: 1 }} />
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  )
}
