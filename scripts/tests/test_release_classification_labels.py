"""Exercise real reconciliation; substitute only GitHub's mutable API boundary."""

import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("labels", ROOT / "scripts/release_classification_labels.py")
labels = importlib.util.module_from_spec(spec)
spec.loader.exec_module(labels)


class GitHub:
    def __init__(self):
        self.pull = {"number": 42, "state": "open", "draft": False,
                     "base": {"ref": "main", "sha": "a" * 40},
                     "head": {"sha": "b" * 40}, "labels": []}
        self.events = [{"id": 1, "event": "commented", "created_at": "2026-11-12T09:00:00Z",
                        "actor": {"login": "maintainer"}, "body": "Review this PR"}]
        self.writes = []
        self.on_write = None

    def event(self, name, kind="labeled", time=None, actor="maintainer"):
        names = {item["name"] for item in self.pull["labels"]}
        names.add(name) if kind == "labeled" else names.discard(name)
        self.pull["labels"] = [{"name": name} for name in sorted(names)]
        self.events.append({"id": len(self.events) + 1, "event": kind,
                            "label": {"name": name, "color": "ededed"},
                            "actor": {"login": actor},
                            "created_at": time or f"2026-11-12T10:{len(self.events) // 60:02}:{len(self.events) % 60:02}Z"})

    def payload(self, action="labeled", name="release:patch"):
        return {"action": action, "number": 42, "pull_request": copy.deepcopy(self.pull),
                "label": {"name": name}, "sender": {"login": "maintainer"},
                "repository": {"full_name": "owner/repo"}}

    def api(self, path, method="GET", data=None):
        if method != "GET":
            self.writes.append((method, path, data))
            if self.on_write:
                self.on_write()
            if method == "POST":
                self.event(data["labels"][0], actor="github-actions[bot]")
            elif method == "DELETE":
                self.event(unquote(path.rsplit("/", 1)[1]), "unlabeled", actor="github-actions[bot]")
            else:
                raise AssertionError(method)
            return None
        if "/pulls/" in path:
            return copy.deepcopy(self.pull)
        if "/timeline?" in path:
            page = int(path.rsplit("page=", 1)[1])
            return copy.deepcopy(self.events[(page - 1) * 100:page * 100])
        raise AssertionError(path)

    def run(self, payload=None):
        with patch.object(labels, "api", self.api):
            labels.reconcile("owner/repo", payload or self.payload())

    def names(self):
        return {item["name"] for item in self.pull["labels"]}


class ReconciliationTests(unittest.TestCase):
    def test_open_default_and_duplicate_delivery(self):
        github = GitHub()
        payload = github.payload("opened")
        github.run(payload)
        github.run(payload)
        self.assertEqual(github.names(), {"release:patch"})
        self.assertEqual(len(github.writes), 1)

    def test_existing_selections_survive_open_reopen_sync_and_drafts(self):
        for intent in ("minor", "major", "none"):
            github = GitHub()
            github.pull["draft"] = True
            github.event(f"release:{intent}")
            for action in ("opened", "reopened", "synchronize", "ready_for_review"):
                github.run(github.payload(action))
            self.assertEqual(github.names(), {f"release:{intent}"})
            self.assertEqual(github.writes, [])

    def test_switch_default_to_all_selections_with_full_paginated_history(self):
        for intent in ("minor", "major", "none"):
            github = GitHub()
            github.run(github.payload("opened"))
            old = github.payload()
            for i in range(150):
                github.events.append({"id": 10 + i, "event": "commented", "body": "Review"})
            github.event(f"release:{intent}")
            payload = github.payload(name=f"release:{intent}")
            github.run(old)  # Delayed default-label delivery cannot win over live history.
            github.run(payload)
            github.run(old)
            self.assertEqual(github.names(), {f"release:{intent}"})
            self.assertEqual(len(github.writes), 2)

    def test_rapid_minor_to_major_latest_wins_even_out_of_order(self):
        github = GitHub()
        github.run(github.payload("opened"))
        github.event("release:minor")
        minor = github.payload(name="release:minor")
        github.event("release:major")
        major = github.payload(name="release:major")
        github.run(minor)
        github.run(major)
        self.assertEqual(github.names(), {"release:major"})

    def test_equal_time_selection_fails_closed(self):
        github = GitHub()
        for name in ("patch", "minor", "major"):
            github.event(f"release:{name}", time="2026-11-12T10:00:00Z")
        with self.assertRaisesRegex(ValueError, "Simultaneous"):
            github.run()
        self.assertEqual(github.writes, [])

    def test_remove_never_redefaults_including_delayed_open_event(self):
        github = GitHub()
        opened = github.payload("opened")
        github.run(opened)
        github.event("release:patch", "unlabeled")
        for payload in (opened, github.payload("unlabeled"), github.payload("reopened")):
            with self.assertRaisesRegex(ValueError, "exactly one"):
                github.run(payload)
        self.assertEqual(github.names(), set())
        self.assertEqual(len(github.writes), 1)

    def test_unrecognized_classification_fails_without_default(self):
        github = GitHub()
        github.event("release:banana")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            github.run(github.payload("opened"))
        self.assertEqual(github.writes, [])

    def test_concurrent_maintainer_edit_during_write_fails(self):
        github = GitHub()
        github.run(github.payload("opened"))
        github.event("release:minor")
        github.on_write = lambda: github.event("release:none")
        with self.assertRaisesRegex(ValueError, "Concurrent"):
            github.run()
        self.assertEqual(github.names(), {"release:minor", "release:none"})

    def test_closed_pr_is_not_mutated(self):
        github = GitHub()
        github.pull["state"] = "closed"
        github.run(github.payload("opened"))
        self.assertEqual(github.writes, [])


if __name__ == "__main__":
    unittest.main()
