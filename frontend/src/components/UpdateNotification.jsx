import { useEffect, useState } from "react";
import { Box, IconButton, Link, Tooltip, Typography } from "@mui/material";
import SystemUpdateAltRoundedIcon from "@mui/icons-material/SystemUpdateAltRounded";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import OpenInNewRoundedIcon from "@mui/icons-material/OpenInNewRounded";
import { appVersion } from "../lib/appVersion.js";
import { releaseNotice } from "../lib/releaseCheck.js";

const DISMISSED_KEY = "usage-dashboard:dismissed-update:";
const DISMISS_EVENT = "usage-dashboard:update-dismissed";
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
  if (!update) return null;

  const backend = appVersion(update.current_version);
  const frontend = appVersion(import.meta.env.VITE_APP_VERSION || "unknown");
  const versionsMatch = backend.kind !== "unknown" && frontend.kind !== "unknown" &&
    backend.full.replace(/^v/, "") === frontend.full.replace(/^v/, "");
  const notificationType = releaseNotice(frontend.full, backend.full, update.release);
  const developmentNotice = notificationType === "stable_release_available";
  const tag = update.release?.release?.tag_name;
  const latest = appVersion(tag);
  const dismissal = `${notificationType}:${tag}`;
  const showNotice = notificationType && !dismissed.includes(dismissal);
  const versionDetails = backend.kind === "development" ? "Development channel: stable releases are alternatives, not newer-version comparisons.\n" : "";
  const metadata = `Backend: ${backend.full}\nFrontend: ${frontend.full}`;

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
      localStorage.setItem(DISMISSED_KEY + notificationType, tag);
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
              <IconButton size="small" aria-label={`Dismiss ${developmentNotice ? "stable release" : "update"} ${tag}`} onClick={dismiss}>
                <CloseRoundedIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
          <Typography className="update-notification-copy">{developmentNotice ? "A stable release is available as an alternative to this development build." : "A new version of Usage Dashboard is available."}</Typography>
          <Box className="update-version-change">
            {!developmentNotice && (
              <>
                <span className="update-version-installed">{backend.label}</span>
                <span aria-hidden="true">→</span>
                <span className="update-version-comparison-label">to</span>
              </>
            )}
            <span className="update-version-latest">{latest.label}</span>
            {!developmentNotice && <span className="update-new-badge">New</span>}
          </Box>
          <Link href={update.release.release.html_url} target="_blank" rel="noopener noreferrer" className="update-release-link">
            View release <OpenInNewRoundedIcon fontSize="inherit" aria-hidden="true" />
          </Link>
        </Box>
      )}
      <Box className="sidebar-version-row">
        <Tooltip title={<span style={{ whiteSpace: "pre-line", overflowWrap: "anywhere" }}>{versionDetails}{metadata}</span>} describeChild>
          <button type="button" className="sidebar-version" aria-label="Version details">
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
      <span role="status" className="version-copy-status">{copyStatus}</span>
    </Box>
  );
}
