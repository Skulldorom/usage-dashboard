"""Verify registry image labels before making a stable release discoverable."""

import json
import subprocess
import sys


def verify(tag, sha):
    for component in ("backend", "frontend"):
        image = f"ghcr.io/skulldorom/usage-dashboard-{component}:{tag}"
        # Pull resolves the runnable platform from OCI indexes, including provenance attestations.
        subprocess.run(["docker", "pull", "--platform", "linux/amd64", image], check=True, timeout=300)
        raw = subprocess.check_output(
            ["docker", "image", "inspect", image, "--format", "{{json .Config.Labels}}"],
            text=True,
            timeout=30,
        )
        labels = json.loads(raw) or {}
        if (
            labels.get("org.opencontainers.image.version") != tag
            or labels.get("org.opencontainers.image.revision") != sha
        ):
            raise ValueError(f"{component} image does not match the reserved release")


if __name__ == "__main__":
    verify(*sys.argv[1:])
