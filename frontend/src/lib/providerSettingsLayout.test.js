import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const settingsSource = readFileSync(
  resolve(currentDir, "../pages/SettingsPage.jsx"),
  "utf8",
);
const styles = readFileSync(resolve(currentDir, "../styles.css"), "utf8");

describe("connected provider layout guardrails", () => {
  it("assigns every provider field and action group to a named layout area", () => {
    expect(settingsSource).toContain(
      'className="config-detail config-credential"',
    );
    expect(settingsSource).toContain(
      'className="config-detail config-endpoint"',
    );
    expect(settingsSource).toContain(
      'className="config-detail config-billing"',
    );
    expect(settingsSource).toContain('className="config-actions"');
    expect(styles).toContain(
      '"order identity credential endpoint billing actions"',
    );
  });

  it("uses an explicit stacked layout on mobile without hiding fields", () => {
    expect(styles).toContain('"order credential"');
    expect(styles).toContain('"order endpoint"');
    expect(styles).toContain('"order billing"');
    expect(styles).toContain('"actions actions"');
    expect(styles).not.toMatch(/config-detail:nth-of-type/);
  });

  it("shows the canonical provider name in provider identity", () => {
    expect(settingsSource).toContain("providerDisplayName(config.provider)");
  });
});
