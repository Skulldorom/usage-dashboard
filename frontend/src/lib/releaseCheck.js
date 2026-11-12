import { appVersion, newerStable } from "./appVersion.js";

export const RELEASE_API = "https://api.github.com/repos/Skulldorom/usage-dashboard/releases/latest";
export const RELEASE_BASE = "https://github.com/Skulldorom/usage-dashboard/releases/tag/";
export const CACHE_KEY = "usage-dashboard:verified-release:v1";
export const RETRY_KEY = "usage-dashboard:release-retry:v1";
export const CACHE_MS = 15 * 60 * 1000;
export const RETRY_MS = 60 * 1000;
export const TIMEOUT_MS = 5000;
const MAX_BYTES = 256 * 1024;
let inFlight;
let storageAvailable = true;

function read(key) {
  let raw;
  try { raw = localStorage.getItem(key); }
  catch { storageAvailable = false; return null; }
  try { return JSON.parse(raw); } catch { return null; }
}
function write(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch { storageAvailable = false; }
}

export function validateRelease(payload, now = Date.now()) {
  if (!payload || typeof payload !== "object") return null;
  const { tag_name: tag, html_url: url, published_at: published, url: apiUrl } = payload;
  if (appVersion(tag).kind !== "stable" || payload.draft !== false || payload.prerelease !== false ||
      url !== RELEASE_BASE + tag || typeof apiUrl !== "string" ||
      !/^https:\/\/api\.github\.com\/repos\/Skulldorom\/usage-dashboard\/releases\/[1-9][0-9]*$/.test(apiUrl) ||
      typeof published !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(published)) return null;
  const timestamp = Date.parse(published);
  if (!Number.isFinite(timestamp) || timestamp > now ||
      new Date(timestamp).toISOString() !== published.replace("Z", ".000Z")) return null;
  // Persist only the fields needed to revalidate trust, never arbitrary API content.
  return { tag_name: tag, html_url: url, url: apiUrl, published_at: published, draft: false, prerelease: false };
}

export function freshRelease(record, now = Date.now()) {
  return record && Number.isFinite(record.checkedAt) && record.checkedAt <= now &&
    now - record.checkedAt < CACHE_MS && validateRelease(record.release, now) ? record : null;
}

let memoryCache = null;
let retryUntil = 0;

export function cachedRelease() {
  if (retryPending()) return null;
  const stored = read(CACHE_KEY);
  return freshRelease(storageAvailable ? stored : memoryCache);
}

function retryPending() {
  const now = Date.now();
  const stored = read(RETRY_KEY);
  // Reject corrupted/future-dated backoffs rather than suppress checks indefinitely.
  const until = storageAvailable ? stored : retryUntil;
  return Number.isFinite(until) && until > now && until <= now + RETRY_MS;
}

async function fetchRelease(controller) {
  let timedOut = false;
  const timeout = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, TIMEOUT_MS);
  try {
    const aborted = new Promise((_, reject) => {
      controller.signal.addEventListener("abort", () => reject(new Error(timedOut ? "timeout" : "cancelled")), { once: true });
    });
    const record = await Promise.race([
      (async () => {
        const response = await fetch(RELEASE_API, {
          signal: controller.signal,
          credentials: "omit",
          referrerPolicy: "no-referrer",
          redirect: "error",
          cache: "no-store",
          headers: { Accept: "application/vnd.github+json" },
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        if (!response.headers.get("content-type")?.includes("application/json")) throw new Error("invalid content type");
        const reader = response.body.getReader();
        let size = 0;
        const chunks = [];
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            size += value.byteLength;
            if (size > MAX_BYTES) throw new Error("oversized response");
            chunks.push(value);
          }
        } finally {
          await reader.cancel();
        }
        const bytes = new Uint8Array(size);
        let offset = 0;
        for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
        let payload;
        try { payload = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); }
        catch { throw new Error("invalid JSON"); }
        const release = validateRelease(payload);
        if (!release) throw new Error("invalid release metadata");
        return { release, checkedAt: Date.now() };
      })(),
      aborted,
    ]);
    if (controller.signal.aborted) return null;
    memoryCache = record;
    retryUntil = 0;
    write(RETRY_KEY, null);
    write(CACHE_KEY, record);
    return record;
  } catch (error) {
    if (!controller.signal.aborted || timedOut) {
      memoryCache = null;
      retryUntil = Date.now() + RETRY_MS;
      write(CACHE_KEY, null);
      write(RETRY_KEY, retryUntil);
      // Only our bounded diagnostic codes reach logs; never response bodies or credentials.
      const reason = /^(HTTP \d{3}|timeout|invalid content type|oversized response|invalid JSON|invalid release metadata)$/.test(error.message)
        ? error.message : "network error";
      console.warn(`[updates] GitHub release check failed: ${reason}`);
    }
    return null;
  } finally {
    window.clearTimeout(timeout);
  }
}

// One request per page, with optional cross-tab Web Locks. localStorage shares only
// verified results/backoff; without Web Locks simultaneous cold tabs can each fetch.
export function checkRelease(signal) {
  if (signal?.aborted) return Promise.resolve(null);
  const cached = cachedRelease();
  if (cached) return Promise.resolve(cached);
  if (retryPending()) return Promise.resolve(null);
  if (!inFlight || inFlight.controller.signal.aborted) {
    const controller = new AbortController();
    const flight = { controller, clients: new Set() };
    inFlight = flight;
    const run = () => cachedRelease() || (retryPending() || controller.signal.aborted ? null : fetchRelease(controller));
    flight.promise = Promise.resolve().then(() => navigator.locks?.request
      ? navigator.locks.request(CACHE_KEY, { ifAvailable: true }, (lock) => lock ? run() : null)
      : run()
    ).catch(() => null).finally(() => {
      if (inFlight === flight) inFlight = null;
    });
  }
  const flight = inFlight;
  const client = {};
  flight.clients.add(client);
  return new Promise((resolve) => {
    function finish(result) {
      signal?.removeEventListener("abort", cancel);
      flight.clients.delete(client);
      resolve(result);
    }
    function cancel() {
      finish(null);
      if (!flight.clients.size) flight.controller.abort();
    }
    signal?.addEventListener("abort", cancel, { once: true });
    flight.promise.then((result) => finish(signal?.aborted ? null : result));
  });
}

export function releaseNotice(frontendValue, backendValue, record, now = Date.now()) {
  const frontend = appVersion(frontendValue);
  const backend = appVersion(backendValue);
  if (frontend.kind === "unknown" || backend.kind === "unknown" ||
      frontend.full.replace(/^v/, "") !== backend.full.replace(/^v/, "") || !freshRelease(record, now)) return null;
  const latest = appVersion(record.release.tag_name);
  if (backend.kind === "development") return "stable_release_available";
  return newerStable(backend, latest) ? "update_available" : null;
}
