const SEMVER = /^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/;

export function appVersion(value) {
  const match = typeof value === "string" && value.length <= 128 && value.match(SEMVER);
  if (!match || match[0] !== value || match[4]?.split(".").some((part) => /^0\d+$/.test(part))) {
    return { kind: "unknown", label: "Version unknown", full: value || "unknown" };
  }
  const core = match.slice(1, 4);
  if (!match[4] && core.every((part) => part === "0")) {
    return { kind: "unknown", label: "Version unknown", full: value };
  }
  if (match[4]) {
    const sha = match[4].match(/(?:^|\.)dev\.([a-f0-9]{7,64})(?:\.|$)/i)?.[1];
    return { kind: "development", label: "Development", sha: sha?.slice(0, 7), full: value };
  }
  return { kind: "stable", label: `v${core.join(".")}`, full: value, core };
}

export function newerStable(current, latest) {
  if (current.kind !== "stable" || latest.kind !== "stable") return false;
  for (let index = 0; index < 3; index += 1) {
    const installed = BigInt(current.core[index]);
    const published = BigInt(latest.core[index]);
    if (installed !== published) return installed < published;
  }
  return false;
}
