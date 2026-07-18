import { useState } from 'react'
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import {
  Box,
  Button,
  CssBaseline,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  ThemeProvider,
  Typography,
  createTheme,
} from '@mui/material'
import DashboardRoundedIcon from '@mui/icons-material/DashboardRounded'
import ContentCopyRoundedIcon from '@mui/icons-material/ContentCopyRounded'
import KeyRoundedIcon from '@mui/icons-material/KeyRounded'
import SettingsRoundedIcon from '@mui/icons-material/SettingsRounded'
import DashboardPage from './pages/DashboardPage.jsx'
import SettingsPage from './pages/SettingsPage.jsx'
import { getAdminToken, setAdminToken } from './api.js'
import './styles.css'

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#06c8ff', light: '#63e3ff', dark: '#0095ca', contrastText: '#031018' },
    secondary: { main: '#a855f7', light: '#c084fc' },
    success: { main: '#38e6a1' },
    warning: { main: '#ffbf69' },
    error: { main: '#ff6685' },
    background: { default: '#08050f', paper: '#15101f' },
    text: { primary: '#fbf9ff', secondary: '#aaa2b9' },
    divider: 'rgba(255, 255, 255, 0.09)',
  },
  shape: { borderRadius: 18 },
  typography: {
    fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    h1: { fontWeight: 800, letterSpacing: '-0.045em' },
    h2: { fontWeight: 800, letterSpacing: '-0.04em' },
    h3: { fontWeight: 750, letterSpacing: '-0.035em' },
    h4: { fontWeight: 750, letterSpacing: '-0.03em' },
    h5: { fontWeight: 700, letterSpacing: '-0.02em' },
    h6: { fontWeight: 700, letterSpacing: '-0.015em' },
    button: { fontWeight: 750, letterSpacing: '0.01em', textTransform: 'none' },
    overline: { fontWeight: 800, letterSpacing: '0.14em' },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: 12, minHeight: 42, paddingInline: 18 },
        containedPrimary: {
          background: 'linear-gradient(135deg, #06c8ff 0%, #69e7ff 100%)',
          boxShadow: '0 10px 30px rgba(6, 200, 255, 0.2)',
          '&:hover': { background: 'linear-gradient(135deg, #37d4ff 0%, #8eeeff 100%)', boxShadow: '0 12px 38px rgba(6, 200, 255, 0.28)' },
        },
        outlined: { borderColor: 'rgba(255,255,255,.14)', background: 'rgba(255,255,255,.025)' },
      },
    },
    MuiCard: { styleOverrides: { root: { backgroundImage: 'none' } } },
    MuiDialog: { styleOverrides: { paper: { backgroundImage: 'linear-gradient(145deg, rgba(31,22,47,.98), rgba(12,9,18,.98))', border: '1px solid rgba(255,255,255,.1)', boxShadow: '0 30px 100px rgba(0,0,0,.65)' } } },
    MuiTextField: { defaultProps: { variant: 'outlined' } },
    MuiOutlinedInput: { styleOverrides: { root: { background: 'rgba(3, 2, 8, .35)', '& fieldset': { borderColor: 'rgba(255,255,255,.12)' }, '&:hover fieldset': { borderColor: 'rgba(6,200,255,.45)' } } } },
    MuiLinearProgress: { styleOverrides: { root: { height: 7, borderRadius: 20, backgroundColor: 'rgba(255,255,255,.07)' }, bar: { borderRadius: 20, background: 'linear-gradient(90deg, #7557ff, #06c8ff)' } } },
    MuiAlert: { styleOverrides: { root: { borderRadius: 14, border: '1px solid rgba(255,255,255,.09)' } } },
  },
})

function BrandMark() {
  return <Box component="img" className="brand-mark" src="/logo.svg" alt="" aria-hidden="true" />
}


function GitHubLogo() {
  return (
    <svg className="github-logo" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82A7.57 7.57 0 0 1 8 3.86c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  )
}

