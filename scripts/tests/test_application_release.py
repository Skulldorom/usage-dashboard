"""External GitHub/registry boundaries are substituted; policy and git metadata run for real."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = load("application_release")
images = load("verify_release_images")
label_workflow = load("release_classification_labels")


class PolicyTests(unittest.TestCase):
    def test_increments_and_initial(self):
        for kind, expected in [("patch", "v1.2.10"), ("minor", "v1.3.0"), ("major", "v2.0.0"), ("none", None)]:
            self.assertEqual(release.increment("v1.2.9", kind), expected)

    def test_invalid(self):
        for tag in ["latest", "1.2.3", "v01.2.3", "v1.2", "v1.2.3-rc.1", "v1.2.3+build"]:
            with self.assertRaises(ValueError):
                release.increment(tag, "patch")
        with self.assertRaises(ValueError):
            release.increment("v1.2.3", "guess")

    def test_default_classification_is_only_applied_on_open(self):
        self.assertEqual(label_workflow.label_actions("opened", []), [("add", "release:patch")])
        for intent in ("minor", "major", "none"):
            self.assertEqual(label_workflow.label_actions("opened", {f"release:{intent}"}), [])
        self.assertEqual(label_workflow.label_actions("reopened", set()), [])
        self.assertEqual(label_workflow.label_actions("unlabeled", set(), "release:patch"), [])

    def test_label_change_removes_old_only_when_event_order_is_unambiguous(self):
        timeline = [
            {"event": "labeled", "label": {"name": "release:patch"}, "created_at": "1"},
            {"event": "labeled", "label": {"name": "release:minor"}, "created_at": "2"},
        ]
        self.assertEqual(
            label_workflow.label_actions("labeled", {"release:patch", "release:minor"}, "release:minor", timeline),
            [("remove", "release:patch")],
        )
        for ambiguous in (timeline + [{**timeline[-1], "label": {"name": "release:patch"}}],):
            with self.assertRaises(ValueError):
                label_workflow.label_actions("labeled", {"release:patch", "release:minor"}, "release:minor", ambiguous)
        with self.assertRaises(ValueError):
            label_workflow.label_actions("labeled", {"release:patch", "release:minor"}, "release:minor", [])

    def test_classification_workflow_uses_trusted_base_script_and_least_privilege(self):
        workflow = (ROOT / ".github/workflows/release-classification-labels.yml").read_text()
        self.assertIn("pull_request_target:", workflow)
        self.assertIn("issues: write", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("branches: [main]", workflow)
        self.assertIn("ref=$BASE_SHA", workflow)
        self.assertNotIn("actions/checkout", workflow)

    def test_reusable_permission_contract_and_remaining_evaluation(self):
        caller = (ROOT / ".github/workflows/application-release.yml").read_text()
        callee = (ROOT / ".github/workflows/docker-images.yml").read_text()
        image_job = caller.split("  images:")[1].split("  publish:")[0]
        for permission in ("contents: read", "packages: write", "pull-requests: read"):
            self.assertIn(permission, image_job)
        self.assertIn("if: github.event_name == 'pull_request'", callee)
        self.assertIn("branches: [main]", caller)
        self.assertIn("--skip-unbootstrapped-push", caller)
        self.assertIn("needs: [prepare, publish]", caller)
        self.assertIn('if [ "$head" != "$RELEASE_SHA" ]', caller)
        self.assertIn("actions: write", caller)

    def test_classification(self):
        for kind in release.LEVELS:
            self.assertEqual(release.classify([f"release:{kind}"], ["frontend/src/App.jsx"]), kind)
        self.assertEqual(release.classify(["release:major"], ["README.md", "backend/tests/test_auth.py"]), "none")
        for labels in [[], ["release:patch", "release:minor"], ["release:maybe"]]:
            with self.assertRaises(ValueError):
                release.classify(labels, ["backend/app/main.py"])
            with self.assertRaises(ValueError):
                release.classify(labels, ["README.md"])

    def test_atomic_competing_reservations(self):
        # GitHub's create-ref conflict is the only external boundary; verify the loser never moves it.
        error = subprocess.CalledProcessError(1, "gh")
        with patch.object(release, "api", side_effect=[error, {"object": {"type": "commit", "sha": "a"}}]) as api:
            release.reserve("owner/repo", "v1.0.0", "a")
            self.assertEqual(api.call_count, 2)
        with patch.object(release, "api", side_effect=[error, {"object": {"type": "commit", "sha": "b"}}]):
            with self.assertRaises(ValueError):
                release.reserve("owner/repo", "v1.0.0", "a")

    def test_registry_failure_never_succeeds(self):
        labels = {"org.opencontainers.image.version": "v1.2.3", "org.opencontainers.image.revision": "sha"}
        valid = json.dumps(labels)
        for results in [
            [valid, subprocess.CalledProcessError(1, "docker")],
            [valid, json.dumps({})],
            [valid, json.dumps({**labels, "org.opencontainers.image.version": "v1.0.0"})],
            [valid, json.dumps({**labels, "org.opencontainers.image.revision": "other"})],
        ]:
            with (
                patch.object(images.subprocess, "run"),
                patch.object(images.subprocess, "check_output", side_effect=results),
            ):
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    images.verify("v1.2.3", "sha")
        with (
            patch.object(images.subprocess, "run") as pull,
            patch.object(images.subprocess, "check_output", return_value=valid) as inspect,
        ):
            images.verify("v1.2.3", "sha")
            self.assertEqual(inspect.call_count, 2)
            self.assertEqual(pull.call_count, 2)
            self.assertIn("--platform", pull.call_args.args[0])

    def test_publish_failure_and_idempotency(self):
        draft = {"id": 1, "tag_name": "v1.0.0", "draft": True, "body": release.MARKER}
        ref = {"object": {"type": "commit", "sha": "a"}}
        with (
            patch.object(release, "pages", return_value=[draft]),
            patch.object(release, "api", side_effect=[ref, subprocess.CalledProcessError(1, "gh")]) as api,
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                release.publish("o/r", "v1.0.0", "a")
            self.assertFalse(any(call.args[1:2] == ("PATCH",) for call in api.call_args_list))
        with (
            patch.object(release, "pages", return_value=[{**draft, "draft": False}]),
            patch.object(release, "api", return_value=ref) as api,
        ):
            release.publish("o/r", "v1.0.0", "a")
            self.assertEqual(api.call_count, 1)
        with (
            patch.object(release, "pages", return_value=[draft]),
            patch.object(release, "api", side_effect=[ref, {"body": "Notes"}, {}]) as api,
        ):
            release.publish("o/r", "v1.0.0", "a")
            self.assertFalse(api.call_args.args[2]["draft"])

    def test_pagination_is_complete_and_bounded(self):
        with patch.object(release, "api", side_effect=[[{}] * 100, [{"id": 101}]]) as api:
            self.assertEqual(len(release.pages("repos/o/r/commits/sha/pulls")), 101)
            self.assertTrue(api.call_args.args[0].endswith("page=2"))
        with patch.object(release, "api", return_value=[{}] * 100):
            with self.assertRaisesRegex(ValueError, "pagination limit"):
                release.pages("repos/o/r/releases")

    def test_registry_pull_failure_stops_verification(self):
        with (
            patch.object(images.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "docker")),
            patch.object(images.subprocess, "check_output") as inspect,
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                images.verify("v1.0.0", "sha")
            inspect.assert_not_called()

    def test_classification_workflow_covers_all_main_prs(self):
        workflow = (ROOT / ".github/workflows/docker-images.yml").read_text()
        pr_trigger = workflow.split("  pull_request:")[1].split("  push:")[0]
        self.assertNotIn("paths:", pr_trigger)
        self.assertIn("branches: [main]", pr_trigger)
        self.assertIn("labeled, unlabeled", pr_trigger)
        self.assertIn("edited", pr_trigger)

    def test_merge_intent_ignores_post_merge_labels(self):
        pr = {"number": 42, "merged_at": "2026-11-12T12:00:00Z", "labels": [{"name": "release:major"}]}
        for intent in ("patch", "minor", "major", "none"):
            events = [
                {"event": "labeled", "label": {"name": "release:minor"}},
                {"event": "unlabeled", "label": {"name": "release:minor"}},
                {"event": "labeled", "label": {"name": f"release:{intent}"}},
                {"event": "merged", "commit_id": "sha", "created_at": pr["merged_at"]},
                {"event": "unlabeled", "label": {"name": f"release:{intent}"}},
                {"event": "labeled", "label": {"name": "release:major"}},
            ]
            with patch.object(release, "pages", return_value=events):
                self.assertEqual(release.merged_intent("o/r", pr, "sha"), intent)

    def test_merge_intent_fails_closed(self):
        pr = {"number": 42, "merged_at": "now", "labels": [{"name": "release:patch"}]}
        merged = {"event": "merged", "commit_id": "sha", "created_at": "now"}
        labeled = {"event": "labeled", "label": {"name": "release:patch"}}
        for events in [
            [],
            [merged, labeled],
            [labeled],
            [labeled, {**merged, "commit_id": "other"}],
            [labeled, {**merged, "created_at": "later"}],
            [labeled, {"event": "labeled", "label": {"name": "release:none"}}, merged],
            [{"event": "unlabeled", "label": {"name": "release:minor"}}, labeled, merged],
        ]:
            with patch.object(release, "pages", return_value=events):
                with self.assertRaises(ValueError):
                    release.merged_intent("o/r", pr, "sha")

    def test_workflow_gates_and_metadata(self):
        workflow = (ROOT / ".github/workflows/application-release.yml").read_text()
        build = (ROOT / ".github/workflows/docker-images.yml").read_text()
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("branches: [main]", workflow)
        self.assertIn("needs: [prepare, images]", workflow)
        self.assertLess(
            workflow.index("python scripts/verify_release_images.py"),
            workflow.index("python scripts/application_release.py publish"),
        )
        self.assertIn("needs: [test-backend, test-backend-migrations, test-frontend]", build)
        self.assertIn("ref: ${{ inputs.release_sha || github.sha }}", build)
        self.assertIn("APP_VERSION=${{ inputs.release_tag || format('v0.0.0-dev.{0}', github.sha) }}", build)
        self.assertNotIn("publish-release:", build)
        self.assertIn("APP_VERSION=${APP_VERSION}", (ROOT / "backend/Dockerfile").read_text())
        self.assertIn("VITE_APP_VERSION=$APP_VERSION", (ROOT / "frontend/Dockerfile").read_text())


class GitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, self.cwd)
        self.run_git("init", "-b", "main")
        self.run_git("config", "user.name", "Test")
        self.run_git("config", "user.email", "test@example.com")
        self.run_git("commit", "--allow-empty", "-m", "baseline")
        self.base = self.run_git("rev-parse", "HEAD")
        Path("backend/app").mkdir(parents=True)
        Path("backend/app/main.py").write_text("pass\n")
        self.run_git("add", ".")
        self.run_git("commit", "-m", "feature")
        self.head = self.run_git("rev-parse", "HEAD")
        self.run_git("remote", "add", "origin", self.tmp.name)
        self.run_git("fetch", "origin")
        self.real_merged_intent = release.merged_intent
        self.timeline_patch = patch.object(release, "merged_intent", side_effect=self.fixture_intent)
        self.timeline_patch.start()
        self.addCleanup(self.timeline_patch.stop)

    def fixture_intent(self, repo, pr, commit):
        events = [{"event": "labeled", "label": label} for label in pr["labels"]]
        events.append({"event": "merged", "commit_id": commit, "created_at": pr["merged_at"]})
        with patch.object(release, "pages", return_value=events):
            return self.real_merged_intent(repo, pr, commit)

    def run_git(self, *args):
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()

    def test_initial_release_and_resume(self):
        prs = [
            {
                "number": 1,
                "merged_at": "now",
                "base": {"ref": "main"},
                "merge_commit_sha": self.head,
                "labels": [{"name": "release:minor"}],
            }
        ]
        with (
            patch.object(release, "pages", side_effect=lambda path: prs if "/commits/" in path else []),
            patch.object(release, "reserve") as reserve,
            patch.object(release, "ensure_draft"),
        ):
            self.assertEqual(release.prepare("o/r", self.base), {"tag": "v1.0.0", "sha": self.head})
            reserve.assert_called_once_with("o/r", "v1.0.0", self.head)
            with self.assertRaises(ValueError):
                release.prepare("o/r", "")
        # All tags below exist only in a disposable repository and are never pushed.
        self.run_git("tag", "v1.0.0")
        with (
            patch.object(release, "pages", return_value=[]),
            patch.object(release, "ensure_draft"),
            patch.object(release, "reserve") as reserve,
        ):
            self.assertEqual(release.prepare("o/r", ""), {"tag": "v1.0.0", "sha": self.head})
            reserve.assert_not_called()

    def test_existing_release_increments_and_no_release(self):
        self.run_git("tag", "v1.2.9", self.base)
        published = [{"tag_name": "v1.2.9", "draft": False, "prerelease": False}]
        for level, expected in [("patch", "v1.2.10"), ("minor", "v1.3.0"), ("major", "v2.0.0"), ("none", None)]:
            prs = [
                {
                    "number": 1,
                    "merged_at": "now",
                    "base": {"ref": "main"},
                    "merge_commit_sha": self.head,
                    "labels": [{"name": f"release:{level}"}],
                }
            ]
            with (
                patch.object(release, "pages", side_effect=lambda path: prs if "/commits/" in path else published),
                patch.object(release, "reserve") as reserve,
                patch.object(release, "ensure_draft"),
            ):
                result = release.prepare("o/r", "")
                self.assertEqual(result, {"tag": expected, "sha": self.head} if expected else None)
                self.assertEqual(reserve.call_count, 1 if expected else 0)
        with (
            patch.object(release, "pages", side_effect=lambda path: [] if "/commits/" in path else published),
            patch.object(release, "reserve") as reserve,
        ):
            with self.assertRaises(ValueError):
                release.prepare("o/r", "")
            reserve.assert_not_called()

    def test_batch_uses_highest_intent_once(self):
        self.run_git("tag", "v1.2.3", self.base)
        first = self.head
        Path("backend/app/main.py").write_text("feature\n")
        self.run_git("add", ".")
        self.run_git("commit", "-m", "next")
        second = self.run_git("rev-parse", "HEAD")

        def prs(path, *args, **kwargs):
            commit = second if second in path else first
            return [
                {
                    "number": 1,
                    "merged_at": "now",
                    "base": {"ref": "main"},
                    "merge_commit_sha": commit,
                    "labels": [{"name": "release:minor" if commit == first else "release:patch"}],
                }
            ]

        with (
            patch.object(
                release,
                "pages",
                side_effect=lambda path: (
                    prs(path) if "/commits/" in path else [{"tag_name": "v1.2.3", "draft": False, "prerelease": False}]
                ),
            ),
            patch.object(release, "reserve") as reserve,
            patch.object(release, "ensure_draft"),
        ):
            self.assertEqual(release.prepare("o/r", ""), {"tag": "v1.3.0", "sha": second})
            reserve.assert_called_once_with("o/r", "v1.3.0", second)

    def test_runtime_none_is_included_in_later_eligible_batch(self):
        self.run_git("tag", "v1.2.3", self.base)
        first = self.head
        Path("backend/app/main.py").write_text("feature\n")
        self.run_git("add", ".")
        self.run_git("commit", "-m", "next")
        second = self.run_git("rev-parse", "HEAD")

        def prs(path, *args, **kwargs):
            commit = second if second in path else first
            return [
                {
                    "number": 1,
                    "merged_at": "now",
                    "base": {"ref": "main"},
                    "merge_commit_sha": commit,
                    "labels": [{"name": "release:minor" if commit == first else "release:none"}],
                }
            ]

        with (
            patch.object(
                release,
                "pages",
                side_effect=lambda path: (
                    prs(path) if "/commits/" in path else [{"tag_name": "v1.2.3", "draft": False, "prerelease": False}]
                ),
            ),
            patch.object(release, "reserve") as reserve,
            patch.object(release, "ensure_draft"),
        ):
            self.assertEqual(release.prepare("o/r", ""), {"tag": "v1.3.0", "sha": second})
            reserve.assert_called_once_with("o/r", "v1.3.0", second)

    def test_docs_only_and_source_verification(self):
        self.run_git("tag", "v1.0.0")
        release.verify_source("v1.0.0", self.head)
        with self.assertRaises(ValueError):
            release.verify_source("v1.0.0", self.base)
        Path("README.md").write_text("docs")
        self.run_git("add", ".")
        self.run_git("commit", "-m", "docs")
        with (
            patch.object(release, "pages", return_value=[{"tag_name": "v1.0.0", "draft": False, "prerelease": False}]),
            patch.object(release, "reserve") as reserve,
        ):
            self.assertIsNone(release.prepare("o/r", ""))
            reserve.assert_not_called()

    def test_automatic_push_waits_for_reviewed_first_release_bootstrap(self):
        with (
            patch.object(release, "pages", return_value=[]),
            patch.object(release, "reserve") as reserve,
            patch.object(release, "ensure_draft") as draft,
        ):
            self.assertIsNone(release.prepare("o/r", "", skip_unbootstrapped_push=True))
            reserve.assert_not_called()
            draft.assert_not_called()

    def test_bootstrap_always_one_stable_version(self):
        for kind in ["patch", "minor", "major", "none"]:
            with self.subTest(kind=kind):
                prs = [
                    {
                        "number": 1,
                        "merged_at": "now",
                        "base": {"ref": "main"},
                        "merge_commit_sha": self.head,
                        "labels": [{"name": f"release:{kind}"}],
                    }
                ]
                with (
                    patch.object(release, "pages", side_effect=lambda path: prs if "/commits/" in path else []),
                    patch.object(release, "reserve") as reserve,
                    patch.object(release, "ensure_draft"),
                ):
                    expected = {"tag": "v1.0.0", "sha": self.head} if kind != "none" else None
                    self.assertEqual(release.prepare("o/r", self.base), expected)
                    self.assertEqual(reserve.call_count, 0 if kind == "none" else 1)

    def test_bootstrap_rejects_legacy_substable_reservation(self):
        self.run_git("tag", "v0.1.0")
        with patch.object(release, "pages", return_value=[]), patch.object(release, "ensure_draft") as draft:
            with self.assertRaisesRegex(ValueError, "must be v1.0.0"):
                release.prepare("o/r", "")
            draft.assert_not_called()

    def test_real_merge_and_out_of_order_prs(self):
        self.run_git("tag", "v1.0.0", self.head)
        self.run_git("checkout", "-b", "feature", self.base)
        Path("backend/app").mkdir(parents=True, exist_ok=True)
        Path("backend/app/other.py").write_text("feature")
        self.run_git("add", ".")
        self.run_git("commit", "-m", "older authored feature")
        self.run_git("checkout", "main")
        self.run_git("merge", "--no-ff", "feature", "-m", "Merge PR")
        merged = self.run_git("rev-parse", "HEAD")
        unrelated = {
            "number": 1,
            "merged_at": "now",
            "base": {"ref": "main"},
            "merge_commit_sha": self.base,
            "labels": [{"name": "release:major"}],
        }
        intended = {**unrelated, "merge_commit_sha": merged, "labels": [{"name": "release:patch"}]}
        with (
            patch.object(
                release,
                "pages",
                side_effect=lambda path: (
                    [unrelated, intended]
                    if "/commits/" in path
                    else [{"tag_name": "v1.0.0", "draft": False, "prerelease": False}]
                ),
            ),
            patch.object(release, "reserve"),
            patch.object(release, "ensure_draft"),
        ):
            self.assertEqual(release.prepare("o/r", ""), {"tag": "v1.0.1", "sha": merged})

    def test_resume_excludes_concurrent_merges(self):
        self.run_git("tag", "v1.0.0")
        reserved = self.head
        Path("backend/app/main.py").write_text("new merge after reservation")
        self.run_git("add", ".")
        self.run_git("commit", "-m", "later merge")
        with (
            patch.object(release, "pages", return_value=[]),
            patch.object(release, "ensure_draft"),
            patch.object(release, "reserve") as reserve,
        ):
            self.assertEqual(release.prepare("o/r", ""), {"tag": "v1.0.0", "sha": reserved})
            reserve.assert_not_called()

    def test_real_merge_and_squash_changed_paths(self):
        for mode in ("merge", "squash"):
            with self.subTest(mode=mode):
                self.run_git("checkout", "-B", f"target-{mode}", self.head)
                self.run_git("checkout", "-b", f"feature-{mode}")
                Path("frontend/src").mkdir(parents=True, exist_ok=True)
                Path("frontend/src/New.jsx").write_text("feature")
                self.run_git("rm", "backend/app/main.py")
                self.run_git("add", ".")
                self.run_git("commit", "-m", "runtime feature")
                self.run_git("checkout", f"target-{mode}")
                Path("README.md").write_text("independent main change")
                self.run_git("add", ".")
                self.run_git("commit", "-m", "main docs")
                if mode == "merge":
                    self.run_git("merge", "--no-ff", f"feature-{mode}", "-m", "merge feature")
                else:
                    self.run_git("merge", "--squash", f"feature-{mode}")
                    self.run_git("commit", "-m", "squash feature")
                commit = self.run_git("rev-parse", "HEAD")
                paths = release.changed_paths(commit)
                self.assertEqual(set(paths), {"backend/app/main.py", "frontend/src/New.jsx"})
                self.assertTrue(release.releasable(paths))
                parent_count = len(self.run_git("rev-list", "--parents", "-n", "1", commit).split()) - 1
                self.assertEqual(parent_count, 2 if mode == "merge" else 1)

    def test_native_build_metadata(self):
        Path("scripts").mkdir()
        Path("frontend").mkdir()
        Path("deploy").mkdir()
        Path("bin").mkdir()
        Path("scripts/build-release.sh").write_text((ROOT / "scripts/build-release.sh").read_text())
        Path("bin/npm").write_text('#!/bin/sh\nprintf "%s" "$VITE_APP_VERSION" > ../frontend-version\n')
        Path("bin/npm").chmod(0o755)
        env = {**os.environ, "PATH": str(Path("bin").resolve()) + os.pathsep + os.environ["PATH"]}
        self.run_git("add", ".")
        self.run_git("commit", "-m", "build")
        self.run_git("tag", "v1.2.3")
        subprocess.run(["sh", "scripts/build-release.sh"], env=env, check=True, capture_output=True)
        self.assertEqual(Path("frontend-version").read_text(), "v1.2.3")
        self.assertEqual(Path("deploy/version.env").read_text(), "APP_VERSION=v1.2.3\n")
        Path("backend/app/main.py").write_text("changed\n")
        subprocess.run(["sh", "scripts/build-release.sh"], env=env, check=True, capture_output=True)
        self.assertIn("-dev.", Path("frontend-version").read_text())
        self.assertTrue(Path("frontend-version").read_text().endswith(".dirty"))


if __name__ == "__main__":
    unittest.main()
