"""Promote verified digests. Writers must hold the application-release workflow lock."""

import argparse
import json
import os
import re
import subprocess

from application_release import MARKER, STABLE, api, pages, version
from verify_release_images import COMPONENTS, labels, manifest, repository, verify


def candidate(repo, tag=None, sha=None):
    releases = pages(f"repos/{repo}/releases")
    published = [r for r in releases if not r["draft"] and not r["prerelease"] and STABLE.fullmatch(r["tag_name"])]
    latest = max(published, key=lambda r: version(r["tag_name"])) if published else None
    if tag is None:
        if not latest:
            raise ValueError("No published stable release to bootstrap")
        tag = latest["tag_name"]
    version(tag)
    if latest and version(latest["tag_name"]) > version(tag):
        raise ValueError("Refusing to promote an older release")
    release = next((r for r in releases if r["tag_name"] == tag), None)
    if not release or release["prerelease"]:
        raise ValueError("Missing stable release record")
    if release["draft"] and not release.get("body", "").startswith(MARKER):
        raise ValueError("Unmanaged draft release")
    ref = api(f"repos/{repo}/git/ref/tags/{tag}")["object"]
    if ref["type"] != "commit" or not re.fullmatch(r"[0-9a-f]{40}", ref["sha"]):
        raise ValueError("Stable tag must directly identify a commit")
    if sha and sha != ref["sha"]:
        raise ValueError("Release source mismatch")
    # Bootstrap cannot bypass an unfinished reserved release, including partial promotion.
    pending = [
        r for r in releases if r["draft"] and STABLE.fullmatch(r["tag_name"]) and version(r["tag_name"]) > version(tag)
    ]
    if pending:
        raise ValueError("Resume the newer reserved Application release first")
    return tag, ref["sha"]


def aliases(tag):
    major, minor, _ = version(tag)
    return (f"v{major}.{minor}", f"v{major}", "stable", "latest")


def promote(repo, tag=None, sha=None, execute=False):
    tag, sha = candidate(repo, tag, sha)
    digests = verify(tag, sha)
    targets = aliases(tag)
    current = {}
    # Preflight every destination before the first write; a partial newer promotion is a rollback barrier.
    for component in COMPONENTS:
        for alias in targets:
            digest = manifest(component, alias)
            current[component, alias] = digest
            if not digest:
                continue
            metadata = labels(component, digest)
            old = metadata.get("org.opencontainers.image.version", "")
            if STABLE.fullmatch(old):
                if version(old) > version(tag):
                    raise ValueError(f"Refusing rollback of {component}:{alias} from {old}")
                if old == tag and digest != digests[component]:
                    raise ValueError(f"Conflicting digest for {component}:{alias}")
            elif not (alias == "latest" and old.startswith("v0.0.0-dev.")):
                raise ValueError(f"Unrecognized existing channel metadata on {component}:{alias}")
    # Recheck authoritative state after potentially slow pulls, while still holding the shared lock.
    candidate(repo, tag, sha)
    print(json.dumps({"tag": tag, "sha": sha, "digests": digests, "aliases": targets, "execute": execute}, indent=2))
    if not execute:
        return digests
    try:
        for component in COMPONENTS:
            missing = [alias for alias in targets if current[component, alias] != digests[component]]
            if missing:
                command = ["docker", "buildx", "imagetools", "create", "--prefer-index=false"]
                for alias in missing:
                    command += ["--tag", f"{repository(component)}:{alias}"]
                subprocess.run(command + [f"{repository(component)}@{digests[component]}"], check=True, timeout=300)
        for component in COMPONENTS:
            for alias in targets:
                if manifest(component, alias) != digests[component]:
                    raise ValueError(f"Promotion verification failed: {component}:{alias}")
    except Exception:
        print(
            "PARTIAL PROMOTION POSSIBLE. Do not roll back aliases. Rerun Application release for a pending draft; "
            "otherwise rerun Stable channels on main. Existing exact tags are reused and verified."
        )
        raise
    return digests


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag")
    parser.add_argument("--sha")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    promote(os.environ["GITHUB_REPOSITORY"], args.tag, args.sha, args.execute)
