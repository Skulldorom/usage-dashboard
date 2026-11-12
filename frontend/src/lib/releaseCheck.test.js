// @vitest-environment jsdom
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

let service;
const NOW = Date.parse("2026-11-12T12:00:00Z");
const payload = {
  tag_name: "v1.3.0", html_url: "https://github.com/Skulldorom/usage-dashboard/releases/tag/v1.3.0",
  url: "https://api.github.com/repos/Skulldorom/usage-dashboard/releases/123",
  draft: false, prerelease: false, published_at: "2026-11-11T12:00:00Z",
};
const response = (body = payload, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "content-type": "application/json" },
});
beforeEach(async () => {
  vi.resetModules();
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  localStorage.clear();
  Object.defineProperty(navigator, "locks", { configurable: true, value: undefined });
  vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => response()));
  service = await import("./releaseCheck.js");
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("verified browser releases", () => {
  it("fetches the fixed official endpoint without any application credentials", async () => {
    localStorage.setItem("usage_dashboard_admin_session_token", "secret");
    const record = await service.checkRelease();
    expect(record).toEqual({ checkedAt: NOW, release: payload });
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch).toHaveBeenCalledWith(service.RELEASE_API, expect.objectContaining({
      credentials: "omit", referrerPolicy: "no-referrer", redirect: "error", cache: "no-store",
      headers: { Accept: "application/vnd.github+json" },
    }));
    expect(JSON.parse(localStorage.getItem(service.CACHE_KEY))).toEqual(record);
  });
  it.each([
    ["v1.2.0", "v1.2.0", "update_available"],
    ["v1.3.0", "v1.3.0", null], ["v2.0.0", "v2.0.0", null],
    ["1.2.0", "v1.2.0", "update_available"],
    ["v0.0.0-dev.abcdef1", "v0.0.0-dev.abcdef1", "stable_release_available"],
    ["v9.0.0-rc.1", "v9.0.0-rc.1", "stable_release_available"],
    ["unknown", "v1.2.0", null], ["v1.2.0", null, null],
    ["v0.0.0", "v0.0.0", null], ["v1.2.0", "v1.1.0", null],
    ["v0.0.0-dev.abcdef1", "v0.0.0-dev.abcdef2", null],
    ["v1.2.0+one", "v1.2.0+two", null],
  ])("compares frontend %s / backend %s safely", async (frontend, backend, expected) => {
    expect(service.releaseNotice(frontend, backend, await service.checkRelease())).toBe(expected);
  });
  it.each([
    null, [], {}, { tag_name: "v0.0.0" }, { tag_name: "v1.03.0" },
    { tag_name: "v1.3.0-rc.1" }, { tag_name: "placeholder" },
    { draft: true }, { draft: null }, { prerelease: true }, { prerelease: undefined },
    { html_url: "https://evil.example/v1.3.0" },
    { html_url: payload.html_url + "?redirect=evil" },
    { html_url: payload.html_url.replace("github.com", "github.com.evil.example") },
    { html_url: payload.html_url.replace("Skulldorom", "other") },
    { url: payload.url.replace("Skulldorom", "other") }, { url: null },
    { published_at: null }, { published_at: "garbage" }, { published_at: "2026-11-13T12:00:00Z" },
    { published_at: "2026-02-30T12:00:00Z" }, { published_at: "2026-11-11T12:00:00" },
  ])("rejects malformed or untrusted metadata %j", async (change) => {
    fetch.mockResolvedValue(response(change === null || Array.isArray(change) || Object.keys(change).length === 0 ? change : { ...payload, ...change }));
    expect(await service.checkRelease()).toBeNull();
    expect(localStorage.getItem(service.CACHE_KEY)).toBeNull();
    expect(console.warn).toHaveBeenCalled();
  });
  it.each([404, 403, 429, 500])("backs off HTTP %s without caching success", async (status) => {
    fetch.mockResolvedValue(response({ message: "secret response content" }, status));
    expect(await service.checkRelease()).toBeNull();
    expect(await service.checkRelease()).toBeNull();
    expect(fetch).toHaveBeenCalledOnce();
    expect(console.warn).toHaveBeenCalledWith(`[updates] GitHub release check failed: HTTP ${status}`);
    expect(localStorage.getItem(service.CACHE_KEY)).toBeNull();
    await vi.advanceTimersByTimeAsync(service.RETRY_MS);
    fetch.mockResolvedValue(response());
    expect(await service.checkRelease()).not.toBeNull();
    expect(localStorage.getItem(service.RETRY_KEY)).toBeNull();
  });
  it("handles network errors silently in the UI and logs no raw error", async () => {
    fetch.mockRejectedValue(new Error("secret URL"));
    expect(await service.checkRelease()).toBeNull();
    expect(console.warn).toHaveBeenCalledWith("[updates] GitHub release check failed: network error");
  });
  it("bounds timeouts even if the fetch implementation ignores abort", async () => {
    let finish;
    fetch.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const pending = service.checkRelease();
    await vi.advanceTimersByTimeAsync(service.TIMEOUT_MS);
    expect(await pending).toBeNull();
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
    finish(response());
    await vi.advanceTimersByTimeAsync(0);
    expect(localStorage.getItem(service.CACHE_KEY)).toBeNull();
    expect(console.warn).toHaveBeenCalledWith("[updates] GitHub release check failed: timeout");
  });
  it.each([
    () => new Response("bad JSON", { headers: { "content-type": "application/json" } }),
    () => new Response("HTML", { headers: { "content-type": "text/html" } }),
    () => response({ ...payload, body: "x".repeat(262145) }),
  ])("rejects non-JSON and oversized bodies", async (makeResponse) => {
    fetch.mockResolvedValue(makeResponse());
    expect(await service.checkRelease()).toBeNull();
    expect(localStorage.getItem(service.CACHE_KEY)).toBeNull();
  });
  it("stores normalized metadata only, reuses it for 15 minutes, then expires", async () => {
    fetch.mockResolvedValue(response({ ...payload, body: "ignored", assets: [{ untrusted: true }] }));
    const first = await service.checkRelease();
    expect(first.release).toEqual(payload);
    await vi.advanceTimersByTimeAsync(service.CACHE_MS - 1);
    expect(await service.checkRelease()).toEqual(first);
    expect(fetch).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1);
    expect(service.freshRelease(first)).toBeNull();
    expect(service.releaseNotice("v1.2.0", "v1.2.0", first)).toBeNull();
    fetch.mockResolvedValue(response({}, 403));
    expect(await service.checkRelease()).toBeNull();
    expect(service.cachedRelease()).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it.each([
    { checkedAt: NOW + 1, release: payload },
    { checkedAt: NOW, release: { ...payload, html_url: "https://evil.example" } },
    { checkedAt: "today", release: payload },
  ])("never trusts invalid persisted data %j", async (cached) => {
    localStorage.setItem(service.CACHE_KEY, JSON.stringify(cached));
    fetch.mockRejectedValue(new Error("offline"));
    expect(await service.checkRelease()).toBeNull();
  });
  it("coalesces multiple mounts and cancels only after the final consumer leaves", async () => {
    let finish;
    fetch.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const a = new AbortController(), b = new AbortController();
    const one = service.checkRelease(a.signal), two = service.checkRelease(b.signal);
    await vi.advanceTimersByTimeAsync(0);
    a.abort();
    expect(await one).toBeNull();
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(false);
    finish(response());
    expect(await two).not.toBeNull();
    expect(fetch).toHaveBeenCalledOnce();
  });
  it("cancels orphaned requests and ignores late asynchronous responses", async () => {
    let finish;
    fetch.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const controller = new AbortController();
    const pending = service.checkRelease(controller.signal);
    await vi.advanceTimersByTimeAsync(0);
    controller.abort();
    expect(await pending).toBeNull();
    finish(response());
    await vi.advanceTimersByTimeAsync(0);
    expect(localStorage.getItem(service.CACHE_KEY)).toBeNull();
    expect(localStorage.getItem(service.RETRY_KEY)).toBeNull();
    expect(console.warn).not.toHaveBeenCalled();
  });
  it("shares successful checks across independent tabs via localStorage", async () => {
    const first = await service.checkRelease();
    vi.resetModules();
    const tab = await import("./releaseCheck.js");
    expect(await tab.checkRelease()).toEqual(first);
    expect(fetch).toHaveBeenCalledOnce();
  });
  it("uses Web Locks to avoid simultaneous cold-tab requests", async () => {
    let locked = false, finish;
    Object.defineProperty(navigator, "locks", { configurable: true, value: {
      request: vi.fn(async (_key, _options, callback) => {
        if (locked) return callback(null);
        locked = true;
        try { return await callback({ name: "release" }); } finally { locked = false; }
      }),
    } });
    fetch.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const first = service.checkRelease();
    await vi.advanceTimersByTimeAsync(0);
    vi.resetModules();
    const tab = await import("./releaseCheck.js");
    expect(await tab.checkRelease()).toBeNull();
    expect(fetch).toHaveBeenCalledOnce();
    finish(response());
    const result = await first;
    expect(tab.cachedRelease()).toEqual(result);
  });
  it("does not revive page memory after another tab invalidates the shared cache", async () => {
    await service.checkRelease();
    localStorage.removeItem(service.CACHE_KEY);
    localStorage.setItem(service.RETRY_KEY, JSON.stringify(NOW + service.RETRY_MS));
    expect(service.cachedRelease()).toBeNull();
    await vi.advanceTimersByTimeAsync(service.RETRY_MS);
    expect(service.cachedRelease()).toBeNull();
    fetch.mockResolvedValue(response({}, 403));
    expect(await service.checkRelease()).toBeNull();
  });
  it("accepts another tab's recovery during this tab's failure backoff", async () => {
    fetch.mockResolvedValue(response({}, 403));
    expect(await service.checkRelease()).toBeNull();
    const recovery = { checkedAt: NOW, release: payload };
    localStorage.removeItem(service.RETRY_KEY);
    localStorage.setItem(service.CACHE_KEY, JSON.stringify(recovery));
    expect(service.cachedRelease()).toEqual(recovery);
    expect(await service.checkRelease()).toEqual(recovery);
    expect(fetch).toHaveBeenCalledOnce();
  });
  it("retains page cache when writes exceed storage quota", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
    const first = await service.checkRelease();
    expect(await service.checkRelease()).toEqual(first);
    expect(fetch).toHaveBeenCalledOnce();
  });
  it("uses memory when storage is unavailable", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    const first = await service.checkRelease();
    expect(await service.checkRelease()).toEqual(first);
    expect(fetch).toHaveBeenCalledOnce();
  });
});
