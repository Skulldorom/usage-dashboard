import { useEffect, useState } from "react";
import { api } from "../api.js";

const CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;

export default function useUpdateStatus(isAuthenticated) {
  const [update, setUpdate] = useState(null);

  useEffect(() => {
    if (!isAuthenticated) {
      return undefined;
    }

    setUpdate(null);
    let disposed = false;
    let lastCheckAt = 0;
    let inFlight = false;
    const controller = new AbortController();

    async function check() {
      if (disposed || inFlight || document.visibilityState === "hidden") return;
      inFlight = true;
      lastCheckAt = Date.now();
      try {
        const result = await api.systemUpdate({ signal: controller.signal });
        if (!disposed) setUpdate(result);
      } catch {
        if (!disposed) setUpdate((previous) => previous ? { ...previous, status: "check_failed", cache_status: "stale" } : { current_version: null, status: "check_failed", cache_status: "empty" });
      } finally {
        inFlight = false;
      }
    }

    function checkWhenVisible() {
      if (
        document.visibilityState === "visible" &&
        Date.now() - lastCheckAt >= CHECK_INTERVAL_MS
      ) {
        check();
      }
    }

    check();
    const interval = window.setInterval(checkWhenVisible, CHECK_INTERVAL_MS);
    document.addEventListener("visibilitychange", checkWhenVisible);
    return () => {
      disposed = true;
      controller.abort();
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", checkWhenVisible);
    };
  }, [isAuthenticated]);

  return isAuthenticated ? update : null;
}
