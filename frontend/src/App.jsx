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
  return <Box className="brand-mark" aria-hidden="true"><span>U</span><span>D</span></Box>
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
      {!mobile && <div className="sidebar-note"><span className="status-pulse" />Encrypted locally<small>Provider secrets remain encrypted at rest.</small></div>}
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
      <Navigation mobile />
      <Dialog open={authOpen} onClose={() => setAuthOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle><Typography component="span" display="block" variant="overline" color="primary.main">Secure access</Typography><Typography component="span" display="block" variant="h5">Admin authentication</Typography></DialogTitle>
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
