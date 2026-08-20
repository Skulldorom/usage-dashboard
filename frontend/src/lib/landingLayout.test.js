import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(currentDir, "../App.jsx"), "utf8");
const styles = readFileSync(resolve(currentDir, "../styles.css"), "utf8");

describe("landing page layout guardrails", () => {
  it("keeps the unauthenticated hero constrained and two-column on desktop", () => {
    expect(styles).toMatch(
      /\.landing-hero\s*\{[^}]*width:\s*min\(100%,\s*1240px\);/s,
    );
    expect(styles).toMatch(
      /\.landing-hero\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*minmax\(280px,\s*410px\);/s,
    );
    expect(styles).toMatch(/\.landing-copy\s*\{[^}]*z-index:\s*1;/s);
    expect(styles).toMatch(/\.landing-card-stack\s*\{[^}]*z-index:\s*1;/s);
  });

  it("uses purple as primary and cyan as secondary accent in the app theme", () => {
    expect(appSource).toContain('main: "#8b5cf6"');
    expect(appSource).toContain('secondary: { main: "#06c8ff"');
    expect(appSource).not.toContain("linear-gradient(135deg, #06c8ff");
  });
});
