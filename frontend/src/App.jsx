import { useEffect, useState } from "react";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import {
  Alert,
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
} from "@mui/material";
import DashboardRoundedIcon from "@mui/icons-material/DashboardRounded";
import KeyRoundedIcon from "@mui/icons-material/KeyRounded";
import SettingsRoundedIcon from "@mui/icons-material/SettingsRounded";
import DashboardPage from "./pages/DashboardPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import { api, clearAdminToken, getAdminToken, setAdminToken } from "./api.js";
import "./styles.css";

const theme = createTheme({
  palette: {
    mode: "dark",
    primary: {
      main: "#06c8ff",
      light: "#63e3ff",
      dark: "#0095ca",
      contrastText: "#031018",
    },
    secondary: { main: "#a855f7", light: "#c084fc" },
    success: { main: "#38e6a1" },
    warning: { main: "#ffbf69" },
    error: { main: "#ff6685" },
    background: { default: "#08050f", paper: "#15101f" },
    text: { primary: "#fbf9ff", secondary: "#aaa2b9" },
    divider: "rgba(255, 255, 255, 0.09)",
  },
  shape: { borderRadius: 18 },
  typography: {
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    h1: { fontWeight: 800, letterSpacing: "-0.045em" },
    h2: { fontWeight: 800, letterSpacing: "-0.04em" },
    h3: { fontWeight: 750, letterSpacing: "-0.035em" },
    h4: { fontWeight: 750, letterSpacing: "-0.03em" },
    h5: { fontWeight: 700, letterSpacing: "-0.02em" },
    h6: { fontWeight: 700, letterSpacing: "-0.015em" },
    button: { fontWeight: 750, letterSpacing: "0.01em", textTransform: "none" },
    overline: { fontWeight: 800, letterSpacing: "0.14em" },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: 12, minHeight: 42, paddingInline: 18 },
        containedPrimary: {
          background: "linear-gradient(135deg, #06c8ff 0%, #69e7ff 100%)",
          boxShadow: "0 10px 30px rgba(6, 200, 255, 0.2)",
          "&:hover": {
            background: "linear-gradient(135deg, #37d4ff 0%, #8eeeff 100%)",
            boxShadow: "0 12px 38px rgba(6, 200, 255, 0.28)",
          },
        },
        outlined: {
          borderColor: "rgba(255,255,255,.14)",
          background: "rgba(255,255,255,.025)",
        },
      },
    },
    MuiCard: { styleOverrides: { root: { backgroundImage: "none" } } },
    MuiDialog: {
      styleOverrides: {
        paper: {
          backgroundImage:
            "linear-gradient(145deg, rgba(31,22,47,.98), rgba(12,9,18,.98))",
          border: "1px solid rgba(255,255,255,.1)",
          boxShadow: "0 30px 100px rgba(0,0,0,.65)",
        },
      },
    },
    MuiTextField: { defaultProps: { variant: "outlined" } },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          background: "rgba(3, 2, 8, .35)",
          "& fieldset": { borderColor: "rgba(255,255,255,.12)" },
          "&:hover fieldset": { borderColor: "rgba(6,200,255,.45)" },
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          height: 7,
          borderRadius: 20,
          backgroundColor: "rgba(255,255,255,.07)",
        },
        bar: {
          borderRadius: 20,
          background: "linear-gradient(90deg, #7557ff, #06c8ff)",
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: { borderRadius: 14, border: "1px solid rgba(255,255,255,.09)" },
      },
    },
  },
});

function BrandMark() {
  return (
    <Box
      component="img"
      className="brand-mark"
      src="/logo.svg"
      alt=""
      aria-hidden="true"
    />
  );
}

function GitHubLogo() {
  return (
    <svg
      className="github-logo"
      viewBox="0 0 16 16"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82A7.57 7.57 0 0 1 8 3.86c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"
      />
    </svg>
  );
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
          {[
            [170, 45],
            [320, 210],
            [520, 85],
            [690, 245],
            [905, 55],
            [195, 335],
            [400, 610],
            [575, 350],
            [805, 570],
            [1015, 300],
          ].map(([x, y]) => (
            <circle key={`${x}-${y}`} cx={x} cy={y} r="3" />
          ))}
        </g>
      </svg>
    </div>
  );
}

const navItems = [
  { to: "/", label: "Dashboard", icon: <DashboardRoundedIcon /> },
  { to: "/settings", label: "Settings", icon: <SettingsRoundedIcon /> },
];

