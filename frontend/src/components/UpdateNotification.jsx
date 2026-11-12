import { useEffect, useState } from "react";
import { Box, IconButton, Link, Tooltip, Typography } from "@mui/material";
import SystemUpdateAltRoundedIcon from "@mui/icons-material/SystemUpdateAltRounded";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import OpenInNewRoundedIcon from "@mui/icons-material/OpenInNewRounded";
import { appVersion, newerStable } from "../lib/appVersion.js";

const DISMISSED_KEY = "usage-dashboard:dismissed-update:";
const DISMISS_EVENT = "usage-dashboard:update-dismissed";
const RELEASE_BASE = "https://github.com/Skulldorom/usage-dashboard/releases/tag/";
const FRESH_MS = 6 * 60 * 60 * 1000;

function readDismissals() {
  try {
    return [
      ...["update_available", "stable_release_available"].map((type) => `${type}:${localStorage.getItem(DISMISSED_KEY + type)}`),
      `update_available:${localStorage.getItem("usage-dashboard:dismissed-update")}`,
    ];
  } catch {
    return [];
  }
}

export default function UpdateNotification({ update, compact = false }) {
  const [dismissed, setDismissed] = useState(readDismissals);
  const [copyStatus, setCopyStatus] = useState("");
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    function sync(event) {
      setDismissed((previous) => [...new Set([...previous, ...readDismissals(), ...(event.detail ? [event.detail] : [])])]);
    }
    window.addEventListener("storage", sync);
    window.addEventListener(DISMISS_EVENT, sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener(DISMISS_EVENT, sync);
    };
  }, []);
  useEffect(() => {
    if (!update) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 60000);
    return () => window.clearInterval(timer);
  }, [update]);
  if (!update) return null;

  const backend = appVersion(update.current_version);
  const frontend = appVersion(import.meta.env.VITE_APP_VERSION || "unknown");
  const versionsMatch = backend.kind !== "unknown" && frontend.kind !== "unknown" &&
    backend.full.replace(/^v/, "") === frontend.full.replace(/^v/, "");
  const mismatch = backend.kind !== "unknown" && frontend.kind !== "unknown" && !versionsMatch;
  const latest = appVersion(update.latest_version);
  const checkedAt = Date.parse(update.checked_at);
  const currentTime = Math.max(now, Date.now());
  const fresh = update.cache_status === "fresh" && Number.isFinite(checkedAt) &&
    checkedAt <= currentTime && currentTime - checkedAt < FRESH_MS;
  const trustedRelease = fresh && latest.kind === "stable" && update.release_url === RELEASE_BASE + update.latest_version;
  const stableUpdate = update.status === "update_available" && newerStable(backend, latest);
  const developmentNotice = update.status === "stable_release_available" && backend.kind === "development";
  const notificationType = stableUpdate ? "update_available" : "stable_release_available";
  const dismissal = `${notificationType}:${update.latest_version}`;
  const showNotice = versionsMatch && trustedRelease && (stableUpdate || developmentNotice) && !dismissed.includes(dismissal);
  const versionDetails = backend.kind === "development" ? "Development channel: stable releases are alternatives, not newer-version comparisons.\n" : "";
  const metadata = `Backend: ${backend.full}\nFrontend: ${frontend.full}`;
  let diagnostic = "";
  if (mismatch) diagnostic = "Version mismatch";
  else if (!versionsMatch) diagnostic = update.status === "check_failed" ? "Version unknown · Update check unavailable" : "Version unknown";
  else if (update.status === "unverified_release") diagnostic = `Release unverified${update.cache_status === "stale" ? " · Release metadata stale" : ""}`;
  else if (update.status === "check_failed") diagnostic = `Update check unavailable${update.cache_status === "stale" ? " · Release metadata stale" : ""}`;
  else if (update.cache_status === "stale" || (update.cache_status === "fresh" && !fresh)) diagnostic = "Release metadata stale";
  else if (update.status === "up_to_date" && trustedRelease && backend.kind === "stable" && backend.label === latest.label) diagnostic = "Up to date";
  else if (update.status === "ahead_of_release" && trustedRelease && newerStable(latest, backend)) diagnostic = "Ahead of published release";
  else if (!showNotice && !dismissed.includes(dismissal)) diagnostic = "Release status unknown";

  async function copyVersion() {
    try {
      await navigator.clipboard.writeText(versionsMatch ? backend.full : metadata);
      setCopyStatus("Version copied");
    } catch {
      setCopyStatus("Copy unavailable. Full metadata is in version details.");
    }
  }

  function dismiss() {
    try {
      localStorage.setItem(DISMISSED_KEY + notificationType, update.latest_version);
    } catch {
      // Keep the dismissal effective for this session when storage is restricted.
    }
    setDismissed((previous) => [...previous, dismissal]);
    window.dispatchEvent(new CustomEvent(DISMISS_EVENT, { detail: dismissal }));
  }

  return (
    <Box className={`version-footer${compact ? " version-footer-mobile" : ""}`}>
      {showNotice && (
        <Box className={`update-notification${developmentNotice ? " update-notification-info" : ""}`}>
          <Box className="update-notification-header">
            {developmentNotice ? <InfoOutlinedIcon fontSize="small" aria-hidden="true" /> : <SystemUpdateAltRoundedIcon fontSize="small" aria-hidden="true" />}
            <Typography component="strong">{developmentNotice ? "Stable release available" : "Update available"}</Typography>
            <Tooltip title="Dismiss this notification">
              <IconButton size="small" aria-label={`Dismiss ${developmentNotice ? "stable release" : "update"} ${update.latest_version}`} onClick={dismiss}>
                <CloseRoundedIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
          <Typography className="update-version-change">{latest.label}</Typography>
          {developmentNotice && <Typography className="update-notification-copy">An alternative to this development build, not a newer-version comparison.</Typography>}
          <Link href={update.release_url} target="_blank" rel="noopener noreferrer" className="update-release-link">
            View release notes <OpenInNewRoundedIcon fontSize="inherit" aria-hidden="true" />
          </Link>
        </Box>
      )}
      <Box className="sidebar-version-row">
        <Tooltip title={<span style={{ whiteSpace: "pre-line", overflowWrap: "anywhere" }}>{versionDetails}{metadata}</span>} describeChild>
          <button type="button" className="sidebar-version" aria-label="Version details">
            <span className={`version-indicator version-indicator-${backend.kind}`} aria-hidden="true" />
            <span>{backend.label}</span>
            {backend.sha && <code>{backend.sha}</code>}
          </button>
        </Tooltip>
        <Tooltip title="Copy full version metadata">
          <IconButton size="small" aria-label="Copy full version metadata" onClick={copyVersion} className="version-copy">
            <ContentCopyRoundedIcon fontSize="inherit" />
          </IconButton>
        </Tooltip>
      </Box>
      {diagnostic && <Typography className={`version-diagnostic${mismatch ? " version-diagnostic-warning" : ""}`}>{diagnostic}</Typography>}
      <span role="status" className="version-copy-status">{copyStatus}</span>
    </Box>
  );
}
