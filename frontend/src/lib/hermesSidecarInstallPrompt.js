export const HERMES_SIDECAR_REPO_URL = 'https://github.com/Skulldorom/hermes-usage-sidecar'
export const HERMES_SIDECAR_DOCS_URL = 'https://skulldorom.github.io/usage-dashboard/docs/configuration/hermes-usage-sidecar.html'

export const HERMES_SIDECAR_INSTALL_PROMPT = `Install and configure Hermes Usage Sidecar on this machine for my current Hermes Agent installation.

Repository:
https://github.com/Skulldorom/hermes-usage-sidecar

First, inspect the repository's CURRENT README and installation documentation and follow those instructions. Do not assume installation commands, paths, service names, ports, or configuration options if the repository documentation says otherwise.

Requirements:

- Detect my Hermes installation and Hermes home directory automatically.
- Install the Hermes Usage Sidecar using its currently recommended installation method.
- Configure it for this Hermes installation.
- Ensure it automatically discovers the default Hermes profile and all available Hermes profiles.
- Access every Hermes state.db strictly READ-ONLY.
- Never modify, migrate, vacuum, reconfigure, or otherwise write to a Hermes state.db.
- Do not collect or expose conversation/message content.
- Do not expose Hermes provider API keys or other Hermes secrets.
- Do not configure Usage Dashboard, Usage Dashboard providers, provider mappings, or the Hermes Data Source configuration. Only install and configure the sidecar.

Authentication:

- Generate a new cryptographically secure bearer token for the sidecar.
- Generate the token yourself using an appropriate secure random generator.
- Store it using the sidecar's documented/recommended token-file or secret mechanism.
- Do not ask me to create the token manually.
- Do not print the bearer token directly into this conversation unless absolutely required by the sidecar's installation process.
- Instead, after installation, tell me exactly where the token is stored and give me the exact command I can run myself to retrieve/copy it.
- Use the actual path created during installation. Do not give me a placeholder command.

Service configuration:

- Configure the sidecar to start automatically using the recommended deployment method for this environment.
- Keep the sidecar bound to localhost by default unless the documented installation or my environment requires otherwise.
- Do not expose the sidecar publicly to the internet.
- If network exposure beyond localhost is required, explain why and ask before making a security-sensitive networking change.

Verification:

After installation:

1. Start/restart the sidecar.
2. Confirm the service is running correctly.
3. Run its health check.
4. Verify the /usage endpoint works with the generated bearer token.
5. Confirm all expected Hermes profiles were detected.
6. Confirm telemetry can be read.
7. Confirm Hermes database access remains read-only.
8. Confirm no conversation content, provider API keys, or unrelated secrets are returned.

If something fails, diagnose and fix it rather than reporting installation as successful.

When finished, give me a concise report containing:

- Installation status
- Service status
- Sidecar version
- Sidecar address/port
- Profiles detected
- Health-check result
- /usage verification result
- Bearer-token storage location
- Exact command I should run to retrieve/copy the bearer token
- Any warnings or configuration changes you made

Do NOT include the bearer token itself in the final report.

Do not modify Hermes itself unless the sidecar's official documentation explicitly requires a change and you have explained that change to me first.`
