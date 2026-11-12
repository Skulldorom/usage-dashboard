import { useEffect, useState } from "react";
import { CACHE_KEY, RETRY_KEY, CACHE_MS, cachedRelease, checkRelease } from "./releaseCheck.js";

export default function useUpdateStatus(isAuthenticated, backendVersion) {
  const [release, setRelease] = useState(null);
  useEffect(() => {
    if (!isAuthenticated) {
      setRelease(null);
      return undefined;
    }
    let disposed = false;
    let expiry;
    const controller = new AbortController();
    function accept(result) {
      if (disposed) return;
      window.clearTimeout(expiry);
      setRelease(result);
      if (result) {
        // Expire the notice without starting another network request.
        expiry = window.setTimeout(() => accept(null), Math.max(0, result.checkedAt + CACHE_MS - Date.now()));
      }
    }
    async function check() {
      if (disposed || document.visibilityState === "hidden") return;
      accept(cachedRelease());
      const result = await checkRelease(controller.signal);
      // A lock miss may settle after another tab has published a verified result.
      // Re-read shared state before clearing a notice synchronized by storage events.
      if (!disposed) accept(result ?? cachedRelease());
    }
    function visible() {
      if (document.visibilityState === "visible") check();
    }
    function storage(event) {
      if (event.key === CACHE_KEY || event.key === RETRY_KEY || event.key === null) accept(cachedRelease());
    }
    const initial = window.setTimeout(check, 2500);
    document.addEventListener("visibilitychange", visible);
    window.addEventListener("storage", storage);
    return () => {
      disposed = true;
      controller.abort();
      window.clearTimeout(initial);
      window.clearTimeout(expiry);
      document.removeEventListener("visibilitychange", visible);
      window.removeEventListener("storage", storage);
    };
  }, [isAuthenticated]);
  return isAuthenticated ? { current_version: backendVersion, release } : null;
}
