// @vitest-environment jsdom
import { act, createElement, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import UpdateNotification from "./UpdateNotification.jsx";
import useUpdateStatus from "../lib/useUpdateStatus.js";
import { CACHE_KEY, RETRY_KEY, CACHE_MS, checkRelease, cachedRelease } from "../lib/releaseCheck.js";

vi.mock("../lib/releaseCheck.js", async (original) => ({
  ...await original(), checkRelease: vi.fn(), cachedRelease: vi.fn(),
}));
const NOW = Date.parse("2026-11-12T12:00:00Z");
const release = {
  checkedAt: NOW,
  release: {
    tag_name: "v1.3.0", html_url: "https://github.com/Skulldorom/usage-dashboard/releases/tag/v1.3.0",
    url: "https://api.github.com/repos/Skulldorom/usage-dashboard/releases/123",
    draft: false, prerelease: false, published_at: "2026-11-11T12:00:00Z",
  },
};
const update = { current_version: "v1.2.0", release };
let root, container;
async function render(props = {}) {
  await act(async () => root.render(createElement(UpdateNotification, { update, ...props })));
}
function Harness({ authenticated = true, version = "v1.2.0" }) {
  return createElement(UpdateNotification, { update: useUpdateStatus(authenticated, version) });
}
async function mountHarness(props = {}, strict = false) {
  await act(async () => root.render(strict
    ? createElement(StrictMode, null, createElement(Harness, props))
    : createElement(Harness, props)));
}
async function advance(ms) { await act(async () => vi.advanceTimersByTimeAsync(ms)); }
function hasNotice() { return container.querySelector(".update-notification") !== null; }
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  vi.stubEnv("VITE_APP_VERSION", "v1.2.0");
  localStorage.clear();
  checkRelease.mockReset().mockResolvedValue(release);
  cachedRelease.mockReset().mockReturnValue(null);
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.restoreAllMocks(); vi.unstubAllEnvs(); vi.useRealTimers();
});
describe("quiet version footer", () => {
  it("shows the installed version before any release check", async () => {
    await render({ update: { current_version: "v1.2.0", release: null } });
    expect(container.textContent).toBe("v1.2.0");
    expect(container.querySelector(".version-indicator")).toBeNull();
    expect(hasNotice()).toBe(false);
  });
  it("keeps a verified update accessible with a trusted external link", async () => {
    await render();
    expect(container.textContent).toContain("Update available");
    expect(container.querySelector(".update-version-installed").textContent).toBe("v1.2.0");
    expect(container.querySelector(".update-version-latest").textContent).toBe("v1.3.0");
    const link = container.querySelector("a");
    expect(link.href).toBe(release.release.html_url);
    expect(link.target).toBe("_blank");
    expect(link.rel).toBe("noopener noreferrer");
    const close = container.querySelector('[aria-label="Dismiss update v1.3.0"]');
    close.focus();
    expect(document.activeElement).toBe(close);
  });
  it("preserves the mobile layout for long version labels", async () => {
    const tag = "v1.3." + "2".repeat(80);
    await render({ compact: true, update: { ...update, release: {
      ...release, release: { ...release.release, tag_name: tag, html_url: release.release.html_url.replace("v1.3.0", tag) },
    } } });
    expect(container.querySelector(".version-footer-mobile")).not.toBeNull();
    expect(container.querySelector(".update-version-latest").textContent).toBe(tag);
  });
  it("keeps development alternatives separate from newer-version claims", async () => {
    const version = "v0.0.0-dev.abcdef1234567";
    vi.stubEnv("VITE_APP_VERSION", version);
    await render({ update: { ...update, current_version: version } });
    expect(container.textContent).toContain("Stable release available");
    expect(container.textContent).toContain("alternative");
    expect(container.querySelector("code").textContent).toBe("abcdef1");
    expect(container.textContent).not.toContain("→");
    expect(container.querySelector(".update-new-badge")).toBeNull();
  });
  it.each(["v1.3.0", "v2.0.0", "unknown", "v0.0.0", "v1.1.0"])("quietly suppresses updates for backend %s", async (version) => {
    await render({ update: { ...update, current_version: version } });
    expect(hasNotice()).toBe(false);
    expect(container.querySelector(".version-diagnostic")).toBeNull();
  });
  it("never shows expired or malformed data", async () => {
    await render();
    expect(hasNotice()).toBe(true);
    await advance(CACHE_MS);
    await render();
    expect(hasNotice()).toBe(false);
    expect(container.textContent).toBe("v1.2.0");
    await render({ update: { ...update, release: { ...release, checkedAt: Date.now(), release: { ...release.release, draft: true } } } });
    expect(hasNotice()).toBe(false);
  });
  it("persists dismissal across remounts and allows a different release", async () => {
    await render();
    await act(async () => container.querySelector('[aria-label^="Dismiss"]').click());
    expect(hasNotice()).toBe(false);
    await act(async () => root.render(null));
    await render();
    expect(hasNotice()).toBe(false);
    await render({ update: { ...update, release: { ...release, release: {
      ...release.release, tag_name: "v1.4.0", html_url: release.release.html_url.replace("v1.3.0", "v1.4.0"),
    } } } });
    expect(hasNotice()).toBe(true);
  });
  it("respects legacy dismissals and cross-tab dismissal events", async () => {
    localStorage.setItem("usage-dashboard:dismissed-update", "v1.3.0");
    await render();
    expect(hasNotice()).toBe(false);
    await render({ update: { ...update, release: { ...release, release: {
      ...release.release, tag_name: "v1.4.0", html_url: release.release.html_url.replace("v1.3.0", "v1.4.0"),
    } } } });
    expect(hasNotice()).toBe(true);
    localStorage.setItem("usage-dashboard:dismissed-update:update_available", "v1.4.0");
    await act(async () => window.dispatchEvent(new StorageEvent("storage")));
    expect(hasNotice()).toBe(false);
  });
  it("copies real metadata and preserves dismissal when storage fails", async () => {
    const writeText = vi.fn().mockResolvedValue();
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    await render();
    await act(async () => container.querySelector('[aria-label="Copy full version metadata"]').click());
    expect(writeText).toHaveBeenCalledWith("v1.2.0");
    expect(container.querySelector('[role="status"]').textContent).toBe("Version copied");
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    await act(async () => container.querySelector('[aria-label^="Dismiss"]').click());
    expect(hasNotice()).toBe(false);
  });
});
describe("dashboard release lifecycle", () => {
  it("delays the initial authenticated check and survives Strict Mode", async () => {
    await mountHarness({}, true);
    await advance(2499);
    expect(checkRelease).not.toHaveBeenCalled();
    await advance(1);
    expect(checkRelease).toHaveBeenCalledOnce();
    expect(hasNotice()).toBe(true);
    await advance(CACHE_MS * 3);
    expect(hasNotice()).toBe(false);
    expect(checkRelease).toHaveBeenCalledOnce();
  });
  it("does not check while unauthenticated, then checks after login", async () => {
    await mountHarness({ authenticated: false });
    await advance(5000);
    expect(checkRelease).not.toHaveBeenCalled();
    expect(container.textContent).toBe("");
    await mountHarness();
    await advance(2500);
    expect(checkRelease).toHaveBeenCalledOnce();
  });
  it("ignores renders and checks when a hidden dashboard becomes visible", async () => {
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    await mountHarness();
    await advance(2500);
    expect(checkRelease).not.toHaveBeenCalled();
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    await act(async () => document.dispatchEvent(new Event("visibilitychange")));
    expect(checkRelease).toHaveBeenCalledOnce();
    await mountHarness();
    expect(checkRelease).toHaveBeenCalledOnce();
    await advance(CACHE_MS);
    checkRelease.mockResolvedValue(null);
    await act(async () => document.dispatchEvent(new Event("visibilitychange")));
    expect(checkRelease).toHaveBeenCalledTimes(2);
    expect(hasNotice()).toBe(false);
    expect(container.textContent).toBe("v1.2.0");
  });
  it("synchronizes a result or failure from another tab without fetching", async () => {
    await mountHarness();
    cachedRelease.mockReturnValue(release);
    await act(async () => window.dispatchEvent(new StorageEvent("storage", { key: CACHE_KEY })));
    expect(hasNotice()).toBe(true);
    cachedRelease.mockReturnValue(null);
    await act(async () => window.dispatchEvent(new StorageEvent("storage", { key: RETRY_KEY })));
    expect(hasNotice()).toBe(false);
    expect(checkRelease).not.toHaveBeenCalled();
  });
  it("keeps a synchronized verified release when a pending lock attempt finishes with null", async () => {
    let finish;
    checkRelease.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    await mountHarness();
    await advance(2500);
    expect(checkRelease).toHaveBeenCalledOnce();
    expect(hasNotice()).toBe(false);

    // Another tab publishes while this tab's unavailable-lock result is still pending.
    cachedRelease.mockReturnValue(release);
    await act(async () => window.dispatchEvent(new StorageEvent("storage", { key: CACHE_KEY })));
    expect(hasNotice()).toBe(true);
    await act(async () => finish(null));
    expect(hasNotice()).toBe(true);
    expect(checkRelease).toHaveBeenCalledOnce();

    // Reusing the cache must not extend the original verification deadline.
    await advance(CACHE_MS - 2500);
    expect(hasNotice()).toBe(false);
    expect(checkRelease).toHaveBeenCalledOnce();
  });
  it.each(["expired", "invalidated by failure"])("does not revive a synchronized release %s before a pending null result", async (reason) => {
    let finish;
    checkRelease.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    await mountHarness();
    await advance(2500);
    cachedRelease.mockReturnValue(release);
    await act(async () => window.dispatchEvent(new StorageEvent("storage", { key: CACHE_KEY })));
    expect(hasNotice()).toBe(true);

    cachedRelease.mockReturnValue(null);
    if (reason === "expired") await advance(CACHE_MS - 2500);
    else await act(async () => window.dispatchEvent(new StorageEvent("storage", { key: RETRY_KEY })));
    expect(hasNotice()).toBe(false);
    await act(async () => finish(null));
    expect(hasNotice()).toBe(false);
    expect(container.textContent).toBe("v1.2.0");
  });
  it("aborts on logout, ignores late responses, and clears the notice", async () => {
    let finish;
    checkRelease.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    await mountHarness();
    await advance(2500);
    const signal = checkRelease.mock.calls[0][0];
    await mountHarness({ authenticated: false });
    expect(signal.aborted).toBe(true);
    await act(async () => finish(release));
    expect(container.textContent).toBe("");
  });
  it("cancels the initial delay on unmount", async () => {
    await mountHarness();
    await act(async () => root.render(null));
    await advance(5000);
    expect(checkRelease).not.toHaveBeenCalled();
  });
  it("suppresses unknown and changed backend metadata without inventing a version", async () => {
    await mountHarness({ version: undefined });
    await advance(2500);
    await mountHarness({ version: null });
    expect(hasNotice()).toBe(false);
    expect(container.textContent).toBe("Version unknown");
    await mountHarness({ version: "v1.1.0" });
    expect(hasNotice()).toBe(false);
    expect(container.textContent).toBe("v1.1.0");
  });
});
