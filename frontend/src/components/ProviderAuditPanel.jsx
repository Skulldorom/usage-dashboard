import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Typography,
} from '@mui/material'
import CloseRoundedIcon from '@mui/icons-material/CloseRounded'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import { auditRows, confidenceLabel, hasAuditData, reconciliationWarnings } from '../lib/auditFormat.js'

function AuditRows({ rows }) {
  if (!rows.length) {
    return <Typography variant="body2" color="text.secondary">No audit details available for this provider.</Typography>
  }
  let lastSection = null
  return (
    <Stack spacing={1.5}>
      {rows.map((row, index) => {
        const showSection = row.section !== lastSection
        lastSection = row.section
        return (
          <Box key={`${row.section}-${row.label}-${index}`}>
            {showSection && (
              <Typography variant="overline" color="primary.main" sx={{ display: 'block', mt: index === 0 ? 0 : 1 }}>
                {row.section}
              </Typography>
            )}
            <Box className="usage-stat-row">
              <Typography variant="body2" color="text.secondary">{row.label}</Typography>
              <Typography variant="body2">{row.value}</Typography>
            </Box>
          </Box>
        )
      })}
    </Stack>
  )
}

export default function ProviderAuditPanel({ provider }) {
  const [open, setOpen] = useState(false)
  if (!provider || !hasAuditData(provider)) return null

  const rows = auditRows(provider)
  const warnings = reconciliationWarnings(provider)
  const confidence = provider.confidence || provider.audit?.capacity?.confidence

  return (
    <>
      <Button
        size="small"
        variant="text"
        startIcon={<InfoOutlinedIcon />}
        onClick={() => setOpen(true)}
        aria-label={`Why this number for ${provider.provider}`}
      >
        Why this number?
      </Button>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <InfoOutlinedIcon color="primary" />
            <span>Why this number? — {provider.provider}{provider.label && provider.label !== 'main' ? ` · ${provider.label}` : ''}</span>
          </Stack>
          <IconButton onClick={() => setOpen(false)} aria-label="Close">
            <CloseRoundedIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Box>
              <Typography variant="overline" color="primary.main">Confidence</Typography>
              <Typography variant="body2">{confidenceLabel(confidence)}</Typography>
            </Box>
            {warnings.length > 0 && (
              <Box>
                <Typography variant="overline" color="primary.main">Data quality</Typography>
                <Stack spacing={1} sx={{ mt: 0.5 }}>
                  {warnings.map((warning, index) => (
                    <Alert key={index} severity="warning">{warning}</Alert>
                  ))}
                </Stack>
              </Box>
            )}
            <Card variant="outlined" className="glass-panel">
              <CardContent>
                <AuditRows rows={rows} />
              </CardContent>
            </Card>
            <Typography variant="caption" color="text.secondary">
              Authoritative values come from the highest-priority source (provider-native &gt; snapshot &gt; Hermes &gt; estimated).
              Hermes telemetry is corroborating and is never added to provider-reported totals.
            </Typography>
          </Stack>
        </DialogContent>
      </Dialog>
    </>
  )
}
