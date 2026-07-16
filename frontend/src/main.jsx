import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import { useState } from 'react'
import { AppBar, Box, Button, CssBaseline, Dialog, DialogActions, DialogContent, DialogTitle, Divider, Drawer, List, ListItemButton, ListItemIcon, ListItemText, TextField, ThemeProvider, Toolbar, Typography, createTheme } from '@mui/material'
import DashboardIcon from '@mui/icons-material/Dashboard'
import SettingsIcon from '@mui/icons-material/Settings'
import DashboardPage from './pages/DashboardPage.jsx'
import SettingsPage from './pages/SettingsPage.jsx'
import { getAdminToken, setAdminToken } from './api.js'
import './styles.css'
const drawerWidth = 250
const theme = createTheme({ palette: { mode: 'dark', primary: { main: '#8ab4ff' }, background: { default: '#090b10', paper: '#111722' } }, shape: { borderRadius: 14 }, typography: { fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif' } })
function Shell() {
  const [authOpen, setAuthOpen] = useState(!getAdminToken())
  const [token, setToken] = useState(getAdminToken())
  function saveToken() { setAdminToken(token); setAuthOpen(false) }
  return <Box sx={{ display: 'flex' }}><CssBaseline /><AppBar position="fixed" sx={{ zIndex: (t) => t.zIndex.drawer + 1, backgroundImage: 'linear-gradient(90deg,#111722,#151027)' }}><Toolbar><Typography variant="h6" noWrap sx={{ flexGrow: 1 }}>Usage Dashboard</Typography><Button color="inherit" onClick={() => setAuthOpen(true)}>Admin token</Button></Toolbar></AppBar><Drawer variant="permanent" sx={{ width: drawerWidth, [`& .MuiDrawer-paper`]: { width: drawerWidth, boxSizing: 'border-box' } }}><Toolbar /><Box sx={{ overflow: 'auto' }}><List><ListItemButton component={NavLink} to="/" end><ListItemIcon><DashboardIcon /></ListItemIcon><ListItemText primary="Dashboard" /></ListItemButton><ListItemButton component={NavLink} to="/settings"><ListItemIcon><SettingsIcon /></ListItemIcon><ListItemText primary="Settings" /></ListItemButton></List><Divider /><Typography variant="caption" color="text.secondary" sx={{ display: 'block', p: 2 }}>Provider secrets stay encrypted at rest. Enter the admin token configured on the backend to access sensitive dashboard data.</Typography></Box></Drawer><Box component="main" sx={{ flexGrow: 1, p: 3, minHeight: '100vh' }}><Toolbar /><Routes><Route path="/" element={<DashboardPage />} /><Route path="/settings" element={<SettingsPage />} /></Routes></Box><Dialog open={authOpen} onClose={() => setAuthOpen(false)} fullWidth maxWidth="xs"><DialogTitle>Admin authentication</DialogTitle><DialogContent><TextField autoFocus fullWidth margin="dense" label="Admin token" type="password" value={token} onChange={(e) => setToken(e.target.value)} helperText="Stored in this browser and sent as a Bearer token." /></DialogContent><DialogActions><Button onClick={() => { setToken(''); setAdminToken('') }}>Clear</Button><Button variant="contained" onClick={saveToken}>Save</Button></DialogActions></Dialog></Box>
}
createRoot(document.getElementById('root')).render(<React.StrictMode><ThemeProvider theme={theme}><BrowserRouter><Shell /></BrowserRouter></ThemeProvider></React.StrictMode>)
