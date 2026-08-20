#!/bin/sh
set -eu

CONFIG_FILE="/usr/share/nginx/html/runtime-config.js"

json_string() {
  # Escape enough for JSON string values without requiring jq/python in nginx alpine.
  printf '%s' "$1" | sed 's/\/\\/g; s/"/\"/g; s///g; s/$/\n/' | tr -d '
' | sed 's/\n$//'
}

write_target() {
  key="$1"
  value="$2"
  escaped=$(json_string "$value")
  printf '    %s: "%s",
' "$key" "$escaped" >> "$CONFIG_FILE"
}

cat > "$CONFIG_FILE" <<'EOF'
window.__USAGE_DASHBOARD_CONFIG__ = {
  extensionTargets: {
EOF
write_target chrome "${EXTENSION_TARGET_CHROME_ID:-}"
write_target edge "${EXTENSION_TARGET_EDGE_ID:-}"
write_target opera "${EXTENSION_TARGET_OPERA_ID:-}"
write_target firefox "${EXTENSION_TARGET_FIREFOX_ID:-}"
write_target safari "${EXTENSION_TARGET_SAFARI_ID:-}"
cat >> "$CONFIG_FILE" <<'EOF'
  }
};
EOF
