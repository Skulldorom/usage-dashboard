"""Exercise release policy with in-memory GHCR/GitHub and Docker boundaries."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


promotion = load("promote_release_images")
images = load("verify_release_images")
existing = load("release_image_exists")
SHA = "a" * 40
TAG = "v2.7.3"
DIGESTS = {"backend": "sha256:" + "b" * 64, "frontend": "sha256:" + "f" * 64}
ALIASES = ("v2.7", "v2", "stable", "latest")


def release(tag=TAG, draft=False, prerelease=False):
    return {"id": 1, "tag_name": tag, "draft": draft, "prerelease": prerelease, "body": promotion.MARKER}


class RegistryFixture(unittest.TestCase):
    def setUp(self):
        self.releases = [release()]
        self.refs = {TAG: {"type": "commit", "sha": SHA}}
        self.registry = {(component, TAG): digest for component, digest in DIGESTS.items()}
        self.metadata = {(component, digest): self.labels(TAG) for component, digest in DIGESTS.items()}
        self.events = []
        self.writes = []
        self.registry_error = None
        self.pull_error = None
        self.write_error = None
        self.corrupt_write = False
        for target, replacement in (
            ("urllib.request.urlopen", self.urlopen),
            ("subprocess.run", self.run_command),
            ("subprocess.check_output", self.inspect),
        ):
            patcher = patch(target, side_effect=replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def labels(self, tag, sha=SHA):
        return {"org.opencontainers.image.version": tag, "org.opencontainers.image.revision": sha}

    def urlopen(self, request, timeout):
        self.assertEqual(timeout, 30)
        url = request if isinstance(request, str) else request.full_url
        if "/token?" in url:
            return io.BytesIO(b'{"token":"test-pull-token"}')
        component = url.split("usage-dashboard-", 1)[1].split("/", 1)[0]
        tag = url.split("/manifests/", 1)[1]
        self.events.append(("manifest", component, tag))
        self.assertEqual(request.get_header("Authorization"), "Bearer test-pull-token")
        self.assertIn("application/vnd.oci.image.manifest.v1+json", request.get_header("Accept"))
        if self.registry_error:
            raise self.registry_error
        digest = self.registry.get((component, tag))
        if digest is None:
            raise urllib.error.HTTPError(url, 404, "manifest unknown", {}, None)
        response = io.BytesIO(b"{}")
        response.headers = {"Docker-Content-Digest": digest}
        return response

    def run_command(self, command, **kwargs):
        self.assertTrue(kwargs["check"])
        if command[:2] == ["gh", "api"]:
            self.assertEqual(kwargs["timeout"], 60)
            path = command[2]
            self.events.append(("github", path))
            if "/releases?" in path:
                result = self.releases
            elif "/git/ref/tags/" in path:
                result = {"object": self.refs[path.rsplit("/", 1)[1]]}
            else:
                self.fail(f"Unexpected GitHub request: {command}")
            return subprocess.CompletedProcess(command, 0, json.dumps(result))
        self.assertEqual(kwargs["timeout"], 300)
        if command[:2] == ["docker", "pull"]:
            self.assertEqual(command[2:4], ["--platform", "linux/amd64"])
            self.events.append(("pull", command[-1]))
            if self.pull_error and self.pull_error in command[-1]:
                raise subprocess.CalledProcessError(1, command)
        elif command[:4] == ["docker", "buildx", "imagetools", "create"]:
            self.assertIn("--prefer-index=false", command)
            source, digest = command[-1].split("@")
            component = source.rsplit("-", 1)[1]
            self.events.append(("write", component))
            self.writes.append(command)
            if self.write_error == component:
                raise subprocess.CalledProcessError(1, command)
            self.assertEqual(digest, DIGESTS[component])
            for index, value in enumerate(command):
                if value == "--tag":
                    destination, tag = command[index + 1].rsplit(":", 1)
                    self.assertEqual(destination, source)
                    self.registry[component, tag] = "sha256:" + "0" * 64 if self.corrupt_write else digest
        else:
            self.fail(f"Unexpected command: {command}")
        return subprocess.CompletedProcess(command, 0)

    def inspect(self, command, **kwargs):
        self.assertEqual(command[:3], ["docker", "image", "inspect"])
        self.assertEqual(command[-2:], ["--format", "{{json .Config.Labels}}"])
        self.assertEqual(kwargs, {"text": True, "timeout": 30})
        source, digest = command[3].split("@")
        component = source.rsplit("-", 1)[1]
        self.events.append(("inspect", component, digest))
        return json.dumps(self.metadata[component, digest])

    def promote(self, **kwargs):
        return promotion.promote("owner/repo", **kwargs)

    def seed_alias(self, component, alias, tag, digest=None):
        digest = digest or "sha256:" + "c" * 64
        self.registry[component, alias] = digest
        self.metadata[component, digest] = self.labels(tag)


class PromotionTests(RegistryFixture):
    def test_both_verified_before_any_write_and_all_aliases_verified_after(self):
        self.assertEqual(self.promote(execute=True), DIGESTS)
        first_write = next(i for i, event in enumerate(self.events) if event[0] == "write")
        for component, digest in DIGESTS.items():
            self.assertIn(("inspect", component, digest), self.events[:first_write])
            for alias in ALIASES:
                self.assertEqual(self.registry[component, alias], digest)
                self.assertIn(("manifest", component, alias), self.events[first_write:])
        self.assertEqual(len(self.writes), 2)
        self.assertNotIn(f":{TAG}", " ".join(" ".join(c) for c in self.writes))

    def test_default_is_read_only(self):
        self.assertEqual(self.promote(), DIGESTS)
        self.assertFalse(self.writes)

    def test_missing_or_invalid_exact_image_never_writes(self):
        for component in DIGESTS:
            for invalid in (None, {}, self.labels("v1.0.0"), self.labels(TAG, "b" * 40)):
                with self.subTest(component=component, invalid=invalid):
                    self.registry = {(c, TAG): d for c, d in DIGESTS.items()}
                    self.metadata = {(c, d): self.labels(TAG) for c, d in DIGESTS.items()}
                    if invalid is None:
                        del self.registry[component, TAG]
                    else:
                        self.metadata[component, DIGESTS[component]] = invalid
                    with self.assertRaises(ValueError):
                        self.promote(execute=True)
                    self.assertFalse(self.writes)

    def test_pull_failure_never_writes(self):
        self.pull_error = "frontend"
        with self.assertRaises(subprocess.CalledProcessError):
            self.promote(execute=True)
        self.assertFalse(self.writes)

    def test_registry_failures_are_not_absence(self):
        for status in (401, 403, 429, 500):
            with self.subTest(status=status):
                self.registry_error = urllib.error.HTTPError("https://ghcr.io", status, "failure", {}, None)
                with self.assertRaises(urllib.error.HTTPError):
                    self.promote(execute=True)
                self.assertFalse(self.writes)
        self.registry_error = urllib.error.URLError("timed out")
        with self.assertRaises(urllib.error.URLError):
            self.promote(execute=True)
        self.assertFalse(self.writes)

    def test_invalid_registry_digest_never_writes(self):
        for digest in ("", "sha256:abc", "not-a-digest"):
            with self.subTest(digest=digest):
                self.registry["frontend", TAG] = digest
                with self.assertRaisesRegex(ValueError, "digest"):
                    self.promote(execute=True)
                self.assertFalse(self.writes)

    def test_preflight_checks_last_destination_before_writes(self):
        self.seed_alias("frontend", "latest", "unknown")
        with self.assertRaisesRegex(ValueError, "Unrecognized"):
            self.promote(execute=True)
        self.assertFalse(self.writes)

    def test_published_release_prevents_rollback(self):
        self.releases.append(release("v2.8.0"))
        with self.assertRaisesRegex(ValueError, "older"):
            self.promote(tag=TAG, sha=SHA, execute=True)
        self.assertFalse(self.writes)

    def test_each_moving_alias_prevents_partial_newer_rollback(self):
        for component in DIGESTS:
            for alias in ALIASES:
                with self.subTest(component=component, alias=alias):
                    self.registry = {(c, TAG): d for c, d in DIGESTS.items()}
                    self.seed_alias(component, alias, "v2.8.0")
                    with self.assertRaisesRegex(ValueError, "rollback"):
                        self.promote(execute=True)
                    self.assertFalse(self.writes)

    def test_equal_version_conflicting_digest_never_overwritten(self):
        self.seed_alias("frontend", "stable", TAG)
        with self.assertRaisesRegex(ValueError, "Conflicting digest"):
            self.promote(execute=True)
        self.assertFalse(self.writes)

    def test_older_and_legacy_dev_latest_can_be_promoted(self):
        for component in DIGESTS:
            for alias in ALIASES:
                old = "v0.0.0-dev.abc" if alias == "latest" else "v2.6.9"
                digest = "sha256:" + ("d" if alias == "latest" else "c") * 64
                self.seed_alias(component, alias, old, digest)
        self.promote(execute=True)
        self.assertEqual(len(self.writes), 2)

    def test_dev_metadata_not_accepted_on_stable(self):
        self.seed_alias("backend", "stable", "v0.0.0-dev.abc")
        with self.assertRaisesRegex(ValueError, "Unrecognized"):
            self.promote(execute=True)
        self.assertFalse(self.writes)

    def test_idempotent_rerun_verifies_without_writes(self):
        self.promote(execute=True)
        self.writes.clear()
        self.events.clear()
        self.promote(execute=True)
        self.assertFalse(self.writes)
        for component in DIGESTS:
            self.assertIn(("inspect", component, DIGESTS[component]), self.events)

    def test_partial_write_failure_rerun_reuses_successful_component(self):
        self.write_error = "frontend"
        with self.assertRaises(subprocess.CalledProcessError):
            self.promote(execute=True)
        for alias in ALIASES:
            self.assertEqual(self.registry["backend", alias], DIGESTS["backend"])
            self.assertNotIn(("frontend", alias), self.registry)
        self.write_error = None
        self.writes.clear()
        self.promote(execute=True)
        self.assertEqual(len(self.writes), 1)
        self.assertIn("usage-dashboard-frontend@", self.writes[0][-1])

    def test_partial_alias_recovery_only_writes_missing_aliases(self):
        self.registry["frontend", "stable"] = DIGESTS["frontend"]
        self.promote(execute=True)
        frontend = self.writes[-1]
        self.assertNotIn(images.repository("frontend") + ":stable", frontend)
        self.assertIn(images.repository("frontend") + ":latest", frontend)

    def test_postwrite_mismatch_fails(self):
        self.corrupt_write = True
        with self.assertRaisesRegex(ValueError, "Promotion verification failed"):
            self.promote(execute=True)

    def test_bootstrap_discovers_highest_numeric_published_release(self):
        self.releases = [
            release("v2.9.9"),
            release("v2.8.0", draft=True),
            release("v99.0.0", prerelease=True),
            release("v3.0.0-rc.1", prerelease=True),
            release(TAG),
            release("v2.10.0"),
        ]
        self.refs["v2.10.0"] = {"type": "commit", "sha": SHA}
        self.assertEqual(promotion.candidate("owner/repo"), ("v2.10.0", SHA))
        self.assertFalse(self.writes)

    def test_authoritative_release_state_rechecked_before_writes(self):
        original = self.inspect

        def inspect(command, **kwargs):
            result = original(command, **kwargs)
            if "usage-dashboard-frontend@" in command[3]:
                self.releases.append(release("v2.8.0"))
            return result

        with patch("subprocess.check_output", side_effect=inspect):
            with self.assertRaisesRegex(ValueError, "older"):
                self.promote(execute=True)
        self.assertFalse(self.writes)

    def test_bootstrap_without_published_stable_fails(self):
        self.releases = [release(TAG, draft=True), release("v3.0.0-rc.1", prerelease=True)]
        with self.assertRaisesRegex(ValueError, "No published"):
            self.promote(execute=True)
        self.assertFalse(self.writes)

    def test_newer_pending_release_blocks_bootstrap(self):
        self.releases.append(release("v2.8.0", draft=True))
        with self.assertRaisesRegex(ValueError, "newer reserved"):
            self.promote(execute=True)
        self.assertFalse(self.writes)

    def test_invalid_release_identity_never_writes(self):
        for ref, sha in (
            ({"type": "tag", "sha": SHA}, SHA),
            ({"type": "commit", "sha": "short"}, SHA),
            ({"type": "commit", "sha": SHA}, "b" * 40),
        ):
            with self.subTest(ref=ref, sha=sha):
                self.refs[TAG] = ref
                with self.assertRaises(ValueError):
                    self.promote(tag=TAG, sha=sha, execute=True)
                self.assertFalse(self.writes)

    def test_managed_pending_release_can_resume(self):
        self.releases = [release(TAG, draft=True)]
        self.promote(tag=TAG, sha=SHA, execute=True)
        self.assertEqual(len(self.writes), 2)

    def test_unmanaged_pending_release_cannot_promote(self):
        self.releases = [{**release(TAG, draft=True), "body": "manual draft"}]
        with self.assertRaisesRegex(ValueError, "Unmanaged"):
            self.promote(tag=TAG, sha=SHA, execute=True)
        self.assertFalse(self.writes)


class ExactArtifactTests(RegistryFixture):
    def test_exact_artifact_reused_only_with_matching_metadata(self):
        for component in DIGESTS:
            self.assertTrue(existing.exists(component, TAG, SHA))
        self.assertFalse(self.writes)

    def test_absent_artifact_allows_build_without_pull(self):
        self.registry.clear()
        self.assertFalse(existing.exists("backend", TAG, SHA))
        self.assertFalse(any(event[0] == "pull" for event in self.events))

    def test_mismatched_existing_artifact_fails_not_rebuild(self):
        for metadata in ({}, self.labels("v1.0.0"), self.labels(TAG, "other")):
            with self.subTest(metadata=metadata):
                self.metadata["backend", DIGESTS["backend"]] = metadata
                with self.assertRaises(ValueError):
                    existing.exists("backend", TAG, SHA)
        self.assertFalse(self.writes)

    def test_existing_artifact_registry_and_pull_errors_fail_closed(self):
        self.registry_error = urllib.error.HTTPError("https://ghcr.io", 503, "failure", {}, None)
        with self.assertRaises(urllib.error.HTTPError):
            existing.exists("backend", TAG, SHA)
        self.registry_error = None
        self.pull_error = "backend"
        with self.assertRaises(subprocess.CalledProcessError):
            existing.exists("backend", TAG, SHA)
        self.assertFalse(self.writes)


class WorkflowTests(unittest.TestCase):
    def workflow(self, name):
        return (ROOT / ".github/workflows" / name).read_text()

    def test_main_push_publishes_only_main_and_sha_not_stable(self):
        workflow = self.workflow("docker-images.yml")
        tags = workflow.split("          tags: |\n", 1)[1].split("\n\n", 1)[0]
        self.assertIn("flavor: latest=false", workflow)
        entries = [line.strip() for line in tags.splitlines()]
        self.assertEqual(len(entries), 4)
        self.assertIn("value=main,enable=${{ !inputs.release_tag", entries[0])
        self.assertIn("value=${{ inputs.release_tag }},enable=${{ inputs.release_tag != '' }}", entries[1])
        for entry in entries[2:]:
            self.assertIn("value=sha-", entry)
            self.assertIn("enable=${{ !inputs.release_tag }}", entry)
        for moving in ("value=latest", "value=stable", "type=semver"):
            self.assertNotIn(moving, tags)
        self.assertNotIn("promote_release_images.py", workflow)

    def test_release_build_requires_all_tests_and_postgres_migrations(self):
        workflow = self.workflow("docker-images.yml")
        self.assertIn("needs: [test-backend, test-backend-migrations, test-frontend]", workflow)
        for command in ("alembic upgrade head", "alembic downgrade base", "pytest tests/test_postgres_migrations.py"):
            self.assertIn(command, workflow)
        self.assertIn("component: backend", workflow)
        self.assertIn("component: frontend", workflow)
        self.assertIn("if: steps.existing.outputs.exists != 'true'", workflow)
        self.assertLess(
            workflow.index("python scripts/release_image_exists.py"), workflow.index("uses: docker/build-push-action")
        )

    def test_release_promotes_before_publishing_under_shared_lock(self):
        workflow = self.workflow("application-release.yml")
        publish = workflow.split("\n  publish:\n", 1)[1].split("\n  evaluate-remaining:", 1)[0]
        self.assertIn("needs: [prepare, images]", publish)
        self.assertNotIn("always()", publish)
        self.assertLess(
            publish.index("python scripts/promote_release_images.py"),
            publish.index("python scripts/application_release.py publish"),
        )
        self.assertIn('--tag "$TAG" --sha "$SHA" --execute', publish)
        bootstrap = self.workflow("stable-channels.yml")
        for text in (workflow, bootstrap):
            self.assertIn("group: application-release", text)
            self.assertIn("cancel-in-progress: false", text)
            self.assertIn("if: github.ref == 'refs/heads/main'", text)
        self.assertIn("default: false", bootstrap)
        self.assertIn('python scripts/promote_release_images.py "${args[@]}"', bootstrap)
        self.assertNotIn("--tag", bootstrap)
        self.assertNotIn("application_release.py publish", bootstrap)

    def test_compose_defaults_latest_and_supports_pinned_tag_and_image(self):
        compose = (ROOT / "docker-compose.yml").read_text()
        for component in DIGESTS:
            self.assertIn(
                f"image: ${{{component.upper()}_IMAGE:-ghcr.io/skulldorom/usage-dashboard-{component}:${{IMAGE_TAG:-latest}}}}",
                compose,
            )
        example = (ROOT / ".env.example").read_text()
        self.assertIn("IMAGE_TAG=latest", example)


if __name__ == "__main__":
    unittest.main()
