import React from 'react'
import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { InstallWithHermesSection } from '../components/DataSourcesSection.jsx'
import {
  HERMES_SIDECAR_DOCS_URL,
  HERMES_SIDECAR_INSTALL_PROMPT,
  HERMES_SIDECAR_REPO_URL,
} from './hermesSidecarInstallPrompt.js'

describe('Hermes sidecar assisted install prompt', () => {
  it('references the canonical sidecar repository and current docs inspection', () => {
    expect(HERMES_SIDECAR_REPO_URL).toBe('https://github.com/Skulldorom/hermes-usage-sidecar')
    expect(HERMES_SIDECAR_INSTALL_PROMPT).toContain(HERMES_SIDECAR_REPO_URL)
    expect(HERMES_SIDECAR_INSTALL_PROMPT).toContain("inspect the repository's CURRENT README")
    expect(HERMES_SIDECAR_INSTALL_PROMPT).toContain('installation documentation')
  })

  it('keeps Hermes database access read-only and discovers all profiles', () => {
    expect(HERMES_SIDECAR_INSTALL_PROMPT).toContain('all available Hermes profiles')
    expect(HERMES_SIDECAR_INSTALL_PROMPT).toContain('Access every Hermes state.db strictly READ-ONLY')
    expect(HERMES_SIDECAR_INSTALL_PROMPT).toContain('Never modify, migrate, vacuum, reconfigure, or otherwise write')
  })

  it('requires a generated token that is stored rather than exposed', () => {
    expect(HERMES_SIDECAR_INSTALL_PROMPT).toContain('Generate a new cryptographically secure bearer token')
    expect(HERMES_SIDECAR_INSTALL_PROMPT).toContain('Store it using the sidecar')
    expect(HERMES_SIDECAR_INSTALL_PROMPT).toContain('Do not print the bearer token directly')
    expect(HERMES_SIDECAR_INSTALL_PROMPT).toContain('Exact command I should run to retrieve/copy the bearer token')
  })

  it('does not hard-code a token or ask Hermes to configure Usage Dashboard', () => {
    expect(HERMES_SIDECAR_INSTALL_PROMPT).not.toMatch(/(?:token|bearer)[=:]\s*[A-Za-z0-9._~+/-]{20,}/i)
    expect(HERMES_SIDECAR_INSTALL_PROMPT).toContain('Do not configure Usage Dashboard')
    expect(HERMES_SIDECAR_INSTALL_PROMPT).not.toContain('Create a Usage Dashboard data source')
    expect(HERMES_SIDECAR_INSTALL_PROMPT).not.toContain('configure provider mappings in Usage Dashboard')
  })

  it('includes localhost-only service and verification requirements', () => {
    expect(HERMES_SIDECAR_INSTALL_PROMPT).toContain('Keep the sidecar bound to localhost')
    expect(HERMES_SIDECAR_INSTALL_PROMPT).toContain('Do not expose the sidecar publicly')
    expect(HERMES_SIDECAR_INSTALL_PROMPT).toContain('Run its health check')
    expect(HERMES_SIDECAR_INSTALL_PROMPT).toContain('Verify the /usage endpoint')
  })
})

describe('DataSourcesSection assisted install UI', () => {
  it('renders the install-with-Hermes section and repository/docs links', () => {
    const html = renderToString(React.createElement(InstallWithHermesSection, { onCopyInstallPrompt: () => {} }))

    expect(html).toContain('Install with Hermes')
    expect(html).toContain('Copy installation prompt')
    expect(html).toContain('Manual installation')
    expect(html).toContain('Sidecar repository')
    expect(html).toContain(HERMES_SIDECAR_REPO_URL)
    expect(html).toContain(HERMES_SIDECAR_DOCS_URL)
  })
})