function SidebarActions() {
  return (
    <div className="sidebar-actions" aria-label="Project shortcuts">
      <a
        className="sidebar-action sidebar-action-wide"
        href="https://github.com/Skulldorom/usage-dashboard"
        target="_blank"
        rel="noreferrer"
        aria-label="Open Usage Dashboard GitHub project"
        title="Open GitHub"
      >
        <GitHubLogo />
        <span>GitHub Repository</span>
      </a>
    </div>
  );
}

function Navigation({ mobile = false, isAuthenticated = true }) {
  return (
    <nav
      className={mobile ? "mobile-navigation" : "side-navigation"}
      aria-label="Primary navigation"
    >
      {!mobile && (
        <div className="brand-lockup">
          <BrandMark />
          <div>
            <strong>Usage</strong>
            <span>Command Center</span>
          </div>
        </div>
      )}
      {isAuthenticated && (
        <div className="nav-links">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            >
              {item.icon}
              <span>{item.label}</span>
            </NavLink>
          ))}
        </div>
      )}
      {!mobile && <SidebarActions />}
      {!mobile && <span className="sidebar-copyright">© {new Date().getFullYear()} Skulldorom</span>}
    </nav>
  );
}

function AuthDialog({ open, authStatus, onAuthenticated, onClose }) {
  const [mode, setMode] = useState("login");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const setupRequired = authStatus?.setup_required;
  const activeMode = setupRequired ? "setup" : mode;
  const needsCode = activeMode === "setup" || activeMode === "reset";
  const needsConfirm = activeMode === "setup" || activeMode === "reset";

  useEffect(() => {
    if (setupRequired) setMode("setup");
  }, [setupRequired]);

  function resetForm(nextMode) {
    setMode(nextMode);
    setCode("");
    setPassword("");
    setConfirmPassword("");
    setError("");
    setMessage("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    if (needsConfirm && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      const payload = needsCode ? { code, password } : { password };
      const result = activeMode === "setup"
        ? await api.setupAuth(payload)
        : activeMode === "reset"
          ? await api.completePasswordReset(payload)
          : await api.login(payload);
      setAdminToken(result.access_token);
      onAuthenticated();
    } catch (err) {
      setError(err.message || "Authentication failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function requestResetCode() {
    setError("");
    setMessage("");
    setSubmitting(true);
    try {
      await api.requestPasswordReset();
      resetForm("reset");
      setMessage("Reset code generated. Check the backend logs, then enter it below.");
    } catch (err) {
      setError(err.message || "Could not request a reset code.");
    } finally {
      setSubmitting(false);
    }
  }

  const title = activeMode === "setup" ? "Create admin password" : activeMode === "reset" ? "Reset admin password" : "Admin login";
  const helper = activeMode === "setup"
    ? "A one-time setup code has been printed in the backend logs. Use it to create the dashboard password."
    : activeMode === "reset"
      ? "Enter the reset code from the backend logs and choose a new password."
      : "Enter the dashboard admin password.";

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <Box component="form" onSubmit={handleSubmit}>
        <DialogTitle>
          <Stack spacing={0.75}>
            <Typography component="span" display="block" variant="overline" color="primary.main">
              Secure access
            </Typography>
            <Typography component="span" display="block" variant="h5">
              {title}
            </Typography>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2}>
            <Typography color="text.secondary">{helper}</Typography>
            {message && <Alert severity="info">{message}</Alert>}
            {error && <Alert severity="error">{error}</Alert>}
            {needsCode && (
              <TextField
                autoFocus
                fullWidth
                label={activeMode === "setup" ? "Setup code" : "Reset code"}
                value={code}
                onChange={(event) => setCode(event.target.value)}
                required
              />
            )}
            <TextField
              autoFocus={!needsCode}
              fullWidth
              label={activeMode === "login" ? "Password" : "New password"}
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              helperText="Minimum 12 characters. Stored as a salted PBKDF2 hash on the backend."
              required
            />
            {needsConfirm && (
              <TextField
                fullWidth
                label="Confirm password"
                type="password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                required
              />
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          {!setupRequired && activeMode === "login" && (
            <Button color="inherit" onClick={requestResetCode} disabled={submitting}>
              Reset password
            </Button>
          )}
          {!setupRequired && activeMode === "reset" && (
            <Button color="inherit" onClick={() => resetForm("login")} disabled={submitting}>
              Back to login
            </Button>
          )}
          <Button variant="contained" type="submit" disabled={submitting}>
            {activeMode === "login" ? "Log in" : activeMode === "setup" ? "Create password" : "Reset password"}
          </Button>
        </DialogActions>
      </Box>
    </Dialog>
  );
}

function LandingPage({ authStatus, onLogin }) {
  const setupRequired = authStatus?.setup_required;
  return (
    <section className="landing-page">
      <div className="landing-hero glass-panel">
        <div className="landing-orb" aria-hidden="true" />
        <Stack spacing={2.4} className="landing-copy">
          <Typography className="page-kicker" component="span">
            Private telemetry command center
          </Typography>
          <Typography variant="h1">Usage intelligence, locked down.</Typography>
          <Typography color="text.secondary" className="landing-description">
            Monitor provider balances, polling health, and Homepage widget data from one self-hosted dashboard. Sign in to unlock sensitive API usage and provider configuration.
          </Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
            <Button variant="contained" size="large" startIcon={<KeyRoundedIcon />} onClick={onLogin}>
              {setupRequired ? "Create admin password" : "Log in to dashboard"}
            </Button>
            <Button variant="outlined" color="inherit" size="large" href="https://github.com/Skulldorom/usage-dashboard" target="_blank" rel="noreferrer">
              View project
            </Button>
          </Stack>
          <div className="landing-hint">
            {setupRequired
              ? "First run detected. Grab the one-time setup code from the backend logs."
              : "Password resets are protected by one-time codes printed in backend logs."}
          </div>
        </Stack>
        <div className="landing-card-stack" aria-hidden="true">
          <div className="landing-stat-card primary">
            <span>Access</span>
            <strong>Secured</strong>
          </div>
          <div className="landing-stat-card">
            <span>Provider telemetry</span>
            <strong>Encrypted</strong>
          </div>
          <div className="landing-stat-card">
            <span>Recovery</span>
            <strong>Log codes</strong>
          </div>
        </div>
      </div>
    </section>
  );
}

function Shell() {
  const [authOpen, setAuthOpen] = useState(!getAdminToken());
  const [authStatus, setAuthStatus] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(Boolean(getAdminToken()));

  async function loadAuthStatus() {
    setAuthLoading(true);
    try {
      const status = await api.authStatus();
      setAuthStatus(status);
      if (status.setup_required) {
        setIsAuthenticated(false);
        setAuthOpen(true);
      } else if (!getAdminToken()) {
        setIsAuthenticated(false);
        setAuthOpen(false);
      } else {
        setIsAuthenticated(true);
      }
    } catch {
      if (!getAdminToken()) {
        setIsAuthenticated(false);
        setAuthOpen(false);
      }
    } finally {
      setAuthLoading(false);
    }
  }

  useEffect(() => {
    loadAuthStatus();
  }, []);

  async function logout() {
    try {
      await api.logout();
    } catch {
      // Token may already be expired; clear local state anyway.
    }
    clearAdminToken();
    setIsAuthenticated(false);
    setAuthOpen(false);
  }

  return (
    <Box className="app-shell">
      <CssBaseline />
      <NetworkBackdrop />
      <aside className="sidebar">
        <Navigation isAuthenticated={isAuthenticated} />
      </aside>
      <header className="topbar">
        <div className="mobile-brand">
          <BrandMark />
          <strong>Usage</strong>
        </div>
        <div className="topbar-context">
          <span className="eyebrow">API OPERATIONS</span>
          <span className="topbar-divider" />
          <span>{isAuthenticated ? "Live provider telemetry" : authStatus?.setup_required ? "Password setup required" : "Authentication required"}</span>
        </div>
        <Stack direction="row" spacing={1}>
          {!isAuthenticated && (
            <Button
              className="token-button"
              variant="outlined"
              color="inherit"
              startIcon={<KeyRoundedIcon />}
              onClick={() => setAuthOpen(true)}
            >
              {authStatus?.setup_required ? "Set password" : "Admin login"}
            </Button>
          )}
          {isAuthenticated && (
            <Button className="token-button" variant="outlined" color="inherit" onClick={logout}>
              Log out
            </Button>
          )}
        </Stack>
      </header>
      <main className="main-content">
        {authLoading ? (
          <div className="loading-state"><Typography color="text.secondary">Checking authentication…</Typography></div>
        ) : !isAuthenticated ? (
          <LandingPage authStatus={authStatus} onLogin={() => setAuthOpen(true)} />
        ) : (
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        )}
      </main>
      {isAuthenticated && <Navigation mobile isAuthenticated={isAuthenticated} />}
      <AuthDialog
        open={authOpen}
        authStatus={authStatus}
        onAuthenticated={() => {
          setIsAuthenticated(true);
          setAuthOpen(false);
          loadAuthStatus();
        }}
        onClose={() => {
          if (isAuthenticated && !authStatus?.setup_required) setAuthOpen(false);
        }}
      />
    </Box>
  );
}

export default function App() {
  return (
    <ThemeProvider theme={theme}>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </ThemeProvider>
  );
}
