"""Verify registry image labels before making a stable release discoverable."""

import json
import subprocess
import sys


def verify(tag, sha):
    for component in ("backend", "frontend"):
        image = f"ghcr.io/skulldorom/usage-dashboard-{component}:{tag}"
        raw = subprocess.check_output(
            ["docker", "buildx", "imagetools", "inspect", image, "--format", "{{json .Image}}"], text=True
        )
        labels = json.loads(raw)["config"]["Labels"]
        if (
            labels.get("org.opencontainers.image.version") != tag
            or labels.get("org.opencontainers.image.revision") != sha
        ):
            raise ValueError(f"{component} image does not match the reserved release")


if __name__ == "__main__":
    verify(*sys.argv[1:])
