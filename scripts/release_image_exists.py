"""Reuse an existing exact-version artifact; never overwrite it on a retry."""

import os
import sys

from application_release import version
from verify_release_images import manifest, verify_component


def exists(component, tag, sha):
    version(tag)
    digest = manifest(component, tag)
    if digest:
        verify_component(component, tag, sha, digest)
    return bool(digest)


if __name__ == "__main__":
    result = exists(*sys.argv[1:])
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"exists={str(result).lower()}\n")
