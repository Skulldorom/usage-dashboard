"""Plan/resume a single application release. Network mutations require an explicit command."""

import argparse
import json
import os
import re
import subprocess

STABLE = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
LEVELS = {"none": 0, "patch": 1, "minor": 2, "major": 3}
MARKER = "Application release managed by scripts/application_release.py."


def version(tag):
    match = STABLE.fullmatch(tag)
    if not match:
        raise ValueError(f"Invalid stable version: {tag}")
    return tuple(map(int, match.groups()))


def increment(tag, level):
    major, minor, patch = version(tag)
    if level == "major":
        return f"v{major + 1}.0.0"
    if level == "minor":
        return f"v{major}.{minor + 1}.0"
    if level == "patch":
        return f"v{major}.{minor}.{patch + 1}"
    if level == "none":
        return None
    raise ValueError(f"Invalid release classification: {level}")


def releasable(paths):
    return any(
        path.startswith(("backend/app/", "backend/alembic/", "frontend/src/", "frontend/public/", "deploy/"))
        or path
        in {
            "backend/Dockerfile",
            "backend/requirements.txt",
            "frontend/Dockerfile",
            "frontend/package.json",
            "frontend/package-lock.json",
            "frontend/index.html",
            "frontend/nginx.conf",
            "docker-compose.yml",
            "scripts/build-release.sh",
        }
        or path.startswith("frontend/docker-entrypoint.d/")
        for path in paths
    )


def release_intent(labels):
    intents = [label.removeprefix("release:") for label in labels if label.startswith("release:")]
    if len(intents) != 1 or intents[0] not in LEVELS:
        raise ValueError("Every PR requires exactly one release:patch/minor/major/none label")
    return intents[0]


def classify(labels, paths):
    intent = release_intent(labels)
    return intent if releasable(paths) else "none"


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def api(path, method="GET", data=None):
    command = ["gh", "api", path, "--method", method]
    if data is not None:
        command += ["--input", "-"]
    result = subprocess.run(
        command,
        input=json.dumps(data) if data is not None else None,
        text=True,
        capture_output=True,
        check=True,
        timeout=60,
    )
    return json.loads(result.stdout) if result.stdout.strip() else None


def pages(path):
    result = []
    for page in range(1, 101):
        items = api(f"{path}?per_page=100&page={page}")
        result.extend(items)
        if len(items) < 100:
            return result
    raise ValueError("API pagination limit reached")


def changed_paths(commit):
    parents = git("rev-list", "--parents", "-n", "1", commit).split()[1:]
    if len(parents) not in (1, 2):
        raise ValueError("Release history requires ordinary or two-parent merge commits")
    # Explicit first-parent comparison includes merge resolutions and deletions.
    return git("diff", "--name-only", "--no-renames", "-z", parents[0], commit).split("\0")[:-1]


def merged_intent(repo, pr, commit):
    labels = set()
    events = pages(f"repos/{repo}/issues/{pr['number']}/timeline")
    for event in events:
        kind = event.get("event")
        if kind in ("labeled", "unlabeled"):
            name = event["label"]["name"]
            if kind == "labeled":
                labels.add(name)
            else:
                if name.startswith("release:") and name not in labels:
                    raise ValueError("Incomplete release label history")
                labels.discard(name)
        elif kind == "merged":
            if event.get("commit_id") != commit or event.get("created_at") != pr["merged_at"]:
                raise ValueError("PR timeline merge does not match release commit")
            return release_intent(labels)
    raise ValueError("PR timeline has no matching merge event")


def reserve(repo, tag, sha):
    """GitHub refs are create-only: a competing reservation must identify the same commit."""
    try:
        api(f"repos/{repo}/git/refs", "POST", {"ref": f"refs/tags/{tag}", "sha": sha})
    except subprocess.CalledProcessError:
        existing = api(f"repos/{repo}/git/ref/tags/{tag}")
        if existing["object"]["type"] != "commit" or existing["object"]["sha"] != sha:
            raise ValueError("Release tag was already reserved for another commit") from None


def ensure_draft(repo, tag, sha, releases):
    existing = next((item for item in releases if item["tag_name"] == tag), None)
    if existing:
        if not existing["draft"] or not existing.get("body", "").startswith(MARKER):
            raise ValueError("Refusing to overwrite an unmanaged or published release")
        return
    try:
        api(
            f"repos/{repo}/releases",
            "POST",
            {
                "tag_name": tag,
                "target_commitish": sha,
                "name": tag,
                "draft": True,
                "prerelease": False,
                "body": MARKER
                + "\n\nPending tests and both GHCR images.\n\n_Prepared by an AI agent on behalf of the maintainers._",
            },
        )
    except subprocess.CalledProcessError:
        existing = next((item for item in pages(f"repos/{repo}/releases") if item["tag_name"] == tag), None)
        if not existing or not existing["draft"] or not existing.get("body", "").startswith(MARKER):
            raise


