"""Resolve immutable registry manifests and verify their runnable image metadata."""

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request

COMPONENTS = ("backend", "frontend")


def repository(component):
    if component not in COMPONENTS:
        raise ValueError("Unknown image component")
    return f"ghcr.io/skulldorom/usage-dashboard-{component}"


def manifest(component, tag):
    """Public GHCR reads fail closed, except an explicit manifest-not-found response."""
    repo = repository(component).removeprefix("ghcr.io/")
    with urllib.request.urlopen(f"https://ghcr.io/token?scope=repository:{repo}:pull", timeout=30) as response:
        token = json.load(response)["token"]
    request = urllib.request.Request(
        f"https://ghcr.io/v2/{repo}/manifests/{tag}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, "
            "application/vnd.docker.distribution.manifest.list.v2+json, "
            "application/vnd.docker.distribution.manifest.v2+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            digest = response.headers["Docker-Content-Digest"]
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest or ""):
                raise ValueError("Missing or invalid registry digest")
            return digest
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def labels(component, digest):
    image = f"{repository(component)}@{digest}"
    subprocess.run(["docker", "pull", "--platform", "linux/amd64", image], check=True, timeout=300)
    raw = subprocess.check_output(
        ["docker", "image", "inspect", image, "--format", "{{json .Config.Labels}}"], text=True, timeout=30
    )
    return json.loads(raw) or {}


def verify_component(component, tag, sha, digest=None):
    digest = digest or manifest(component, tag)
    if not digest:
        raise ValueError(f"Missing {component}:{tag}")
    metadata = labels(component, digest)
    if (
        metadata.get("org.opencontainers.image.version") != tag
        or metadata.get("org.opencontainers.image.revision") != sha
    ):
        raise ValueError(f"{component} image does not match the reserved release")
    return digest


def verify(tag, sha):
    return {component: verify_component(component, tag, sha) for component in COMPONENTS}


if __name__ == "__main__":
    verify(*sys.argv[1:])