function NetworkBackdrop() {
  return (
    <div className="network-backdrop" aria-hidden="true">
      <svg viewBox="0 0 1200 760" preserveAspectRatio="xMidYMid slice">
        <g className="network-lines">
          <path d="M-20 180 170 45 320 210 520 85 690 245 905 55 1220 190" />
          <path d="M15 545 195 335 400 610 575 350 805 570 1015 300 1225 515" />
          <path d="M170 45 195 335 320 210 400 610 520 85 575 350 690 245 805 570 905 55 1015 300" />
          <path d="M-20 180 195 335 520 85 805 570 1220 190M15 545 320 210 575 350 905 55 1225 515" />
          <path d="M170 45 400 610M320 210 690 245M520 85 1015 300M575 350 1220 190" />
        </g>
        <g className="network-nodes">
          {[[170,45],[320,210],[520,85],[690,245],[905,55],[195,335],[400,610],[575,350],[805,570],[1015,300]].map(([x,y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r="3" />)}
        </g>
      </svg>
    </div>
  )
}

const navItems = [
  { to: '/', label: 'Dashboard', icon: <DashboardRoundedIcon /> },
  { to: '/settings', label: 'Settings', icon: <SettingsRoundedIcon /> },
]

function SidebarActions() {
  const [copyStatus, setCopyStatus] = useState('Copy Homepage API URL')

  async function copyHomepageUrl() {
    const url = `${window.location.origin || ''}/api/v1/homepage`
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url)
      } else {
        window.prompt('Copy Homepage API URL', url)
      }
      setCopyStatus('Copied Homepage API URL')
    } catch {
      window.prompt('Copy Homepage API URL', url)
      setCopyStatus('Copy Homepage API URL')
    }
  }

  return (
    <div className="sidebar-actions" aria-label="Project shortcuts">
      <button type="button" className="sidebar-action" onClick={copyHomepageUrl} aria-label={copyStatus} title={copyStatus}>
        <ContentCopyRoundedIcon />
      </button>
      <a className="sidebar-action" href="https://github.com/Skulldorom/usage-dashboard" target="_blank" rel="noreferrer" aria-label="Open Usage Dashboard GitHub project" title="Open GitHub">
        <GitHubLogo />
      </a>
    </div>
  )
}

function Navigation({ mobile = false }) {
  return (
    <nav className={mobile ? 'mobile-navigation' : 'side-navigation'} aria-label="Primary navigation">
      {!mobile && <div className="brand-lockup"><BrandMark /><div><strong>Usage</strong><span>Command Center</span></div></div>}
      <div className="nav-links">
        {navItems.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === '/'} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            {item.icon}<span>{item.label}</span>
          </NavLink>
        ))}
      </div>
      {!mobile && <SidebarActions />}
    </nav>
  )
}

function Shell() {
  const [authOpen, setAuthOpen] = useState(!getAdminToken())
  const [token, setToken] = useState(getAdminToken())

  function saveToken() {
    setAdminToken(token)
    setAuthOpen(false)
  }

  return (
    <Box className="app-shell">
      <CssBaseline />
      <NetworkBackdrop />
      <aside className="sidebar"><Navigation /></aside>
      <header className="topbar">
        <div className="mobile-brand"><BrandMark /><strong>Usage</strong></div>
        <div className="topbar-context"><span className="eyebrow">API OPERATIONS</span><span className="topbar-divider" /><span>Live provider telemetry</span></div>
        <Button className="token-button" variant="outlined" color="inherit" startIcon={<KeyRoundedIcon />} onClick={() => setAuthOpen(true)}>Admin token</Button>
      </header>
      <main className="main-content"><Routes><Route path="/" element={<DashboardPage />} /><Route path="/settings" element={<SettingsPage />} /></Routes></main>
      <footer className="app-footer">
        <span>© 2026 Skulldorom</span>
        <a className="github-project-link" href="https://github.com/Skulldorom/usage-dashboard" target="_blank" rel="noreferrer" aria-label="Open Usage Dashboard GitHub project">
          <GitHubLogo />
        </a>
      </footer>
      <Navigation mobile />
      <Dialog open={authOpen} onClose={() => setAuthOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle><Stack spacing={0.75}><Typography component="span" display="block" variant="overline" color="primary.main">Secure access</Typography><Typography component="span" display="block" variant="h5">Admin authentication</Typography></Stack></DialogTitle>
        <DialogContent>
          <Typography color="text.secondary" sx={{ mb: 2 }}>Authenticate this browser to load sensitive usage and provider data.</Typography>
          <TextField autoFocus fullWidth label="Admin token" type="password" value={token} onChange={(event) => setToken(event.target.value)} helperText="Stored in this browser and sent as a Bearer token." />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button color="inherit" onClick={() => { setToken(''); setAdminToken('') }}>Clear</Button>
          <Button variant="contained" onClick={saveToken}>Authenticate</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default function App() {
  return <ThemeProvider theme={theme}><BrowserRouter><Shell /></BrowserRouter></ThemeProvider>
}