def prepare(repo, initial_base):
    git("fetch", "origin", "main", "--tags")
    head = git("rev-parse", "origin/main")
    releases = pages(f"repos/{repo}/releases")
    published = [
        item["tag_name"]
        for item in releases
        if not item["draft"] and not item["prerelease"] and STABLE.fullmatch(item["tag_name"])
    ]
    latest = max(published, key=version) if published else None
    tags = [tag for tag in git("tag", "--list").splitlines() if STABLE.fullmatch(tag)]
    pending = [tag for tag in tags if latest is None or version(tag) > version(latest)]
    if pending:
        if len(pending) != 1:
            raise ValueError("Multiple unpublished stable tags; resolve release reservations before proceeding")
        tag = pending[0]
        if latest is None and tag != "v1.0.0":
            raise ValueError("Initial stable reservation must be v1.0.0")
        sha = git("rev-parse", f"{tag}^{{commit}}")
        git("merge-base", "--is-ancestor", sha, head)
    else:
        if latest:
            base = latest
        elif initial_base:
            if not re.fullmatch(r"[0-9a-f]{40}", initial_base):
                raise ValueError("initial_base must be a full commit SHA")
            base = git("rev-parse", "--verify", f"{initial_base}^{{commit}}")
        else:
            raise ValueError("First release requires workflow_dispatch initial_base: reviewed baseline commit SHA")
        git("merge-base", "--is-ancestor", base, head)
        commits = git("rev-list", "--first-parent", f"{base}..{head}").splitlines()
        if len(commits) > 500:
            raise ValueError("Release batch exceeds 500 commits; select a reviewed initial baseline")
        levels = ["none"]
        for commit in commits:
            paths = changed_paths(commit)
            if not releasable(paths):
                continue
            prs = pages(f"repos/{repo}/commits/{commit}/pulls")
            prs = [
                pr
                for pr in prs
                if pr.get("merged_at") and pr["base"]["ref"] == "main" and pr.get("merge_commit_sha") == commit
            ]
            if len(prs) != 1:
                raise ValueError(f"Commit {commit} requires a classified merged PR (use squash or merge commits)")
            pr = prs[0]
            intent = merged_intent(repo, pr, commit)
            print(f"Runtime PR #{pr['number']} at {commit}: merge-time release:{intent}")
            levels.append(intent)
        level = max(levels, key=LEVELS.get)
        if level == "none":
            return None
        tag = increment(latest, level) if latest else "v1.0.0"
        sha = head
        reserve(repo, tag, sha)
    ensure_draft(repo, tag, sha, releases)
    return {"tag": tag, "sha": sha}


def publish(repo, tag, sha):
    version(tag)
    ref = api(f"repos/{repo}/git/ref/tags/{tag}")
    if ref["object"]["type"] != "commit" or ref["object"]["sha"] != sha:
        raise ValueError("Tag/source mismatch")
    releases = pages(f"repos/{repo}/releases")
    release = next(item for item in releases if item["tag_name"] == tag)
    if not release.get("body", "").startswith(MARKER):
        raise ValueError("Unmanaged release")
    if not release["draft"]:
        return
    # The workflow calls this only after tests, both image pushes and registry verification succeed.
    notes = api(f"repos/{repo}/releases/generate-notes", "POST", {"tag_name": tag})
    api(
        f"repos/{repo}/releases/{release['id']}",
        "PATCH",
        {
            "draft": False,
            "make_latest": "true",
            "body": MARKER + "\n\n" + notes["body"] + "\n\n_Prepared by an AI agent on behalf of the maintainers._",
        },
    )


def verify_source(tag, sha):
    version(tag)
    if git("rev-parse", "HEAD") != sha or git("rev-parse", f"{tag}^{{commit}}") != sha:
        raise ValueError("Release build source does not match reserved tag")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "publish", "classify", "verify-source"])
    parser.add_argument("--pr", type=int)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--initial-base", default="")
    parser.add_argument("--tag")
    parser.add_argument("--sha")
    args = parser.parse_args()
    if args.command == "classify":
        pr = api(f"repos/{args.repo}/pulls/{args.pr}")
        if pr["base"]["ref"] != "main":
            raise ValueError("Classification check expects a PR targeting main")
        print(release_intent([label["name"] for label in pr["labels"]]))
    elif args.command == "verify-source":
        verify_source(args.tag, args.sha)
    elif args.command == "publish":
        publish(args.repo, args.tag, args.sha)
    else:
        plan = prepare(args.repo, args.initial_base)
        if plan:
            with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                output.write(f"tag={plan['tag']}\nsha={plan['sha']}\n")


if __name__ == "__main__":
    main()
