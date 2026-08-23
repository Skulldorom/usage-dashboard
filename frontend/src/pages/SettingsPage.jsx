import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  FormGroup,
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
} from "@mui/material";
import AddRoundedIcon from "@mui/icons-material/AddRounded";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import DeleteOutlineRoundedIcon from "@mui/icons-material/DeleteOutlineRounded";
import DragIndicatorRoundedIcon from "@mui/icons-material/DragIndicatorRounded";
import ExtensionRoundedIcon from "@mui/icons-material/ExtensionRounded";
import HubRoundedIcon from "@mui/icons-material/HubRounded";
import KeyRoundedIcon from "@mui/icons-material/KeyRounded";
import LaunchRoundedIcon from "@mui/icons-material/LaunchRounded";
import NotificationsActiveRoundedIcon from "@mui/icons-material/NotificationsActiveRounded";
import { api } from "../api.js";
import DataSourcesSection from "../components/DataSourcesSection.jsx";
import ProviderIcon from "../components/ProviderIcon.jsx";
import { formatThresholdRule } from "../lib/usageFormat.js";
import {
  extensionBridge,
  extensionSupportsOneClickSetup,
} from "../lib/extensionBridge.js";
import { homepageYaml } from "../lib/homepageYaml.js";

const PROVIDER_SETUP = {
  firecrawl: {
    title: "Firecrawl API key",
    steps: [
      "Sign in to the Firecrawl dashboard.",
      "Open API Keys and create or copy a key beginning with fc-.",
      "Paste that key below; it can read the team token and credit usage endpoints.",
    ],
    url: "https://www.firecrawl.dev/app/api-keys",
    linkLabel: "Open Firecrawl API Keys",
    keyPlaceholder: "fc-…",
  },
  deepseek: {
    title: "DeepSeek API key",
    steps: [
      "Sign in to the DeepSeek Platform.",
      "Create an API key from the API Keys page.",
      "Make sure the account has billing credit; the dashboard reads the balance attached to this key.",
    ],
    url: "https://platform.deepseek.com/api_keys",
    linkLabel: "Open DeepSeek API Keys",
    keyPlaceholder: "sk-…",
  },
  codex: {
    title: "Codex device login",
    steps: [
      "Try Start Codex device login first. If OpenAI Cloudflare blocks your Docker/server IP, use Start browser login instead.",
      "Browser login opens OpenAI in your browser, then asks you to paste the localhost callback URL from the failed browser redirect.",
      "Tokens are exchanged and encrypted by the backend only; access_token and refresh_token are never exposed to browser JavaScript.",
    ],
    url: "https://chatgpt.com/codex/settings/general#settings/Security",
    linkLabel: "Open Codex security settings",
    keyPlaceholder:
      '{"access_token":"…","refresh_token":"…","expires_at":"…","account_id":"…"}',
  },
  openai: {
    title: "OpenAI organization admin key",
    steps: [
      "Open your organization settings as an organization owner.",
      "Create an Admin API key - not a project, standard model, or Codex key.",
      "Paste the admin key below; organization-level access is required by the Costs API. Personal Codex usage has no API and is not trackable here.",
    ],
    url: "https://platform.openai.com/settings/organization/admin-keys",
    linkLabel: "Open OpenAI Admin Keys",
    keyPlaceholder: "sk-admin-…",
  },
  anthropic: {
    title: "Anthropic Admin API key",
    steps: [
      "Use a Claude Platform organization account; the Admin API is unavailable to individual accounts.",
      "As an organization admin, open Settings > Admin keys.",
      "Create and paste an Admin API key beginning with sk-ant-admin. A normal inference key cannot read usage reports.",
    ],
    url: "https://platform.claude.com/settings/admin-keys",
    linkLabel: "Open Anthropic Admin keys",
    keyPlaceholder: "sk-ant-admin…",
  },
  openrouter: {
    title: "OpenRouter API key",
    steps: [
      "Sign in to OpenRouter and open Keys.",
      "Create a standard API key and optionally give it a credit limit.",
      "Paste the key below; the dashboard reports usage and the remaining configured limit.",
    ],
    url: "https://openrouter.ai/keys",
    linkLabel: "Open OpenRouter Keys",
    keyPlaceholder: "sk-or-v1-…",
  },
  custom_http: {
    title: "Custom JSON endpoint",
    steps: [
      "Choose an HTTP endpoint that returns JSON.",
      "Enter its base URL and relative path, then configure the required authentication header.",
      "Provide a JSON path for the metric to display. Use Test connection before saving.",
    ],
    keyPlaceholder: "Secret inserted into the auth header",
  },
};

const API_TOKEN_SCOPES = [
  {
    id: "usage:read",
    label: "Usage read",
    help: "Read current usage cards and summaries.",
  },
  {
    id: "poll:write",
    label: "Poll write",
    help: "Trigger all-provider or single-provider refreshes.",
  },
  {
    id: "configs:read",
    label: "Configs read",
    help: "Read provider labels, order, visibility, and metadata.",
  },
  {
    id: "history:read",
    label: "History read",
    help: "Read per-provider usage history for charts.",
  },
];

const EXTENSION_DEFAULT_SCOPES = ["usage:read", "poll:write", "configs:read"];
const HOMEPAGE_DEFAULT_SCOPES = ["usage:read"];

const initialApiTokenForm = {
  name: "Chrome / Brave extension",
  scopes: [...EXTENSION_DEFAULT_SCOPES],
  expires_at: "",
};

const initialGenericApiTokenForm = {
  name: "Integration token",
  scopes: ["usage:read"],
  expires_at: "",
};

const initialHomepageForm = {
  dashboardUrl: "",
  refreshInterval: "300000",
  displayMode: "dynamic-list",
  authMode: "bearer",
  token: "",
  includeToken: false,
};

const initialHomepageTokenForm = {
  name: "Homepage widget",
  expires_at: "",
};

const EXTENSION_CONNECT_MESSAGES = {
  checking: {
    severity: "info",
    text: "Checking for a compatible extension before creating a token…",
  },
  "requesting-permission": {
    severity: "info",
    text: "Requesting browser permission for this dashboard before creating a token…",
  },
  "creating-token": {
    severity: "info",
    text: "Extension found. Creating a scoped token…",
  },
  configuring: {
    severity: "info",
    text: "Sending the token to the extension…",
  },
  connected: {
    severity: "success",
    text: "Extension connected. The scoped token was saved in the extension.",
  },
  "connected-degraded": {
    severity: "warning",
    text: "Extension connected, but the dashboard could not be reached yet. The pairing was kept so you can retry from the extension.",
  },
  "not-installed": {
    severity: "warning",
    text: "No compatible extension responded. Install or load the extension, or use manual setup below.",
  },
  timeout: {
    severity: "warning",
    text: "The extension did not respond in time. Manual setup is still available below.",
  },
  "incompatible-protocol": {
    severity: "warning",
    text: "The installed extension uses an incompatible setup protocol. Update the extension, then try again.",
  },
  "unsupported-browser": {
    severity: "warning",
    text: "This browser does not expose a supported extension messaging transport. Use manual setup below.",
  },
  "permission-denied": {
    severity: "error",
    text: "The extension could not get permission for this dashboard origin. The newly-created token was revoked.",
  },
  "replacement-confirmation-required": {
    severity: "warning",
    text: "The extension is already connected to another dashboard. Confirm replacement to continue.",
  },
  error: {
    severity: "error",
    text: "Extension connection failed. Any newly-created token was revoked when possible.",
  },
};

function ApiTokenCreationForm({
  form,
  onChange,
  onToggleScope,
  showScopes = true,
  createdToken,
  copied,
  saving,
  submitLabel = "Create token",
  savingLabel = "Creating…",
  resultLabel = "Copy this token now; it will not be shown again.",
  onSubmit,
  onCopy,
  onReset,
}) {
  const canSubmit = !saving && form.name.trim() && form.scopes.length > 0;

  return (
    <Stack spacing={2}>
      <TextField
        label="Token name"
        value={form.name}
        onChange={(event) => onChange({ ...form, name: event.target.value })}
      />
      <TextField
        label="Token expires at (optional)"
        type="datetime-local"
        value={form.expires_at}
        onChange={(event) =>
          onChange({ ...form, expires_at: event.target.value })
        }
        InputLabelProps={{ shrink: true }}
        helperText="Leave blank for no expiry. Revocation still works."
      />
      {showScopes ? (
        <FormGroup className="api-token-scope-grid">
          {API_TOKEN_SCOPES.map((scope) => (
            <FormControlLabel
              key={scope.id}
              control={
                <Checkbox
                  checked={form.scopes.includes(scope.id)}
                  onChange={() => onToggleScope(scope.id)}
                />
              }
              label={
                <Box>
                  <Typography variant="body2">{scope.label}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {scope.id} - {scope.help}
                  </Typography>
                </Box>
              }
            />
          ))}
        </FormGroup>
      ) : (
        <Alert severity="info">
          This flow uses the browser extension preset:{" "}
          <code>{EXTENSION_DEFAULT_SCOPES.join(", ")}</code>. Permission picking
          is hidden here so the extension always gets the minimum safe set it
          expects.
        </Alert>
      )}
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        {onReset && (
          <Button variant="outlined" onClick={onReset} disabled={saving}>
            Reset preset
          </Button>
        )}
        <Button
          variant="contained"
          onClick={onSubmit}
          disabled={!canSubmit}
          startIcon={
            saving ? (
              <CircularProgress size={16} color="inherit" />
            ) : (
              <KeyRoundedIcon />
            )
          }
        >
          {saving ? savingLabel : submitLabel}
        </Button>
      </Stack>
      {createdToken && (
        <Alert
          severity="success"
          action={
            <Button
              color="inherit"
              size="small"
              onClick={onCopy}
              startIcon={
                copied ? <CheckRoundedIcon /> : <ContentCopyRoundedIcon />
              }
            >
              {copied ? "Copied" : "Copy"}
            </Button>
          }
        >
          <strong>{createdToken.name}</strong> was created. {resultLabel}
          <Box component="code" className="one-time-token">
            {createdToken.token}
          </Box>
        </Alert>
      )}
    </Stack>
  );
}

