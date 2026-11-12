"""Reconcile release labels from complete history, then enforce classification."""

import json
import os
import re
import subprocess
from urllib.parse import quote

LABELS = {"release:patch", "release:minor", "release:major", "release:none"}


def label_actions(action, labels, added="", timeline=None):
    current = set(labels) & LABELS
    events = [event for event in (timeline or [])
              if event.get("event") in ("labeled", "unlabeled")
              and event.get("label", {}).get("name", "").startswith("release:")]
    if action == "opened" and not events and not any(name.startswith("release:") for name in labels):
        return [("add", "release:patch")]
    if len(current) <= 1:
        return []
    if not events or any(not event.get("created_at") for event in events):
        raise ValueError("Conflicting classifications without complete event history")
    latest_time = max(event["created_at"] for event in events)
    latest = [event for event in events if event["created_at"] == latest_time]
    if len(latest) != 1 or latest[0]["event"] != "labeled":
        raise ValueError("Simultaneous or ambiguous classification changes; leave exactly one label")
    selected = latest[0]["label"]["name"]
    if selected not in current:
        raise ValueError("Classification history disagrees with live labels")
    return [("remove", name) for name in sorted(current - {selected})]


def api(path, method="GET", data=None):
    command = ["gh", "api", path, "--method", method]
    if data is not None:
        command += ["--input", "-"]
    result = subprocess.run(command, input=json.dumps(data) if data is not None else None,
                            text=True, capture_output=True, timeout=60)
    if result.returncode:
        status = re.search(r"HTTP (\d{3})", result.stderr or "")
        status = status.group(1) if status else "unknown"
        message = "GitHub request failed; no structured error message"
        try:
            body = json.loads(result.stdout)
            if isinstance(body, dict) and isinstance(body.get("message"), str):
                message = body["message"]
        except (TypeError, ValueError):
            pass
        # Never print raw stderr: gh debug output can contain authentication headers.
        for name in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
            token = os.environ.get(name)
            if token:
                message = message.replace(token, "[REDACTED]")
        message = re.sub(r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]+", "[REDACTED]", message)
        message = re.sub(r"(?i)(?:authorization|proxy-authorization|cookie|set-cookie)[^\r\n]*",
                         "[REDACTED header]", message)
        raise RuntimeError(f"GitHub API {method} failed (HTTP {status}, exit {result.returncode}): "
                           f"{json.dumps(message[:1000])}") from None
    return json.loads(result.stdout) if result.stdout.strip() else None


def snapshot(repo, number):
    pull = api(f"repos/{repo}/pulls/{number}")
    events = []
    for page in range(1, 101):
        batch = api(f"repos/{repo}/issues/{number}/timeline?per_page=100&page={page}")
        events.extend(batch)
        if len(batch) < 100:
            return pull, events
    raise ValueError("Classification timeline exceeds pagination limit")


def reconcile(repo, payload):
    number = payload["pull_request"]["number"]
    original = snapshot(repo, number)
    pull, events = original
    if pull["state"] != "open" or pull["base"]["ref"] != "main":
        return
    labels = {item["name"] for item in pull["labels"]}
    actions = label_actions(payload["action"], labels, timeline=events)
    for operation, label in actions:
        # GitHub has no label compare-and-swap; stop if a maintainer edited during this run.
        if snapshot(repo, number) != original:
            raise ValueError("PR changed during classification; retry after labels settle")
        path = f"repos/{repo}/issues/{number}/labels"
        if operation == "add":
            api(path, "POST", {"labels": [label]})
        else:
            api(f"{path}/{quote(label, safe='')}", "DELETE")
        updated = snapshot(repo, number)
        expected = labels | {label} if operation == "add" else labels - {label}
        actual = {item["name"] for item in updated[0]["labels"]}
        new_events = updated[1][len(original[1]):]
        if actual != expected or any(
            event.get("event") in ("labeled", "unlabeled")
            and event.get("label", {}).get("name", "").startswith("release:")
            and (event["label"]["name"] != label
                 or event["event"] != ("labeled" if operation == "add" else "unlabeled"))
            for event in new_events
        ):
            raise ValueError("Concurrent classification edit; leave exactly one label and retry")
        labels = actual
        original = updated
    final_state = snapshot(repo, number)
    if final_state != original:
        raise ValueError("PR changed before validation; retry after labels settle")
    final, _ = final_state
    classifications = [item["name"] for item in final["labels"] if item["name"].startswith("release:")]
    if len(classifications) != 1 or classifications[0] not in LABELS:
        raise ValueError("Every PR requires exactly one release:patch/minor/major/none label")
    print(classifications[0])


def main():
    with open(os.environ["GITHUB_EVENT_PATH"]) as event:
        reconcile(os.environ["GITHUB_REPOSITORY"], json.load(event))


if __name__ == "__main__":
    main()
