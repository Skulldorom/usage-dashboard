import { useState } from "react";
import {
  Box,
  IconButton,
  Link,
  Tooltip,
  Typography,
} from "@mui/material";
import SystemUpdateAltRoundedIcon from "@mui/icons-material/SystemUpdateAltRounded";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import OpenInNewRoundedIcon from "@mui/icons-material/OpenInNewRounded";

const DISMISSED_UPDATE_KEY = "usage-dashboard:dismissed-update";

function dismissedVersion() {
  try {
    return localStorage.getItem(DISMISSED_UPDATE_KEY);
  } catch {
    return null;
  }
}

function dismissVersion(version) {
  try {
    localStorage.setItem(DISMISSED_UPDATE_KEY, version);
  } catch {
    // Storage restrictions must not affect update checks.
  }
}

export default function UpdateNotification({ update, compact = false }) {
  const [dismissed, setDismissed] = useState(() => dismissedVersion());
  if (!update) return null;
  const currentVersion = update.current_version === "unknown" ? null : update.current_version;
  const frontendVersion = import.meta.env.VITE_APP_VERSION || "unknown";
  const versionsMatch = currentVersion && frontendVersion !== "unknown" &&
    currentVersion.replace(/^v/, "") === frontendVersion.replace(/^v/, "");
  const isUpdateAvailable =
    versionsMatch &&
    update?.status === "update_available" &&
    currentVersion &&
    update.latest_version &&
    update.cache_status !== "stale" &&
    update.release_url === `https://github.com/Skulldorom/usage-dashboard/releases/tag/${update.latest_version}` &&
    dismissed !== update.latest_version;

  if (isUpdateAvailable) {
    return (
      <Box className={compact ? "mobile-update-notification" : "update-notification"}>
        <Box className="update-notification-header">
          <SystemUpdateAltRoundedIcon fontSize="small" aria-hidden="true" />
          <Typography component="strong">Update available</Typography>
          <Tooltip title="Dismiss this update">
            <IconButton
              size="small"
              aria-label={`Dismiss update ${update.latest_version}`}
              onClick={() => {
                dismissVersion(update.latest_version);
                setDismissed(update.latest_version);
              }}
            >
              <CloseRoundedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
        {!compact && (
          <Typography className="update-notification-copy">
            A new version of Usage Dashboard is available.
          </Typography>
        )}
        <Typography className="update-version-change">
          {currentVersion} <span aria-hidden="true">→</span> {update.latest_version}
        </Typography>
        <Link
          href={update.release_url}
          target="_blank"
          rel="noopener noreferrer"
          className="update-release-link"
        >
          View release notes <OpenInNewRoundedIcon fontSize="inherit" aria-hidden="true" />
        </Link>
      </Box>
    );
  }

  if (!currentVersion) return <Typography className="sidebar-version">Version unknown</Typography>;

  return (
    <Typography
      className="sidebar-version"
      title={versionsMatch && update?.status === "up_to_date" ? "Latest stable version installed" : undefined}
    >
      Version {currentVersion}
      {!versionsMatch && <><br />Frontend {frontendVersion === "unknown" ? "version unknown" : frontendVersion}</>}
    </Typography>
  );
}