const initialForm = {
  provider: "firecrawl",
  label: "",
  api_key: "",
  base_url: "",
  custom_method: "GET",
  custom_path: "",
  custom_auth_header_name: "Authorization",
  custom_auth_header_template: "Bearer {api_key}",
  custom_metric_label: "remaining",
  custom_metric_path: "$.credits.remaining",
  custom_metric_unit: "credits",
  custom_metric_maximum_path: "",
};

export default function SettingsPage() {
  const [providers, setProviders] = useState([]);
  const [configs, setConfigs] = useState([]);
  const [apiTokens, setApiTokens] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(initialForm);
  const [error, setError] = useState("");
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [codexDeviceFlow, setCodexDeviceFlow] = useState(null);
  const [codexBrowserFlow, setCodexBrowserFlow] = useState(null);
  const [codexCallback, setCodexCallback] = useState("");
  const [codexDeviceStatus, setCodexDeviceStatus] = useState("");
  const [codexDeviceBusy, setCodexDeviceBusy] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [testError, setTestError] = useState("");
  const [homepageForm, setHomepageForm] = useState(() => ({
    ...initialHomepageForm,
    dashboardUrl: typeof window !== "undefined" ? window.location.origin : "",
  }));
  const [homepageCopied, setHomepageCopied] = useState(false);
  const [apiTokenForm, setApiTokenForm] = useState(initialApiTokenForm);
  const [apiTokenSaving, setApiTokenSaving] = useState(false);
  const [apiTokenCopied, setApiTokenCopied] = useState(false);
  const [manualExtensionDialogOpen, setManualExtensionDialogOpen] =
    useState(false);
  const [genericTokenDialogOpen, setGenericTokenDialogOpen] = useState(false);
  const [genericApiTokenForm, setGenericApiTokenForm] = useState(
    initialGenericApiTokenForm,
  );
  const [genericApiTokenSaving, setGenericApiTokenSaving] = useState(false);
  const [createdGenericApiToken, setCreatedGenericApiToken] = useState(null);
  const [genericApiTokenCopied, setGenericApiTokenCopied] = useState(false);
  const [extensionUrlCopied, setExtensionUrlCopied] = useState(false);
  const extensionUrl =
    typeof window !== "undefined" ? window.location.origin : "";
  const [createdApiToken, setCreatedApiToken] = useState(null);
  const [homepageTokenForm, setHomepageTokenForm] = useState(
    initialHomepageTokenForm,
  );
  const [homepageTokenSaving, setHomepageTokenSaving] = useState(false);
  const [createdHomepageToken, setCreatedHomepageToken] = useState(null);
  const [homepageTokenCopied, setHomepageTokenCopied] = useState(false);
  const [extensionConnectState, setExtensionConnectState] = useState({
    status: "idle",
  });
  const [extensionConnectBusy, setExtensionConnectBusy] = useState(false);
  const [extensionReplacement, setExtensionReplacement] = useState(null);
  const [draggingConfigId, setDraggingConfigId] = useState(null);
  const [dragOverConfigId, setDragOverConfigId] = useState(null);
  const dragCommitRef = useRef(null);
  const [thresholdDialog, setThresholdDialog] = useState(null);
  const [thresholdForm, setThresholdForm] = useState([]);
  const [thresholdSaving, setThresholdSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [credentialTarget, setCredentialTarget] = useState(null);
  const [credentialValue, setCredentialValue] = useState("");
  const [credentialSaving, setCredentialSaving] = useState(false);
  const [credentialStatus, setCredentialStatus] = useState("");
  const homepagePreview = useMemo(
    () => homepageYaml(homepageForm),
    [homepageForm],
  );
  const selectedProvider = useMemo(
    () => providers.find((provider) => provider.id === form.provider),
    [providers, form.provider],
  );
  const isCustom = form.provider === "custom_http";
  const isCodex = form.provider === "codex";
  const setup = PROVIDER_SETUP[form.provider];
  const thresholdProviderMetrics = useMemo(() => {
    if (!thresholdDialog) return [];
    const provider = providers.find(
      (entry) => entry.id === thresholdDialog.provider,
    );
    return provider?.alert_metrics || [];
  }, [providers, thresholdDialog]);
  const providerIcons = useMemo(
    () => new Map(providers.map((provider) => [provider.id, provider.icon])),
    [providers],
  );
  const extensionConnectNotice = useMemo(() => {
    if (
      !extensionConnectState.status ||
      extensionConnectState.status === "idle"
    )
      return null;
    const known = EXTENSION_CONNECT_MESSAGES[extensionConnectState.status];
    const fallback = {
      severity: "error",
      text: `Extension setup failed with status: ${extensionConnectState.status}.`,
    };
    const notice = known || fallback;
    const detail =
      extensionConnectState.error || extensionConnectState.detail || "";
    return {
      ...notice,
      detail,
      tokenRevoked: Boolean(extensionConnectState.tokenRevoked),
    };
  }, [extensionConnectState]);

  const load = useCallback(async () => {
    setError("");
    try {
      const providerRows = await api.providers();
      setProviders(providerRows);
      setForm((current) => {
        if (
          providerRows.length &&
          !providerRows.some((provider) => provider.id === current.provider)
        )
          return { ...initialForm, provider: providerRows[0].id };
        return current;
      });
    } catch (err) {
      setProviders([]);
      setError(err.message);
      return;
    }
    try {
      const [configRows, tokenRows] = await Promise.all([
        api.configs(),
        api.apiTokens(),
      ]);
      setConfigs(configRows);
      setApiTokens(tokenRows);
    } catch (err) {
      setConfigs([]);
      setApiTokens([]);
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function payloadFromForm() {
    const payload = {
      provider: form.provider,
      label: form.label.trim() || null,
      api_key: form.api_key.trim(),
      base_url: form.base_url.trim() || null,
      is_enabled: true,
      extra: {},
    };
    if (isCustom) {
      payload.extra = {
        method: form.custom_method,
        path: form.custom_path.trim(),
        auth_header_name:
          form.custom_auth_header_name.trim() || "Authorization",
        auth_header_template:
          form.custom_auth_header_template.trim() || "Bearer {api_key}",
        metrics: [
          {
            label: form.custom_metric_label.trim(),
            path: form.custom_metric_path.trim(),
            unit: form.custom_metric_unit.trim() || null,
            maximum_path: form.custom_metric_maximum_path.trim() || null,
          },
        ],
      };
    }
    return payload;
  }

  async function submit() {
    setError("");
    setSaving(true);
    try {
      await api.createConfig(payloadFromForm());
      setOpen(false);
      setForm(initialForm);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function testConnection() {
    setError("");
    setTestError("");
    setTestResult(null);
    setTesting(true);
    try {
      setTestResult(await api.testConfig(payloadFromForm()));
    } catch (err) {
      setTestError(err.message);
    } finally {
      setTesting(false);
    }
  }

  async function confirmDelete() {
    setError("");
    setDeleting(true);
    try {
      await api.deleteConfig(deleteTarget.id);
      setDeleteTarget(null);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeleting(false);
    }
  }

  function openCredentialDialog(config) {
    setCredentialTarget(config);
    setCredentialValue("");
    setCredentialStatus("");
    setTestError("");
    setTestResult(null);
    setCodexDeviceFlow(null);
    setCodexBrowserFlow(null);
    setCodexCallback("");
    setCodexDeviceStatus("");
  }

  function closeCredentialDialog() {
    if (credentialSaving || codexDeviceBusy) return;
    setCredentialTarget(null);
    setCredentialValue("");
    setCredentialStatus("");
    setCodexDeviceFlow(null);
    setCodexBrowserFlow(null);
    setCodexCallback("");
    setCodexDeviceStatus("");
  }

  async function replaceCredential() {
    if (!credentialTarget || !credentialValue.trim()) return;
    setError("");
    setCredentialStatus("");
    setCredentialSaving(true);
    try {
      await api.updateConfig(credentialTarget.id, {
        api_key: credentialValue.trim(),
      });
      setCredentialValue("");
      setCredentialStatus("Credential replaced. The old token was overwritten and never displayed.");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setCredentialSaving(false);
    }
  }
  function updateHomepageForm(patch) {
    setHomepageCopied(false);
    setHomepageTokenCopied(false);
    setHomepageForm((current) => ({ ...current, ...patch }));
  }
  async function copyHomepageYaml() {
    setHomepageCopied(false);
    try {
      if (navigator.clipboard?.writeText)
        await navigator.clipboard.writeText(homepagePreview);
      else window.prompt("Copy Homepage YAML", homepagePreview);
      setHomepageCopied(true);
      window.setTimeout(() => setHomepageCopied(false), 2200);
    } catch {
      window.prompt("Copy Homepage YAML", homepagePreview);
    }
  }
  function toggleApiTokenScope(scopeId) {
    setApiTokenForm((current) => {
      const hasScope = current.scopes.includes(scopeId);
      return {
        ...current,
        scopes: hasScope
          ? current.scopes.filter((scope) => scope !== scopeId)
          : [...current.scopes, scopeId],
      };
    });
  }
  function toggleGenericApiTokenScope(scopeId) {
    setGenericApiTokenForm((current) => {
      const hasScope = current.scopes.includes(scopeId);
      return {
        ...current,
        scopes: hasScope
          ? current.scopes.filter((scope) => scope !== scopeId)
          : [...current.scopes, scopeId],
      };
    });
  }
  async function copyExtensionUrl() {
    setExtensionUrlCopied(false);
    try {
      if (navigator.clipboard?.writeText)
        await navigator.clipboard.writeText(extensionUrl);
      else window.prompt("Copy dashboard URL", extensionUrl);
      setExtensionUrlCopied(true);
      window.setTimeout(() => setExtensionUrlCopied(false), 2200);
    } catch {
      window.prompt("Copy dashboard URL", extensionUrl);
    }
  }
  function tokenPayloadFromForm(
    tokenForm,
    fallbackName,
    scopes = tokenForm.scopes,
  ) {
    return {
      name: tokenForm.name.trim() || fallbackName,
      scopes,
      expires_at: tokenForm.expires_at
        ? new Date(tokenForm.expires_at).toISOString()
        : null,
    };
  }
  function extensionTokenPayload() {
    return tokenPayloadFromForm(
      apiTokenForm,
      initialApiTokenForm.name,
      EXTENSION_DEFAULT_SCOPES,
    );
  }
  function logExtensionSetup(stage, detail = {}) {
    const payload = { stage, ...detail };
    if (
      detail?.status &&
      !["available", "authorized", "connected", "connected-degraded"].includes(
        detail.status,
      )
    )
      console.warn("[Usage Dashboard] extension setup", payload);
    else console.info("[Usage Dashboard] extension setup", payload);
  }
  async function revokeCreatedConnectionToken(token) {
    if (!token?.id) return;
    try {
      await api.revokeApiToken(token.id);
      logExtensionSetup("token-revoked", { tokenId: token.id });
    } catch (err) {
      logExtensionSetup("token-revoke-failed", {
        tokenId: token.id,
        error: err.message,
      });
    }
  }
  async function connectExtension({ replaceExisting = false } = {}) {
    setError("");
    setCreatedApiToken(null);
    setApiTokenCopied(false);
    setExtensionConnectState({ status: "checking" });
    setExtensionConnectBusy(true);
    logExtensionSetup("started");
    try {
      const ping = await extensionBridge.ping();
      logExtensionSetup("ping", {
        status: ping.status,
        target: ping.target?.key,
        extensionId: ping.target?.id,
        capabilities: ping.response?.capabilities,
      });
      if (ping.status !== "available") {
        setExtensionConnectState({ status: ping.status });
        return;
      }
      if (!extensionSupportsOneClickSetup(ping.response)) {
        logExtensionSetup("capability-check", {
          status: "incompatible-protocol",
          target: ping.target?.key,
          extensionId: ping.target?.id,
          code: "missing-authorize-origin",
          capabilities: ping.response?.capabilities,
        });
        setExtensionConnectState({
          status: "incompatible-protocol",
          error:
            "The installed extension does not advertise the safe one-click setup capability. Update or reload the extension, then try again.",
        });
        return;
      }

      setExtensionConnectState({
        status: "requesting-permission",
        target: ping.target,
      });
      const authorized = await extensionBridge.authorizeOrigin({
        target: ping.target,
      });
      logExtensionSetup("authorize-origin", {
        status: authorized.status,
        error: authorized.error,
        detail: authorized.response?.detail,
        code: authorized.response?.code,
      });
      if (authorized.status !== "authorized") {
        setExtensionConnectState({
          status: authorized.status || "error",
          error:
            authorized.error ||
            authorized.response?.error ||
            authorized.response?.detail ||
            authorized.response?.message ||
            "",
          tokenRevoked: false,
        });
        return;
      }

      setExtensionConnectState({ status: "creating-token" });
      const token = await api.createApiToken(extensionTokenPayload());
      logExtensionSetup("token-created", {
        tokenId: token.id,
        tokenPrefix: token.token_prefix,
      });
      await load();

      setExtensionConnectState({ status: "configuring", target: ping.target });
      const configured = await extensionBridge.configure({
        target: ping.target,
        token: token.token,
        replaceExisting,
      });
      logExtensionSetup("configure", {
        status: configured.status,
        error: configured.error,
        detail: configured.response?.detail,
        code: configured.response?.code,
        reachable: configured.reachable,
      });
      if (configured.status === "replacement-confirmation-required") {
        await revokeCreatedConnectionToken(token);
        await load();
        setExtensionReplacement({ target: ping.target });
        setExtensionConnectState({
          status: "replacement-confirmation-required",
        });
        return;
      }
      if (!["connected", "connected-degraded"].includes(configured.status)) {
        await revokeCreatedConnectionToken(token);
        await load();
        setExtensionConnectState({
          status: configured.status || "error",
          error:
            configured.error ||
            configured.response?.error ||
            configured.response?.detail ||
            configured.response?.message ||
            "",
          tokenRevoked: true,
        });
        return;
      }

      setApiTokenForm({
        ...initialApiTokenForm,
        scopes: [...initialApiTokenForm.scopes],
      });
      setExtensionConnectState({
        status: configured.status,
        target: ping.target,
      });
      logExtensionSetup("connected", {
        status: configured.status,
        target: ping.target?.key,
      });
      await load();
    } catch (err) {
      setExtensionConnectState({ status: "error", error: err.message });
      logExtensionSetup("exception", { status: "error", error: err.message });
      setError(err.message);
    } finally {
      setExtensionConnectBusy(false);
    }
  }
  function confirmExtensionReplacement() {
    setExtensionReplacement(null);
    connectExtension({ replaceExisting: true });
  }
  async function createExtensionApiToken() {
    setError("");
    setApiTokenSaving(true);
    setApiTokenCopied(false);
    try {
      const token = await api.createApiToken(extensionTokenPayload());
      setCreatedApiToken(token);
      setApiTokenForm({
        ...initialApiTokenForm,
        scopes: [...initialApiTokenForm.scopes],
      });
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setApiTokenSaving(false);
    }
  }
  async function createGenericApiToken() {
    setError("");
    setGenericApiTokenSaving(true);
    setGenericApiTokenCopied(false);
    try {
      const token = await api.createApiToken(
        tokenPayloadFromForm(
          genericApiTokenForm,
          initialGenericApiTokenForm.name,
        ),
      );
      setCreatedGenericApiToken(token);
      setGenericApiTokenForm({
        ...initialGenericApiTokenForm,
        scopes: [...initialGenericApiTokenForm.scopes],
      });
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setGenericApiTokenSaving(false);
    }
  }
  async function revokeApiToken(id) {
    setError("");
    try {
      await api.revokeApiToken(id);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }
  async function copyCreatedApiToken() {
    if (!createdApiToken?.token) return;
    setApiTokenCopied(false);
    try {
      if (navigator.clipboard?.writeText)
        await navigator.clipboard.writeText(createdApiToken.token);
      else window.prompt("Copy API token", createdApiToken.token);
      setApiTokenCopied(true);
      window.setTimeout(() => setApiTokenCopied(false), 2200);
    } catch {
      window.prompt("Copy API token", createdApiToken.token);
    }
  }
  async function copyCreatedGenericApiToken() {
    if (!createdGenericApiToken?.token) return;
    setGenericApiTokenCopied(false);
    try {
      if (navigator.clipboard?.writeText)
        await navigator.clipboard.writeText(createdGenericApiToken.token);
      else window.prompt("Copy API token", createdGenericApiToken.token);
      setGenericApiTokenCopied(true);
      window.setTimeout(() => setGenericApiTokenCopied(false), 2200);
    } catch {
      window.prompt("Copy API token", createdGenericApiToken.token);
    }
  }
  async function createHomepageApiToken() {
    setError("");
    setHomepageTokenSaving(true);
    setHomepageTokenCopied(false);
    try {
      const token = await api.createApiToken({
        name: homepageTokenForm.name.trim() || initialHomepageTokenForm.name,
        scopes: HOMEPAGE_DEFAULT_SCOPES,
        expires_at: homepageTokenForm.expires_at
          ? new Date(homepageTokenForm.expires_at).toISOString()
          : null,
      });
      setCreatedHomepageToken(token);
      updateHomepageForm({
        authMode: "bearer",
        token: token.token,
        includeToken: true,
      });
      setHomepageTokenForm(initialHomepageTokenForm);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setHomepageTokenSaving(false);
    }
  }
  async function copyCreatedHomepageToken() {
    if (!createdHomepageToken?.token) return;
    setHomepageTokenCopied(false);
    try {
      if (navigator.clipboard?.writeText)
        await navigator.clipboard.writeText(createdHomepageToken.token);
      else window.prompt("Copy Homepage API token", createdHomepageToken.token);
      setHomepageTokenCopied(true);
      window.setTimeout(() => setHomepageTokenCopied(false), 2200);
    } catch {
      window.prompt("Copy Homepage API token", createdHomepageToken.token);
    }
  }
  async function toggleApi(config) {
    await api.updateConfig(config.id, { is_enabled: !config.is_enabled });
    await load();
  }
  async function toggleUi(config) {
    await api.updateConfig(config.id, { is_visible: !config.is_visible });
    await load();
  }
  async function persistConfigOrder(nextConfigs) {
    setConfigs(nextConfigs);
    try {
      setConfigs(
        await api.reorderConfigs(nextConfigs.map((config) => config.id)),
      );
    } catch (err) {
      setError(err.message);
      await load();
    }
  }
  async function moveConfig(configId, direction) {
    const currentIndex = configs.findIndex((config) => config.id === configId);
    const nextIndex = currentIndex + direction;
    if (currentIndex < 0 || nextIndex < 0 || nextIndex >= configs.length)
      return;
    const nextConfigs = [...configs];
    const [moved] = nextConfigs.splice(currentIndex, 1);
    nextConfigs.splice(nextIndex, 0, moved);
    await persistConfigOrder(nextConfigs);
  }
  function reorderConfigToTarget(sourceId, targetId) {
    if (!sourceId || !targetId || sourceId === targetId) return;
    const sourceIndex = configs.findIndex((config) => config.id === sourceId);
    const targetIndex = configs.findIndex((config) => config.id === targetId);
    if (sourceIndex < 0 || targetIndex < 0) return;
    const nextConfigs = [...configs];
    const [moved] = nextConfigs.splice(sourceIndex, 1);
    nextConfigs.splice(targetIndex, 0, moved);
    persistConfigOrder(nextConfigs);
  }
  function scheduleDragReorder(sourceId, targetId) {
    window.clearTimeout(dragCommitRef.current);
    if (!sourceId || !targetId || sourceId === targetId) return;
    dragCommitRef.current = window.setTimeout(
      () => reorderConfigToTarget(sourceId, targetId),
      90,
    );
  }
  function endConfigDrag() {
    window.clearTimeout(dragCommitRef.current);
    setDraggingConfigId(null);
    setDragOverConfigId(null);
  }
  function openThresholdDialog(config) {
    setThresholdDialog(config);
    setThresholdForm(
      (config.alert_thresholds || []).map((rule) => ({
        metric: rule.metric,
        direction: rule.direction || "increasing",
        warning: rule.warning ?? "",
        critical: rule.critical ?? "",
        exhausted: rule.exhausted ?? "",
      })),
    );
  }
  function addThresholdRule() {
    setThresholdForm((current) => [
      ...current,
      {
        metric: "",
        direction: "increasing",
        warning: "",
        critical: "",
        exhausted: "",
      },
    ]);
  }
  function updateThresholdRule(index, patch) {
    setThresholdForm((current) =>
      current.map((rule, i) => (i === index ? { ...rule, ...patch } : rule)),
    );
  }
  function selectThresholdMetric(index, metric) {
    const spec = thresholdProviderMetrics.find(
      (entry) => entry.metric === metric,
    );
    updateThresholdRule(index, {
      metric,
      direction: spec?.direction || "increasing",
    });
  }
  function removeThresholdRule(index) {
    setThresholdForm((current) => current.filter((_, i) => i !== index));
  }
  async function saveThresholds() {
    setError("");
    setThresholdSaving(true);
    const clean = thresholdForm
      .filter((rule) => rule.metric.trim())
      .map((rule) => {
        const num = (value) =>
          value === "" || value === null ? null : Number(value);
        return {
          metric: rule.metric.trim(),
          direction: rule.direction,
          warning: num(rule.warning),
          critical: num(rule.critical),
          exhausted: num(rule.exhausted),
        };
      });
    try {
      await api.updateConfig(thresholdDialog.id, { alert_thresholds: clean });
      setThresholdDialog(null);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setThresholdSaving(false);
    }
  }
  async function startCodexDeviceLogin() {
    setError("");
    setCredentialStatus("");
    setTestError("");
    setTestResult(null);
    setCodexDeviceStatus("Requesting device code…");
    setCodexDeviceBusy(true);
    try {
      const flow = await api.startCodexDeviceOAuth();
      setCodexDeviceFlow(flow);
      setCodexBrowserFlow(null);
      setCodexCallback("");
      setCodexDeviceStatus(
        "Open the link, enter the code, then leave this dialog open while polling completes.",
      );
      if (flow.verification_uri_complete)
        window.open(
          flow.verification_uri_complete,
          "_blank",
          "noopener,noreferrer",
        );
    } catch (err) {
      setCodexDeviceStatus("");
      setTestError(err.message);
    } finally {
      setCodexDeviceBusy(false);
    }
  }

  async function startCodexBrowserLogin() {
    setError("");
    setCredentialStatus("");
    setTestError("");
    setTestResult(null);
    setCodexDeviceStatus("Creating browser login link…");
    setCodexDeviceBusy(true);
    try {
      const flow = await api.startCodexBrowserOAuth();
      setCodexBrowserFlow(flow);
      setCodexDeviceFlow(null);
      setCodexCallback("");
      setCodexDeviceStatus(
        "Open the login link. After OpenAI redirects to localhost, copy the full browser URL and paste it below.",
      );
      window.open(flow.authorization_url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setCodexDeviceStatus("");
      setTestError(err.message);
    } finally {
      setCodexDeviceBusy(false);
    }
  }

  async function completeCodexBrowserLogin() {
    if (!codexBrowserFlow?.flow_id || !codexCallback.trim()) return;
    setError("");
    setTestError("");
    setCodexDeviceBusy(true);
    try {
      const result = await api.completeCodexBrowserOAuth(
        codexBrowserFlow.flow_id,
        {
          label: credentialTarget ? credentialTarget.label : form.label.trim() || null,
          callback: codexCallback.trim(),
          config_id: credentialTarget?.id || null,
        },
      );
      if (result.status === "completed") {
        const label = result.config?.label || "codex";
        setCodexDeviceStatus(
          credentialTarget
            ? `Codex reauthenticated for ${label}.`
            : `Codex connected as ${label}.`,
        );
        setCredentialStatus(
          credentialTarget
            ? "Codex credential replaced. The previous OAuth token was overwritten and never displayed."
            : "",
        );
        setCodexBrowserFlow(null);
        setCodexCallback("");
        if (!credentialTarget) {
          setOpen(false);
          setForm(initialForm);
        }
        await load();
      } else {
        setCodexDeviceStatus("");
        setTestError(
          result.error || "Codex browser authorization did not complete.",
        );
      }
    } catch (err) {
      setTestError(err.message);
    } finally {
      setCodexDeviceBusy(false);
    }
  }

  async function pollCodexDeviceLogin() {
    if (!codexDeviceFlow?.flow_id) return;
    setError("");
    setTestError("");
    setCodexDeviceBusy(true);
    try {
      const result = await api.pollCodexDeviceOAuth(codexDeviceFlow.flow_id, {
        label: credentialTarget ? credentialTarget.label : form.label.trim() || null,
        config_id: credentialTarget?.id || null,
      });
      if (result.status === "completed") {
        const label = result.config?.label || "codex";
        setCodexDeviceStatus(
          credentialTarget
            ? `Codex reauthenticated for ${label}.`
            : `Codex connected as ${label}.`,
        );
        setCredentialStatus(
          credentialTarget
            ? "Codex credential replaced. The previous OAuth token was overwritten and never displayed."
            : "",
        );
        setCodexDeviceFlow(null);
        if (!credentialTarget) {
          setOpen(false);
          setForm(initialForm);
        }
        await load();
      } else if (result.status === "pending" || result.status === "slow_down") {
        setCodexDeviceStatus(
          `Still waiting for OpenAI authorization. Try again in ${result.interval_seconds || codexDeviceFlow.interval_seconds || 5}s.`,
        );
      } else {
        setCodexDeviceStatus("");
        setTestError(
          result.error || "Codex device authorization did not complete.",
        );
      }
    } catch (err) {
      setTestError(err.message);
    } finally {
      setCodexDeviceBusy(false);
    }
  }

  const missingRequired =
    (!isCodex && !form.api_key.trim()) ||
    (isCustom &&
      (!form.base_url.trim() ||
        !form.custom_path.trim() ||
        !form.custom_metric_label.trim() ||
        !form.custom_metric_path.trim()));
  const testDisabled = testing || saving || missingRequired;
  const saveDisabled =
    testing || saving || missingRequired || (isCodex && !form.api_key.trim());

  return (
    <>
      <header className="page-heading">
        <Box>
          <div className="page-kicker">Connections</div>
          <Typography component="h1" variant="h2">
            Provider settings
          </Typography>
          <Typography component="p">
            Manage credentials and custom endpoints. Secrets are encrypted
            before storage and never returned in full.
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<AddRoundedIcon />}
          onClick={() => {
            setOpen(true);
            setTestResult(null);
            setTestError("");
            setCodexDeviceFlow(null);
            setCodexBrowserFlow(null);
            setCodexCallback("");
            setCodexDeviceStatus("");
          }}
        >
          Add provider
        </Button>
      </header>
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}
      <Paper
        id="provider-settings"
        className="settings-panel glass-panel"
        variant="outlined"
      >
        <div className="settings-panel-header">
          <Box>
            <Typography variant="h6">Connected providers</Typography>
            <Typography variant="body2" color="text.secondary">
              {configs.length} connection{configs.length === 1 ? "" : "s"}{" "}
              configured
            </Typography>
          </Box>
          <KeyRoundedIcon color="primary" />
        </div>
        {configs.length === 0 ? (
          <Box className="empty-state" sx={{ m: 2 }}>
            <div className="empty-state-icon">
              <HubRoundedIcon />
            </div>
            <Typography variant="h6">Nothing connected yet</Typography>
            <Typography color="text.secondary" sx={{ mt: 1 }}>
              Add a provider to start collecting usage telemetry.
            </Typography>
          </Box>
        ) : (
          <div className="config-list">
            {configs.map((config, index) => {
              const dragging = draggingConfigId === config.id;
              const dragOver =
                dragOverConfigId === config.id &&
                draggingConfigId !== config.id;
              return (
                <div
                  className={`config-row${dragging ? " is-dragging" : ""}${dragOver ? " is-drag-over" : ""}`}
                  key={config.id}
                  draggable
                  onDragStart={(event) => {
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", String(config.id));
                    setDraggingConfigId(config.id);
                  }}
                  onDragEnter={(event) => {
                    event.preventDefault();
                    setDragOverConfigId(config.id);
                    scheduleDragReorder(draggingConfigId, config.id);
                  }}
                  onDragOver={(event) => {
                    event.preventDefault();
                    event.dataTransfer.dropEffect = "move";
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    reorderConfigToTarget(
                      Number(event.dataTransfer.getData("text/plain")),
                      config.id,
                    );
                    endConfigDrag();
                  }}
                  onDragEnd={endConfigDrag}
                >
                  <div
                    className="config-order-controls"
                    aria-label={`Reorder ${config.label}`}
                  >
                    <Tooltip title="Drag to reorder">
                      <button
                        type="button"
                        className="config-drag-handle"
                        aria-label={`Drag ${config.label} to reorder`}
                      >
                        <DragIndicatorRoundedIcon />
                      </button>
                    </Tooltip>
                    <IconButton
                      size="small"
                      onClick={() => moveConfig(config.id, -1)}
                      disabled={index === 0}
                      aria-label={`Move ${config.label} up`}
                    >
                      ↑
                    </IconButton>
                    <IconButton
                      size="small"
                      onClick={() => moveConfig(config.id, 1)}
                      disabled={index === configs.length - 1}
                      aria-label={`Move ${config.label} down`}
                    >
                      ↓
                    </IconButton>
                  </div>
                  <div className="config-identity">
                    <div className="config-avatar" aria-hidden="true">
                      <ProviderIcon icon={providerIcons.get(config.provider)} />
                    </div>
                    <div>
                      <span>Provider</span>
                      <strong>{config.label}</strong>
                      <Typography variant="caption" color="text.secondary">
                        {config.provider}
                      </Typography>
                      {(config.alert_thresholds || []).length > 0 && (
                        <div className="config-alert-summary">
                          {(config.alert_thresholds || []).map(
                            (rule, ruleIndex) => (
                              <span
                                className="threshold-chip"
                                key={`${rule.metric}-${ruleIndex}`}
                              >
                                {formatThresholdRule(rule)}
                              </span>
                            ),
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="config-detail">
                    <span>Credential</span>
                    {config.api_key_masked}
                  </div>
                  <div className="config-detail">
                    <span>Endpoint</span>
                    {config.base_url || "Provider default"}
                  </div>
                  <div className="config-actions">
                    <label className="config-switch">
                      <span>API</span>
                      <Tooltip
                        title={
                          config.is_enabled
                            ? "Disable API polling and Homepage output"
                            : "Enable API polling and Homepage output"
                        }
                      >
                        <Switch
                          checked={config.is_enabled}
                          onChange={() => toggleApi(config)}
                          color="success"
                          inputProps={{
                            "aria-label": `${config.is_enabled ? "Disable" : "Enable"} API for ${config.label}`,
                          }}
                        />
                      </Tooltip>
                    </label>
                    <label className="config-switch">
                      <span>UI</span>
                      <Tooltip
                        title={
                          config.is_visible
                            ? "Hide from main dashboard"
                            : "Show on main dashboard"
                        }
                      >
                        <Switch
                          checked={config.is_visible}
                          onChange={() => toggleUi(config)}
                          color="primary"
                          inputProps={{
                            "aria-label": `${config.is_visible ? "Hide" : "Show"} ${config.label} on main dashboard`,
                          }}
                        />
                      </Tooltip>
                    </label>
                    <Tooltip title="Replace credential">
                      <IconButton
                        size="small"
                        onClick={() => openCredentialDialog(config)}
                        aria-label={`Replace credential for ${config.label}`}
                      >
                        <KeyRoundedIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Alert thresholds">
                      <IconButton
                        size="small"
                        onClick={() => openThresholdDialog(config)}
                        aria-label={`Edit alert thresholds for ${config.label}`}
                      >
                        <NotificationsActiveRoundedIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Remove provider">
                      <IconButton
                        color="error"
                        onClick={() => setDeleteTarget(config)}
                        aria-label={`Remove ${config.label}`}
                      >
                        <DeleteOutlineRoundedIcon />
                      </IconButton>
                    </Tooltip>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Paper>
      <DataSourcesSection />
      <Paper
        id="integrations"
        className="settings-panel integrations-panel glass-panel"
        variant="outlined"
      >
        <div className="settings-panel-header">
          <Box>
            <Typography variant="h6">Integrations</Typography>
            <Typography variant="body2" color="text.secondary">
              Connect external clients with scoped tokens instead of sharing
              your admin session.
            </Typography>
          </Box>
          <ExtensionRoundedIcon color="primary" />
        </div>
        <Box className="integrations-stack">
          <Box
            id="browser-extension-integration"
            className="integration-card browser-extension-card"
          >
            <div className="integration-card-header">
              <Box>
                <Typography component="h3" variant="subtitle1">
                  Browser extension
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  One-click setup for Chrome/Brave and compatible browser
                  builds.
                </Typography>
              </Box>
              <ExtensionRoundedIcon color="primary" />
            </div>
            <Box className="integration-card-body">
              <Stack spacing={2}>
                <Box className="homepage-guide api-token-guide">
                  <Typography variant="body2" color="text.secondary">
                    Install or load the Chrome/Brave extension from{" "}
                    <a
                      href="https://skulldorom.github.io/usage-dashboard/extension.html"
                      target="_blank"
                      rel="noreferrer"
                    >
                      the Usage Dashboard extension page
                    </a>
                    . Before using one-click setup, open the extension Options
                    page and paste this dashboard URL so the extension knows
                    which self-hosted instance to trust.
                  </Typography>
                  <Stack
                    className="extension-url-inline-copy"
                    direction={{ xs: "column", sm: "row" }}
                    spacing={1}
                    alignItems={{ xs: "stretch", sm: "center" }}
                    sx={{ mt: 1.5 }}
                  >
                    <TextField
                      size="small"
                      fullWidth
                      label="Dashboard URL for extension options"
                      value={extensionUrl}
                      InputProps={{ readOnly: true }}
                      onFocus={(event) => event.target.select()}
                      helperText="Paste this in the extension Options page before one-click setup."
                    />
                    <Button
                      variant="outlined"
                      onClick={copyExtensionUrl}
                      startIcon={
                        extensionUrlCopied ? (
                          <CheckRoundedIcon />
                        ) : (
                          <ContentCopyRoundedIcon />
                        )
                      }
                      sx={{ flex: "0 0 auto" }}
                    >
                      {extensionUrlCopied ? "Copied" : "Copy"}
                    </Button>
                  </Stack>
                  <Stack
                    direction="row"
                    spacing={1}
                    flexWrap="wrap"
                    useFlexGap
                    sx={{ mt: 1.5 }}
                  >
                    <Button
                      variant="contained"
                      onClick={() => connectExtension()}
                      disabled={
                        extensionConnectBusy || !apiTokenForm.name.trim()
                      }
                      startIcon={
                        extensionConnectBusy ? (
                          <CircularProgress size={16} color="inherit" />
                        ) : (
                          <ExtensionRoundedIcon />
                        )
                      }
                    >
                      {extensionConnectBusy
                        ? "Connecting…"
                        : "Connect extension"}
                    </Button>
                    <Button
                      variant="outlined"
                      onClick={() => {
                        setManualExtensionDialogOpen(true);
                        setCreatedApiToken(null);
                        setApiTokenCopied(false);
                        setExtensionUrlCopied(false);
                      }}
                    >
                      Manual setup
                    </Button>
                    <Button
                      component="a"
                      href="https://skulldorom.github.io/usage-dashboard/extension.html"
                      target="_blank"
                      rel="noreferrer"
                      variant="outlined"
                      endIcon={<LaunchRoundedIcon />}
                    >
                      Install extension
                    </Button>
                  </Stack>
                  {extensionConnectNotice && (
                    <Alert
                      severity={extensionConnectNotice.severity}
                      sx={{ mt: 1.5 }}
                    >
                      {extensionConnectNotice.text}
                      {extensionConnectNotice.tokenRevoked && (
                        <>
                          <br />
                          The newly-created token was revoked, so there is no
                          dangling credential.
                        </>
                      )}
                      {extensionConnectNotice.detail && (
                        <>
                          <br />
                          <Typography component="span" variant="caption">
                            Details: {extensionConnectNotice.detail}
                          </Typography>
                        </>
                      )}
                    </Alert>
                  )}
                </Box>
              </Stack>
            </Box>
          </Box>
          <Box
            id="homepage-integration"
            className="integration-card homepage-integration-card"
          >
            <div className="integration-card-header">
              <Box>
                <Typography component="h3" variant="subtitle1">
                  Homepage integration
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Generate a paste-ready services.yaml entry for gethomepage.dev
                  with its own scoped token.
                </Typography>
              </Box>
              <ContentCopyRoundedIcon color="primary" />
            </div>
            <Box className="homepage-guide integration-guide">
              <Typography component="h4" variant="subtitle1">
                Where this YAML goes
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Paste the generated service block into the Homepage group you
                want inside <code>services.yaml</code>. The generator always
                creates a single <strong>Usage Dashboard</strong> service
                pointed at the existing <code>/api/v1/homepage</code> endpoint.
                Dynamic provider list is the default because it renders one row
                per enabled API. Switch to summary cards only when you want
                top-level stats.
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Tip: if you set <code>HOMEPAGE_ALLOWED_HOSTS</code> for the
                Homepage host, choose “No auth header”. Otherwise generate a
                Homepage token below; it only gets <code>usage:read</code>.
              </Typography>
            </Box>
            <Box className="homepage-config-grid integration-card-body">
              <Stack spacing={2}>
                <TextField
                  label="Usage Dashboard URL / hostname"
                  value={homepageForm.dashboardUrl}
                  onChange={(event) =>
                    updateHomepageForm({ dashboardUrl: event.target.value })
                  }
                  placeholder="https://usage.example.com"
                  helperText="The public URL Homepage can reach. The API path is fixed to /api/v1/homepage."
                />
                <TextField
                  label="Refresh interval (ms)"
                  value={homepageForm.refreshInterval}
                  onChange={(event) =>
                    updateHomepageForm({ refreshInterval: event.target.value })
                  }
                  placeholder="300000"
                  helperText="Homepage refresh interval in milliseconds. Leave blank to omit."
                />
                <FormControl fullWidth>
                  <InputLabel>Homepage display</InputLabel>
                  <Select
                    label="Homepage display"
                    value={homepageForm.displayMode}
                    onChange={(event) =>
                      updateHomepageForm({ displayMode: event.target.value })
                    }
                  >
                    <MenuItem value="dynamic-list">
                      Dynamic provider list
                    </MenuItem>
                    <MenuItem value="summary">Summary cards</MenuItem>
                  </Select>
                  <FormHelperText>
                    Dynamic list renders each enabled provider row from the
                    API's list payload.
                  </FormHelperText>
                </FormControl>
                <FormControl fullWidth>
                  <InputLabel>Authentication</InputLabel>
                  <Select
                    label="Authentication"
                    value={homepageForm.authMode}
                    onChange={(event) =>
                      updateHomepageForm({ authMode: event.target.value })
                    }
                  >
                    <MenuItem value="bearer">
                      Bearer Authorization header
                    </MenuItem>
                    <MenuItem value="none">
                      No auth header / allowed host
                    </MenuItem>
                  </Select>
                  <FormHelperText>
                    Use no auth only when Homepage is allowed by host or
                    protected by your network.
                  </FormHelperText>
                </FormControl>
                {homepageForm.authMode === "bearer" && (
                  <>
                    <Box className="homepage-token-generator">
                      <Stack spacing={1.5}>
                        <Typography component="h4" variant="subtitle2">
                          Homepage token
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Generate a separate token with only{" "}
                          <code>usage:read</code>. The full token is shown once
                          and inserted into the YAML preview.
                        </Typography>
                        <TextField
                          label="Homepage token name"
                          value={homepageTokenForm.name}
                          onChange={(event) =>
                            setHomepageTokenForm({
                              ...homepageTokenForm,
                              name: event.target.value,
                            })
                          }
                        />
                        <TextField
                          label="Homepage token expires at (optional)"
                          type="datetime-local"
                          value={homepageTokenForm.expires_at}
                          onChange={(event) =>
                            setHomepageTokenForm({
                              ...homepageTokenForm,
                              expires_at: event.target.value,
                            })
                          }
                          InputLabelProps={{ shrink: true }}
                        />
                        <Button
                          variant="contained"
                          onClick={createHomepageApiToken}
                          disabled={
                            homepageTokenSaving ||
                            !homepageTokenForm.name.trim()
                          }
                          startIcon={
                            homepageTokenSaving ? (
                              <CircularProgress size={16} color="inherit" />
                            ) : (
                              <KeyRoundedIcon />
                            )
                          }
                        >
                          {homepageTokenSaving
                            ? "Generating…"
                            : "Generate Homepage token"}
                        </Button>
                      </Stack>
                    </Box>
                    <TextField
                      label="Token (optional)"
                      type="password"
                      value={homepageForm.token}
                      onChange={(event) =>
                        updateHomepageForm({ token: event.target.value })
                      }
                      helperText="Use a scoped token with usage:read. Left blank, the YAML keeps a safe placeholder instead of exposing a secret."
                    />
                    <label className="config-switch homepage-token-switch">
                      <span>Include token in YAML</span>
                      <Tooltip title="Off keeps a placeholder so copied YAML does not leak secrets on screen.">
                        <Switch
                          checked={homepageForm.includeToken}
                          onChange={(event) =>
                            updateHomepageForm({
                              includeToken: event.target.checked,
                            })
                          }
                          color="warning"
                          inputProps={{
                            "aria-label": "Include token in generated YAML",
                          }}
                        />
                      </Tooltip>
                    </label>
                    {createdHomepageToken && (
                      <Alert
                        severity="success"
                        action={
                          <Button
                            color="inherit"
                            size="small"
                            onClick={copyCreatedHomepageToken}
                            startIcon={
                              homepageTokenCopied ? (
                                <CheckRoundedIcon />
                              ) : (
                                <ContentCopyRoundedIcon />
                              )
                            }
                          >
                            {homepageTokenCopied ? "Copied" : "Copy"}
                          </Button>
                        }
                      >
                        <strong>{createdHomepageToken.name}</strong> was created
                        with <code>usage:read</code> only and inserted into the
                        YAML preview. Copy it now; it will not be shown again.
                        <Box component="code" className="one-time-token">
                          {createdHomepageToken.token}
                        </Box>
                      </Alert>
                    )}
                  </>
                )}
              </Stack>
              <Box className="homepage-yaml-preview">
                <Stack
                  direction="row"
                  justifyContent="space-between"
                  alignItems="center"
                  spacing={2}
                  sx={{ mb: 1.5 }}
                >
                  <Box>
                    <Typography variant="overline" color="primary.main">
                      Live YAML preview
                    </Typography>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      display="block"
                    >
                      Updates as you type; copy, paste, done.
                    </Typography>
                  </Box>
                  <Button
                    variant="contained"
                    size="small"
                    onClick={copyHomepageYaml}
                    startIcon={
                      homepageCopied ? (
                        <CheckRoundedIcon />
                      ) : (
                        <ContentCopyRoundedIcon />
                      )
                    }
                  >
                    {homepageCopied ? "Copied" : "Copy YAML"}
                  </Button>
                </Stack>
                <pre>
                  <code>{homepagePreview}</code>
                </pre>
              </Box>
            </Box>
          </Box>
          <Box
            id="integration-tokens"
            className="integration-card integration-tokens-card"
          >
            <div className="integration-card-header">
              <Box>
                <Typography component="h3" variant="subtitle1">
                  Integration tokens
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Review, create, and revoke scoped tokens used by integrations.
                </Typography>
              </Box>
              <Stack direction="row" spacing={1} alignItems="center">
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<AddRoundedIcon />}
                  onClick={() => {
                    setGenericTokenDialogOpen(true);
                    setCreatedGenericApiToken(null);
                    setGenericApiTokenCopied(false);
                  }}
                >
                  Add token
                </Button>
                <KeyRoundedIcon color="primary" />
              </Stack>
            </div>
            <Box className="integration-card-body">
              <Box className="api-token-list">
                <Typography variant="overline" color="primary.main">
                  Existing integration tokens
                </Typography>
                {apiTokens.length === 0 ? (
                  <Box className="empty-state api-token-empty">
                    <Typography variant="h6">No scoped tokens yet</Typography>
                    <Typography color="text.secondary" sx={{ mt: 1 }}>
                      Create separate tokens for the extension and Homepage;
                      tiny blast radiuses, very adult.
                    </Typography>
                  </Box>
                ) : (
                  apiTokens.map((token) => {
                    const revoked = Boolean(token.revoked_at);
                    const expired =
                      token.expires_at &&
                      new Date(token.expires_at) <= new Date();
                    const scopes = token.scopes || [];
                    const tokenKind =
                      scopes.length === 1 && scopes.includes("usage:read")
                        ? "Homepage-ready"
                        : scopes.includes("poll:write") &&
                            scopes.includes("configs:read")
                          ? "Extension-ready"
                          : "Scoped token";
                    return (
                      <Box className="api-token-row" key={token.id}>
                        <Stack
                          direction={{ xs: "column", sm: "row" }}
                          justifyContent="space-between"
                          alignItems={{ xs: "flex-start", sm: "center" }}
                          spacing={1.5}
                        >
                          <Box>
                            <Typography variant="subtitle1">
                              {token.name}
                            </Typography>
                            <Typography
                              variant="caption"
                              color="text.secondary"
                            >
                              {tokenKind} • Prefix {token.token_prefix} •
                              created{" "}
                              {new Date(token.created_at).toLocaleString()} •
                              last used{" "}
                              {token.last_used_at
                                ? new Date(token.last_used_at).toLocaleString()
                                : "never"}
                            </Typography>
                          </Box>
                          <Stack direction="row" spacing={1}>
                            {revoked && (
                              <Chip
                                size="small"
                                color="error"
                                label="Revoked"
                              />
                            )}
                            {expired && !revoked && (
                              <Chip
                                size="small"
                                color="warning"
                                label="Expired"
                              />
                            )}
                            {!revoked && !expired && (
                              <Chip
                                size="small"
                                color="success"
                                label="Active"
                              />
                            )}
                          </Stack>
                        </Stack>
                        <Stack
                          direction="row"
                          spacing={1}
                          flexWrap="wrap"
                          useFlexGap
                          sx={{ mt: 1.2 }}
                        >
                          {scopes.map((scope) => (
                            <Chip
                              key={scope}
                              size="small"
                              variant="outlined"
                              label={scope}
                            />
                          ))}
                        </Stack>
                        <Stack
                          direction="row"
                          justifyContent="space-between"
                          alignItems="center"
                          sx={{ mt: 1.5 }}
                        >
                          <Typography variant="caption" color="text.secondary">
                            Expires{" "}
                            {token.expires_at
                              ? new Date(token.expires_at).toLocaleString()
                              : "never"}
                          </Typography>
                          <Button
                            size="small"
                            color="error"
                            onClick={() => revokeApiToken(token.id)}
                          >
                            {revoked ? "Delete" : "Revoke"}
                          </Button>
                        </Stack>
                      </Box>
                    );
                  })
                )}
              </Box>
            </Box>
          </Box>
        </Box>
      </Paper>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          <Stack spacing={0.75}>
            <Typography
              component="span"
              display="block"
              variant="overline"
              color="primary.main"
            >
              New connection
            </Typography>
            <Typography component="span" display="block" variant="h5">
              Add API provider
            </Typography>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2.25} sx={{ mt: 1 }}>
            <FormControl fullWidth>
              <InputLabel>Provider</InputLabel>
              <Select
                label="Provider"
                value={form.provider}
                onChange={(event) =>
                  setForm({ ...initialForm, provider: event.target.value })
                }
              >
                {providers.map((provider) => (
                  <MenuItem key={provider.id} value={provider.id}>
                    {provider.name}
                  </MenuItem>
                ))}
              </Select>
              {selectedProvider && (
                <FormHelperText>{selectedProvider.description}</FormHelperText>
              )}
            </FormControl>
            {setup && (
              <Box className="provider-setup-guide">
                <Typography component="h3" variant="subtitle2">
                  How to connect {selectedProvider?.name || "this provider"}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {setup.title}
                </Typography>
                <ol>
                  {setup.steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
                {setup.url && (
                  <Button
                    component="a"
                    href={setup.url}
                    target="_blank"
                    rel="noreferrer"
                    size="small"
                    variant="outlined"
                    endIcon={<LaunchRoundedIcon />}
                    aria-label={`${setup.linkLabel} (opens in a new tab)`}
                  >
                    {setup.linkLabel}
                  </Button>
                )}
              </Box>
            )}
            <TextField
              label="Connection label (optional)"
              value={form.label}
              onChange={(event) =>
                setForm({ ...form, label: event.target.value })
              }
              placeholder="Auto-filled when blank"
              helperText="Leave blank to auto-fill a unique label."
            />
            {isCodex && (
              <Box className="provider-setup-guide">
                <Typography component="h3" variant="subtitle2">
                  Connect without Codex CLI
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Button
                    variant="contained"
                    onClick={startCodexDeviceLogin}
                    disabled={codexDeviceBusy}
                    startIcon={
                      codexDeviceBusy ? (
                        <CircularProgress size={16} color="inherit" />
                      ) : null
                    }
                  >
                    Start Codex device login
                  </Button>
                  <Button
                    variant="outlined"
                    onClick={startCodexBrowserLogin}
                    disabled={codexDeviceBusy}
                  >
                    Start browser login fallback
                  </Button>
                  {codexDeviceFlow && (
                    <Button
                      variant="outlined"
                      onClick={pollCodexDeviceLogin}
                      disabled={codexDeviceBusy}
                    >
                      I authorized it - check now
                    </Button>
                  )}
                </Stack>
                {codexDeviceFlow && (
                  <Stack spacing={1} sx={{ mt: 1.5 }}>
                    <Typography variant="body2">
                      Open{" "}
                      <a
                        href={
                          codexDeviceFlow.verification_uri_complete ||
                          codexDeviceFlow.verification_uri
                        }
                        target="_blank"
                        rel="noreferrer"
                      >
                        {codexDeviceFlow.verification_uri}
                      </a>{" "}
                      and enter:
                    </Typography>
                    <Typography
                      variant="h5"
                      component="code"
                      sx={{ letterSpacing: ".08em" }}
                    >
                      {codexDeviceFlow.user_code}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Expires at{" "}
                      {new Date(codexDeviceFlow.expires_at).toLocaleString()}.
                    </Typography>
                  </Stack>
                )}
                {codexBrowserFlow && (
                  <Stack spacing={1} sx={{ mt: 1.5 }}>
                    <Button
                      component="a"
                      href={codexBrowserFlow.authorization_url}
                      target="_blank"
                      rel="noreferrer"
                      size="small"
                      variant="outlined"
                      endIcon={<LaunchRoundedIcon />}
                    >
                      Open OpenAI browser login
                    </Button>
                    <Typography variant="caption" color="text.secondary">
                      When your browser lands on a localhost error page, copy
                      the full address bar URL and paste it here. The one-time
                      code is exchanged server-side.
                    </Typography>
                    <TextField
                      label="OpenAI localhost callback URL"
                      value={codexCallback}
                      onChange={(event) => setCodexCallback(event.target.value)}
                      placeholder="http://localhost:1455/auth/callback?code=…&state=…"
                      multiline
                      minRows={2}
                    />
                    <Button
                      variant="contained"
                      onClick={completeCodexBrowserLogin}
                      disabled={codexDeviceBusy || !codexCallback.trim()}
                    >
                      Complete browser login
                    </Button>
                  </Stack>
                )}
                {codexDeviceStatus && (
                  <Alert severity="info" sx={{ mt: 1.5 }}>
                    {codexDeviceStatus}
                  </Alert>
                )}
              </Box>
            )}
            <TextField
              label={
                isCodex
                  ? "Manual OAuth token bundle fallback"
                  : isCustom
                    ? "Secret / API key"
                    : "API key"
              }
              value={form.api_key}
              type="password"
              multiline={isCodex}
              minRows={isCodex ? 3 : undefined}
              onChange={(event) =>
                setForm({ ...form, api_key: event.target.value })
              }
              placeholder={setup?.keyPlaceholder}
              helperText={
                isCustom
                  ? "Inserted into the auth header template as {api_key}; never put secrets in URLs."
                  : isCodex
                    ? "Optional fallback only. Prefer device login above; pasted JSON is still encrypted at rest."
                    : `Use the ${setup?.title || "key"} described above.`
              }
            />
            <TextField
              label="Base URL override"
              value={form.base_url}
              onChange={(event) =>
                setForm({ ...form, base_url: event.target.value })
              }
              placeholder={
                isCustom
                  ? "https://api.example.com"
                  : "Optional -- provider default will be used"
              }
              required={isCustom}
            />
            {isCustom && (
              <Stack spacing={2.25}>
                <Typography className="dialog-section-label">
                  Custom request
                </Typography>
                <FormControl fullWidth>
                  <InputLabel>HTTP method</InputLabel>
                  <Select
                    label="HTTP method"
                    value={form.custom_method}
                    onChange={(event) =>
                      setForm({ ...form, custom_method: event.target.value })
                    }
                  >
                    <MenuItem value="GET">GET</MenuItem>
                    <MenuItem value="POST">POST</MenuItem>
                  </Select>
                </FormControl>
                <TextField
                  label="Path"
                  value={form.custom_path}
                  onChange={(event) =>
                    setForm({ ...form, custom_path: event.target.value })
                  }
                  placeholder="/v1/billing"
                  required
                />
                <TextField
                  label="Auth header name"
                  value={form.custom_auth_header_name}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      custom_auth_header_name: event.target.value,
                    })
                  }
                />
                <TextField
                  label="Auth header template"
                  value={form.custom_auth_header_template}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      custom_auth_header_template: event.target.value,
                    })
                  }
                  helperText="Use {api_key} where the encrypted secret should be inserted."
                />
                <Typography className="dialog-section-label">
                  Metric extraction
                </Typography>
                <TextField
                  label="Metric label"
                  value={form.custom_metric_label}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      custom_metric_label: event.target.value,
                    })
                  }
                />
                <TextField
                  label="JSON path"
                  value={form.custom_metric_path}
                  onChange={(event) =>
                    setForm({ ...form, custom_metric_path: event.target.value })
                  }
                  helperText="Supports simple paths such as $.credits.remaining and $.items[0].usage."
                />
                <TextField
                  label="Unit"
                  value={form.custom_metric_unit}
                  onChange={(event) =>
                    setForm({ ...form, custom_metric_unit: event.target.value })
                  }
                />
                <TextField
                  label="Maximum JSON path (optional)"
                  value={form.custom_metric_maximum_path}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      custom_metric_maximum_path: event.target.value,
                    })
                  }
                />
              </Stack>
            )}
            {testError && (
              <Alert severity="error">Test failed: {testError}</Alert>
            )}
            {testResult && (
              <Alert severity="success">
                Test succeeded: {testResult.summary}
                <br />
                {(testResult.metrics || [])
                  .map(
                    (metric) =>
                      `${metric.label}: ${metric.value ?? "-"}${metric.unit ? ` ${metric.unit}` : ""}`,
                  )
                  .join(" · ")}
              </Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3, flexWrap: "wrap" }}>
          <Button
            color="inherit"
            onClick={() => setOpen(false)}
            disabled={testing || saving}
          >
            Cancel
          </Button>
          <Button
            onClick={testConnection}
            disabled={testDisabled}
            startIcon={testing ? <CircularProgress size={16} /> : null}
          >
            {testing ? "Testing…" : "Test connection"}
          </Button>
          <Button
            variant="contained"
            onClick={submit}
            disabled={saveDisabled}
            startIcon={
              saving ? <CircularProgress size={16} color="inherit" /> : null
            }
          >
            {saving ? "Saving…" : "Save provider"}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={manualExtensionDialogOpen}
        onClose={() => {
          if (!apiTokenSaving) setManualExtensionDialogOpen(false);
        }}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          <Stack spacing={0.75}>
            <Typography
              component="span"
              display="block"
              variant="overline"
              color="primary.main"
            >
              Browser extension
            </Typography>
            <Typography component="span" display="block" variant="h5">
              Manual extension setup
            </Typography>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2.25} sx={{ mt: 1 }}>
            <Box className="homepage-guide api-token-guide">
              <Typography variant="body2" color="text.secondary">
                Use this fallback when one-click setup cannot reach the
                extension. For one-click setup, paste the dashboard URL into the
                extension Options page first; manual setup uses the same URL
                plus a token you copy yourself. The generated token uses the
                extension preset and the full token is shown once.
              </Typography>
              <ol>
                <li>Create a token with the browser extension preset.</li>
                <li>Copy it immediately; the full token is shown once.</li>
                <li>
                  Copy the dashboard URL below, then open the extension options
                  page and paste it in. The extension appends{" "}
                  <code>/api/v1</code> automatically.
                </li>
                <li>Paste the token as the extension bearer token and save.</li>
              </ol>
            </Box>
            <Box className="extension-url-copy">
              <Stack
                direction={{ xs: "column", sm: "row" }}
                spacing={1}
                alignItems="flex-start"
              >
                <TextField
                  fullWidth
                  label="Dashboard URL"
                  value={extensionUrl}
                  InputProps={{ readOnly: true }}
                  onFocus={(event) => event.target.select()}
                  helperText="The extension appends /api/v1 automatically."
                />
                <Button
                  variant="outlined"
                  onClick={copyExtensionUrl}
                  startIcon={
                    extensionUrlCopied ? (
                      <CheckRoundedIcon />
                    ) : (
                      <ContentCopyRoundedIcon />
                    )
                  }
                  sx={{ flex: "0 0 auto" }}
                >
                  {extensionUrlCopied ? "Copied" : "Copy"}
                </Button>
              </Stack>
            </Box>
            <ApiTokenCreationForm
              form={apiTokenForm}
              onChange={setApiTokenForm}
              onToggleScope={toggleApiTokenScope}
              showScopes={false}
              createdToken={createdApiToken}
              copied={apiTokenCopied}
              saving={apiTokenSaving}
              submitLabel="Create extension token"
              resultLabel="Copy this extension token now; it will not be shown again."
              onSubmit={createExtensionApiToken}
              onCopy={copyCreatedApiToken}
              onReset={() =>
                setApiTokenForm({
                  ...initialApiTokenForm,
                  scopes: [...initialApiTokenForm.scopes],
                })
              }
            />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button
            color="inherit"
            onClick={() => setManualExtensionDialogOpen(false)}
            disabled={apiTokenSaving}
          >
            Close
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={genericTokenDialogOpen}
        onClose={() => {
          if (!genericApiTokenSaving) setGenericTokenDialogOpen(false);
        }}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          <Stack spacing={0.75}>
            <Typography
              component="span"
              display="block"
              variant="overline"
              color="primary.main"
            >
              Integration tokens
            </Typography>
            <Typography component="span" display="block" variant="h5">
              Add scoped token
            </Typography>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2.25} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Create a standalone token for scripts, widgets, or other clients.
              Pick only the permissions that client needs; boring, responsible,
              regrettably correct.
            </Typography>
            <ApiTokenCreationForm
              form={genericApiTokenForm}
              onChange={setGenericApiTokenForm}
              onToggleScope={toggleGenericApiTokenScope}
              createdToken={createdGenericApiToken}
              copied={genericApiTokenCopied}
              saving={genericApiTokenSaving}
              onSubmit={createGenericApiToken}
              onCopy={copyCreatedGenericApiToken}
              onReset={() =>
                setGenericApiTokenForm({
                  ...initialGenericApiTokenForm,
                  scopes: [...initialGenericApiTokenForm.scopes],
                })
              }
            />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button
            color="inherit"
            onClick={() => setGenericTokenDialogOpen(false)}
            disabled={genericApiTokenSaving}
          >
            Close
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={Boolean(credentialTarget)}
        onClose={closeCredentialDialog}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          <Stack spacing={0.75}>
            <Typography
              component="span"
              display="block"
              variant="overline"
              color="primary.main"
            >
              Credential replacement
            </Typography>
            <Typography component="span" display="block" variant="h5">
              {credentialTarget?.label}
            </Typography>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="info">
              The current credential is stored encrypted and only shown as {" "}
              <code>{credentialTarget?.api_key_masked || "••••••••"}</code>.
              Paste or complete a new credential below; the old token is never
              revealed and is overwritten after save.
            </Alert>
            {credentialTarget?.provider === "codex" && (
              <Box className="homepage-guide api-token-guide">
                <Typography variant="body2" color="text.secondary">
                  For expired Codex OAuth tokens, reauthenticate this exact
                  provider row with device login or browser login. The backend
                  stores the refreshed OAuth secret directly; browser JavaScript
                  never receives the access or refresh token.
                </Typography>
                <Stack
                  direction="row"
                  spacing={1}
                  flexWrap="wrap"
                  useFlexGap
                  sx={{ mt: 1.5 }}
                >
                  <Button
                    variant="outlined"
                    onClick={startCodexDeviceLogin}
                    disabled={codexDeviceBusy}
                  >
                    Start Codex device reauth
                  </Button>
                  <Button
                    variant="outlined"
                    onClick={startCodexBrowserLogin}
                    disabled={codexDeviceBusy}
                  >
                    Start browser reauth
                  </Button>
                </Stack>
                {codexDeviceFlow && (
                  <Stack spacing={1.25} sx={{ mt: 1.5 }}>
                    <Alert severity="info">
                      Visit {" "}
                      <a
                        href={codexDeviceFlow.verification_uri_complete || codexDeviceFlow.verification_uri}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {codexDeviceFlow.verification_uri}
                      </a>{" "}
                      and enter code <strong>{codexDeviceFlow.user_code}</strong>.
                    </Alert>
                    <Button
                      variant="contained"
                      onClick={pollCodexDeviceLogin}
                      disabled={codexDeviceBusy}
                    >
                      {codexDeviceBusy ? "Checking…" : "I authorized Codex"}
                    </Button>
                  </Stack>
                )}
                {codexBrowserFlow && (
                  <Stack spacing={1.25} sx={{ mt: 1.5 }}>
                    <Button
                      component="a"
                      href={codexBrowserFlow.authorization_url}
                      target="_blank"
                      rel="noreferrer"
                      variant="outlined"
                    >
                      Open Codex browser login
                    </Button>
                    <TextField
                      label="Callback URL after login"
                      value={codexCallback}
                      onChange={(event) => setCodexCallback(event.target.value)}
                      placeholder="http://localhost:1455/auth/callback?code=…&state=…"
                      multiline
                      minRows={2}
                    />
                    <Button
                      variant="contained"
                      onClick={completeCodexBrowserLogin}
                      disabled={codexDeviceBusy || !codexCallback.trim()}
                    >
                      {codexDeviceBusy ? "Completing…" : "Complete browser reauth"}
                    </Button>
                  </Stack>
                )}
                {codexDeviceStatus && (
                  <Alert severity="info" sx={{ mt: 1.5 }}>
                    {codexDeviceStatus}
                  </Alert>
                )}
              </Box>
            )}
            <TextField
              label={
                credentialTarget?.provider === "codex"
                  ? "New Codex OAuth token JSON (manual fallback)"
                  : "New provider token"
              }
              type="password"
              value={credentialValue}
              onChange={(event) => setCredentialValue(event.target.value)}
              placeholder={
                PROVIDER_SETUP[credentialTarget?.provider]?.keyPlaceholder ||
                "Paste the replacement token"
              }
              helperText="Leave blank unless you are manually replacing the provider secret. The existing value is intentionally unavailable."
              multiline={credentialTarget?.provider === "codex"}
              minRows={credentialTarget?.provider === "codex" ? 3 : undefined}
            />
            {testError && <Alert severity="error">{testError}</Alert>}
            {credentialStatus && (
              <Alert severity="success">{credentialStatus}</Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button
            color="inherit"
            onClick={closeCredentialDialog}
            disabled={credentialSaving || codexDeviceBusy}
          >
            Close
          </Button>
          <Button
            variant="contained"
            onClick={replaceCredential}
            disabled={credentialSaving || !credentialValue.trim()}
            startIcon={
              credentialSaving ? (
                <CircularProgress size={16} color="inherit" />
              ) : null
            }
          >
            {credentialSaving ? "Replacing…" : "Replace credential"}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={Boolean(thresholdDialog)}
        onClose={() => setThresholdDialog(null)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          <Stack spacing={0.75}>
            <Typography
              component="span"
              display="block"
              variant="overline"
              color="primary.main"
            >
              Alert thresholds
            </Typography>
            <Typography component="span" display="block" variant="h5">
              {thresholdDialog?.label}
            </Typography>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Pick a metric and set warning, critical, and exhausted limits. The
              alert direction is handled for you - a "remaining" metric alerts
              when it drops to the threshold, while a "usage" metric alerts when
              it climbs to it. Leave limits blank to skip a level.
            </Typography>
            {thresholdForm.length === 0 && (
              <Typography variant="body2" color="text.secondary">
                No thresholds configured - this provider won't surface alerts.
              </Typography>
            )}
            {thresholdForm.map((rule, index) => {
              const spec = thresholdProviderMetrics.find(
                (entry) => entry.metric === rule.metric,
              );
              const unit = spec?.unit || "";
              const directionLabel =
                spec?.direction === "decreasing"
                  ? "alerts when value drops to threshold"
                  : spec?.direction === "increasing"
                    ? "alerts when value reaches threshold"
                    : "";
              return (
                <Paper key={index} variant="outlined" sx={{ p: 1.5 }}>
                  <Stack spacing={1.25}>
                    {thresholdProviderMetrics.length > 0 ? (
                      <FormControl size="small" fullWidth>
                        <InputLabel>Metric</InputLabel>
                        <Select
                          label="Metric"
                          value={rule.metric}
                          onChange={(event) =>
                            selectThresholdMetric(index, event.target.value)
                          }
                        >
                          {thresholdProviderMetrics.map((entry) => (
                            <MenuItem key={entry.metric} value={entry.metric}>
                              {entry.label}
                              {entry.unit ? ` (${entry.unit})` : ""}
                            </MenuItem>
                          ))}
                        </Select>
                        {directionLabel && (
                          <FormHelperText>{directionLabel}</FormHelperText>
                        )}
                      </FormControl>
                    ) : (
                      <Stack direction="row" spacing={1}>
                        <TextField
                          size="small"
                          label="Metric label"
                          value={rule.metric}
                          onChange={(event) =>
                            updateThresholdRule(index, {
                              metric: event.target.value,
                            })
                          }
                          placeholder="usage_percent"
                          fullWidth
                        />
                        <FormControl size="small" sx={{ minWidth: 140 }}>
                          <InputLabel>Direction</InputLabel>
                          <Select
                            label="Direction"
                            value={rule.direction}
                            onChange={(event) =>
                              updateThresholdRule(index, {
                                direction: event.target.value,
                              })
                            }
                          >
                            <MenuItem value="increasing">
                              Increasing (≥)
                            </MenuItem>
                            <MenuItem value="decreasing">
                              Decreasing (≤)
                            </MenuItem>
                          </Select>
                        </FormControl>
                      </Stack>
                    )}
                    <Stack direction="row" spacing={1}>
                      <TextField
                        size="small"
                        label={`Warning${unit ? ` (${unit})` : ""}`}
                        type="number"
                        value={rule.warning}
                        onChange={(event) =>
                          updateThresholdRule(index, {
                            warning: event.target.value,
                          })
                        }
                      />
                      <TextField
                        size="small"
                        label={`Critical${unit ? ` (${unit})` : ""}`}
                        type="number"
                        value={rule.critical}
                        onChange={(event) =>
                          updateThresholdRule(index, {
                            critical: event.target.value,
                          })
                        }
                      />
                      <TextField
                        size="small"
                        label={`Exhausted${unit ? ` (${unit})` : ""}`}
                        type="number"
                        value={rule.exhausted}
                        onChange={(event) =>
                          updateThresholdRule(index, {
                            exhausted: event.target.value,
                          })
                        }
                      />
                    </Stack>
                    <Stack direction="row" justifyContent="flex-end">
                      <Button
                        size="small"
                        color="error"
                        onClick={() => removeThresholdRule(index)}
                      >
                        Remove
                      </Button>
                    </Stack>
                  </Stack>
                </Paper>
              );
            })}
            <Button
              variant="outlined"
              startIcon={<AddRoundedIcon />}
              onClick={addThresholdRule}
            >
              Add threshold rule
            </Button>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button color="inherit" onClick={() => setThresholdDialog(null)}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={saveThresholds}
            disabled={thresholdSaving}
            startIcon={
              thresholdSaving ? (
                <CircularProgress size={16} color="inherit" />
              ) : null
            }
          >
            {thresholdSaving ? "Saving…" : "Save thresholds"}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={Boolean(extensionReplacement)}
        onClose={() => {
          if (!extensionConnectBusy) setExtensionReplacement(null);
        }}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>Replace existing extension connection?</DialogTitle>
        <DialogContent>
          <Typography>
            This extension is already connected to another Usage Dashboard.
            Replace that connection with this dashboard?
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button
            color="inherit"
            onClick={() => setExtensionReplacement(null)}
            disabled={extensionConnectBusy}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            color="warning"
            onClick={confirmExtensionReplacement}
            disabled={extensionConnectBusy}
            startIcon={
              extensionConnectBusy ? (
                <CircularProgress size={16} color="inherit" />
              ) : null
            }
          >
            {extensionConnectBusy ? "Replacing…" : "Replace connection"}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={Boolean(deleteTarget)}
        onClose={() => {
          if (!deleting) setDeleteTarget(null);
        }}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>Remove provider?</DialogTitle>
        <DialogContent>
          <Typography>
            This permanently deletes <strong>{deleteTarget?.label}</strong> (
            {deleteTarget?.provider}) and its usage history. This cannot be
            undone.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button
            color="inherit"
            onClick={() => setDeleteTarget(null)}
            disabled={deleting}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={confirmDelete}
            disabled={deleting}
            startIcon={
              deleting ? (
                <CircularProgress size={16} color="inherit" />
              ) : (
                <DeleteOutlineRoundedIcon />
              )
            }
          >
            {deleting ? "Deleting…" : "Delete provider"}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
