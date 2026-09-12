import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const settingsSource = readFileSync(resolve(currentDir, "../pages/SettingsPage.jsx"), "utf8");
const apiSource = readFileSync(resolve(currentDir, "../api.js"), "utf8");

const functionBody = (name) => {
  const start = settingsSource.indexOf(`async function ${name}()`);
  expect(start).toBeGreaterThan(-1);
  const nextFunction = settingsSource.indexOf("\n  async function", start + 1);
  const nextConst = settingsSource.indexOf("\n  const ", start + 1);
  const end = Math.min(...[nextFunction, nextConst].filter((index) => index > start));
  return settingsSource.slice(start, end);
};

describe("Codex browser OAuth settings flow", () => {
  it("keeps Connect Codex on browser OAuth without targeting an existing config", () => {
    expect(settingsSource).toContain("Connect Codex");
    expect(apiSource).toContain("startCodexBrowserOAuth: (payload = {}) => request('/codex/oauth/browser/start'");
    const startBody = functionBody("startCodexBrowserLogin");
    expect(startBody).toContain("api.startCodexBrowserOAuth");
    expect(startBody).toContain("label: credentialTarget ? credentialTarget.label : form.label.trim() || null");
    expect(startBody).toContain("config_id: credentialTarget?.id || null");
    expect(startBody).toContain('window.open(\n      "about:blank",\n      "codex_oauth"');
    expect(startBody).toContain("centeredPopupFeatures(600, 720)");
    expect(startBody).toContain("popup.location.href = flow.authorization_url");
    expect(startBody).not.toContain('window.open(flow.authorization_url, "_blank"');
    const addProviderSection = settingsSource.slice(settingsSource.indexOf("Connect without Codex CLI"), settingsSource.indexOf("Manual OAuth token bundle fallback"));
    expect(addProviderSection).toContain("Connect Codex");
    expect(addProviderSection).toContain("onClick={startCodexBrowserLogin}");
    expect(addProviderSection).not.toContain("credentialTarget?.id");
  });

  it("keeps Reconnect Codex targeted at the exact existing provider config", () => {
    const credentialDialogSection = settingsSource.slice(settingsSource.indexOf("Credential replacement"), settingsSource.indexOf("DialogActions", settingsSource.indexOf("Credential replacement")));
    expect(credentialDialogSection).toContain("Reconnect Codex");
    expect(credentialDialogSection).toContain("onClick={startCodexBrowserLogin}");
    const startBody = functionBody("startCodexBrowserLogin");
    expect(startBody).toContain("config_id: credentialTarget?.id || null");
    expect(startBody).toContain("label: credentialTarget ? credentialTarget.label");
    const completeBody = functionBody("completeCodexBrowserLogin");
    expect(completeBody).toContain("config_id: credentialTarget?.id || null");
    expect(completeBody).toContain("label: credentialTarget ? credentialTarget.label");
    expect(completeBody).toContain("Codex reauthenticated for ${label}.");
  });

  it("preserves manual callback fallback and reconnect config association", () => {
    const startBody = functionBody("startCodexBrowserLogin");
    expect(startBody).toContain("automaticCaptureAvailable");
    expect(startBody).toContain("Waiting for browser authorization… Automatic callback capture is unavailable here. Complete login in the popup, then paste the localhost callback URL below.");
    expect(startBody).toContain("Popup was blocked. Open or copy the login link below, complete OpenAI login, then paste the localhost callback URL below.");
    const completeBody = functionBody("completeCodexBrowserLogin");
    expect(completeBody).toContain("api.completeCodexBrowserOAuth");
    expect(completeBody).toContain("callback: codexCallback.trim()");
    expect(completeBody).toContain("config_id: credentialTarget?.id || null");
    expect(settingsSource).toContain("OpenAI localhost callback URL");
    expect(settingsSource).toContain("Callback URL after login");
    expect(settingsSource).toContain("Open Codex browser login");
  });

  it("covers automatic status completion cleanup for connect and reconnect", () => {
    const effectStart = settingsSource.indexOf("api.codexBrowserOAuthStatus");
    expect(effectStart).toBeGreaterThan(-1);
    const effectBody = settingsSource.slice(effectStart - 1200, effectStart + 2200);
    expect(effectBody).toContain('result.status === "pending"');
    expect(effectBody).toContain('result.status === "processing"');
    expect(effectBody).toContain('result.status === "completed"');
    expect(effectBody).toContain("setCodexBrowserFlow(null)");
    expect(effectBody).toContain('setCodexCallback("")');
    expect(effectBody).toContain("codexPopupRef.current.close()");
    expect(effectBody).toContain("setOpen(false)");
    expect(effectBody).toContain("setForm(initialForm)");
    expect(effectBody).toContain("await load()");
    expect(effectBody).toContain("credentialTarget ? `Codex reauthenticated for ${label}.` : `Codex connected as ${label}.`");
  });


  it("opens a dedicated centered popup independent of automatic capture", () => {
    const startBody = functionBody("startCodexBrowserLogin");
    const popupOpenIndex = startBody.indexOf('window.open(\n      "about:blank",\n      "codex_oauth"');
    const autoCaptureIndex = startBody.indexOf("const automaticCaptureAvailable");
    expect(popupOpenIndex).toBeGreaterThan(-1);
    expect(autoCaptureIndex).toBeGreaterThan(-1);
    expect(popupOpenIndex).toBeLessThan(autoCaptureIndex);
    expect(startBody).toContain("centeredPopupFeatures(600, 720)");
    expect(settingsSource).toContain("function centeredPopupFeatures(width = 600, height = 720)");
    expect(settingsSource).toContain("left=${left},top=${top}");
  });

  it("keeps localhost automatic capture flow separate from popup opening", () => {
    const startBody = functionBody("startCodexBrowserLogin");
    const effectStart = settingsSource.indexOf("api.codexBrowserOAuthStatus");
    const effectBody = settingsSource.slice(effectStart - 1200, effectStart + 2200);
    expect(startBody).toContain('const isLoopbackDashboard = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);');
    expect(startBody).toContain('const automaticCaptureAvailable = flow.callback_available && isLoopbackDashboard && flow.fallback_reason !== "auto_capture_not_enabled";');
    expect(startBody).toContain('automaticCaptureAvailable\n            ? "Waiting for browser authorization…"');
    expect(effectBody).toContain("codexBrowserFlow.callback_available || !isLoopbackDashboard");
  });

  it("handles blocked popups without removing manual authorization workflow", () => {
    const startBody = functionBody("startCodexBrowserLogin");
    expect(startBody).toContain("if (popup) popup.location.href = flow.authorization_url");
    expect(startBody).toContain("Popup was blocked. Open or copy the login link below, complete OpenAI login, then paste the localhost callback URL below.");
    expect(startBody).not.toContain('window.open(flow.authorization_url, "_blank"');
    expect(settingsSource).toContain('href={codexBrowserFlow.authorization_url}');
    expect(settingsSource).toContain("OpenAI localhost callback URL");
    expect(settingsSource).toContain("Callback URL after login");
  });

  it("closes stale and completed Codex popups only through the stored popup ref", () => {
    const startBody = functionBody("startCodexBrowserLogin");
    const staleCloseIndex = startBody.indexOf("codexPopupRef.current.close()");
    const staleClearIndex = startBody.indexOf("codexPopupRef.current = null", staleCloseIndex);
    const popupOpenIndex = startBody.indexOf('window.open(\n      "about:blank",\n      "codex_oauth"');
    expect(staleCloseIndex).toBeGreaterThan(-1);
    expect(staleClearIndex).toBeGreaterThan(staleCloseIndex);
    expect(popupOpenIndex).toBeGreaterThan(staleClearIndex);
    expect(startBody).toContain("codexPopupRef.current = popup");
    expect(startBody).toContain("if (codexPopupRef.current === popup) {");
    expect(settingsSource).toContain("if (codexPopupRef.current && !codexPopupRef.current.closed) {");
    expect(settingsSource).toContain("codexPopupRef.current = null");
    expect(settingsSource).not.toContain("window.close(");
  });

  it("does not render normal device-code login or reauth controls", () => {
    expect(settingsSource).not.toContain("Start Codex device login");
    expect(settingsSource).not.toContain("Start Codex device reauth");
    expect(settingsSource).not.toContain("I authorized it - check now");
    expect(settingsSource).not.toContain("I authorized Codex");
    expect(settingsSource).not.toContain("startCodexDeviceLogin");
    expect(settingsSource).not.toContain("pollCodexDeviceLogin");
    expect(settingsSource).not.toContain("codexDeviceFlow");
    expect(apiSource).not.toContain("startCodexDeviceOAuth");
    expect(apiSource).not.toContain("pollCodexDeviceOAuth");
  });
});
