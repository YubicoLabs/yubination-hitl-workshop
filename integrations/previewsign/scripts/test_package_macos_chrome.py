import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest

import package_macos_chrome


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/package_macos_chrome.py"
EXPECTED_EXTENSION_ASSETS = (
    "background.js",
    "content.js",
    "page.js",
    "popup.html",
    "popup.js",
    "pin.html",
    "pin.js",
    "pin-setup.html",
    "pin-setup.js",
    "pin-change.html",
    "pin-change.js",
    "touch.html",
    "touch.js",
    "select.html",
    "select.js",
)


class PackagingTests(unittest.TestCase):
    def fixture(self, assemble=True):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        extension = base / "extension"
        extension.mkdir()
        (extension / "manifest.json").write_text(
            json.dumps(
                {
                    "manifest_version": 3,
                    "background": {"service_worker": "background.js"},
                    "browser_specific_settings": {"gecko": {"id": "excluded"}},
                }
            )
        )
        for name in EXPECTED_EXTENSION_ASSETS:
            (extension / name).write_text("// synthetic fixture\n")
        (extension / "credentials.json").write_text("must not ship")
        host = base / "dummy-host"
        host.write_text("#!/bin/sh\nexit 99\n")
        host.chmod(0o755)
        if assemble:
            self.command(
                "assemble",
                "--extension-dir",
                extension,
                "--host-binary",
                host,
                "--output",
                base / "package",
                "--synthetic",
                "--workshop-origin",
                "http://localhost:8000",
            )
        return base

    def command(self, *arguments, succeeds=True):
        result = subprocess.run(
            [sys.executable, "-I", "-S", str(CLI), *map(str, arguments)],
            capture_output=True,
            text=True,
        )
        if succeeds:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def installation(self, base, operation="install", succeeds=True):
        arguments = [
            operation,
            "--destination",
            base / "installed",
            "--chrome-user-data-dir",
            base / "chrome-temp",
        ]
        if operation == "install":
            arguments.extend(["--package", base / "package"])
        return self.command(*arguments, succeeds=succeeds)

    def snapshot(self, base):
        return {
            str(path.relative_to(base)): (
                path.stat().st_mode,
                path.read_bytes() if path.is_file() else None,
            )
            for path in base.rglob("*")
        }

    def test_participant_archive_installs_and_removes_without_source_checkout(self):
        import tarfile

        base = self.fixture()
        archive = base / "download.tar.gz"
        self.command("archive", "--package", base / "package", "--output", archive)
        extracted = base / "download"
        with tarfile.open(archive) as bundle:
            bundle.extractall(extracted)
        installer = extracted / "install.py"
        self.assertTrue(installer.is_file())
        self.assertEqual(
            json.loads((extracted / "installation.json").read_text()),
            json.loads((ROOT / "installation.json").read_text()),
        )
        self.assertIn(
            "installation.json",
            json.loads((extracted / "checksums.json").read_text()),
        )
        for operation in ("install", "remove"):
            args = [
                sys.executable,
                "-I",
                "-S",
                str(installer),
                operation,
                "--destination",
                str(base / "installed"),
                "--chrome-user-data-dir",
                str(base / "chrome-temp"),
            ]
            if operation == "install":
                args += ["--package", str(extracted)]
            result = subprocess.run(args, cwd=base, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((base / "installed").exists())
        self.assertFalse(
            (
                base
                / "chrome-temp/NativeMessagingHosts/com.example.sign_extension.json"
            ).exists()
        )

    def test_historical_install_without_facts_retains_owned_cleanup(self):
        base = self.fixture()
        self.installation(base)
        destination = base / "installed"
        inventory_path = destination / ".previewsign-install.json"
        inventory = json.loads(inventory_path.read_bytes())
        records = inventory["files"]
        records.pop("installation.json")
        (destination / "installation.json").unlink()
        package_records = {
            name: expected
            for name, expected in records.items()
            if name != "checksums.json"
        }
        checksum_data = (
            json.dumps(package_records, indent=2, sort_keys=True) + "\n"
        ).encode()
        (destination / "checksums.json").write_bytes(checksum_data)
        records["checksums.json"] = {
            "sha256": hashlib.sha256(checksum_data).hexdigest(),
            "mode": 0o644,
        }
        inventory_path.write_bytes(
            (json.dumps(inventory, indent=2, sort_keys=True) + "\n").encode()
        )

        self.installation(base, "remove")

        self.assertFalse(destination.exists())

    def test_newer_checkout_facts_do_not_redirect_owned_cleanup(self):
        base = self.fixture()
        self.installation(base)
        newer = base / "newer-checkout"
        scripts = newer / "scripts"
        scripts.mkdir(parents=True)
        shutil.copy2(CLI, scripts / CLI.name)
        changed = {
            "chromeExtensionId": "a" * 32,
            "nativeHosts": {
                "macos": "com.example.changed_host",
                "windows": "com.example.changed_windows_host",
            },
        }
        (newer / "installation.json").write_text(json.dumps(changed))

        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                str(scripts / CLI.name),
                "remove",
                "--destination",
                str(base / "installed"),
                "--chrome-user-data-dir",
                str(base / "chrome-temp"),
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((base / "installed").exists())
        self.assertFalse(
            (
                base
                / "chrome-temp/NativeMessagingHosts/com.example.sign_extension.json"
            ).exists()
        )

    def test_assemble_rejects_malformed_canonical_facts_before_output(self):
        base = self.fixture(assemble=False)
        source = base / "source"
        source.mkdir()
        (source / "installation.json").write_text(
            '{"chromeExtensionId":"bad","nativeHosts":{}}'
        )
        output = base / "must-not-exist"
        original_root = package_macos_chrome.ROOT
        package_macos_chrome.ROOT = source
        try:
            with self.assertRaises(ValueError):
                package_macos_chrome.assemble(
                    SimpleNamespace(
                        extension_dir=str(base / "extension"),
                        host_binary=str(base / "dummy-host"),
                        output=str(output),
                        notice=[],
                        synthetic=True,
                        workshop_origin=["http://localhost:8000"],
                    )
                )
        finally:
            package_macos_chrome.ROOT = original_root
        self.assertFalse(output.exists())

    def test_malloc_buf_supplement_ships_in_assembly_and_archive_inventory(
        self,
    ) -> None:
        base = self.fixture(assemble=False)
        extra = base / "other-NOTICE.txt"
        extra.write_bytes(b"Existing explicitly supplied notice\n")
        self.command(
            "assemble",
            "--extension-dir",
            base / "extension",
            "--host-binary",
            base / "dummy-host",
            "--output",
            base / "package",
            "--synthetic",
            "--workshop-origin",
            "http://localhost:8000",
            "--notice",
            extra,
        )
        package = base / "package"
        notice = "notices/malloc_buf-MIT.txt"
        inventory = "notices/malloc_buf-0.0.6.provenance.json"
        self.assertTrue((package / notice).is_file(), "official MIT notice missing")
        notice_bytes = (package / notice).read_bytes()
        expected_hash = (
            "aced7b57e474a63edb5a724954222bf7659c01ceef0e648a03af799582991db7"
        )
        self.assertEqual(hashlib.sha256(notice_bytes).hexdigest(), expected_hash)
        self.assertEqual((ROOT / notice).read_bytes(), notice_bytes)
        expected_inventory = {
            "package": "malloc_buf",
            "version": "0.0.6",
            "declared_license": "MIT",
            "original_mit_manifest_commit": "a7811e5f4c6f9685dd57ad9bfe34e9bf6b0ba4f9",
            "notice_revision": "d9a3e539642bd90e07df458d226b19cdfa606863",
            "notice_source": (
                "https://raw.githubusercontent.com/SSheldon/malloc_buf/"
                "d9a3e539642bd90e07df458d226b19cdfa606863/LICENSE"
            ),
            "notice_file": notice,
            "notice_sha256": expected_hash,
            "relationship": "later-upstream supplementation",
            "limitations": (
                "0.0.6 declares MIT but omitted a standalone notice. This later "
                "upstream notice is not claimed to have shipped with 0.0.6; "
                "supplementation is not legal approval or package qualification."
            ),
        }
        inventory_bytes = (package / inventory).read_bytes()
        self.assertEqual(json.loads(inventory_bytes), expected_inventory)
        self.assertEqual((ROOT / inventory).read_bytes(), inventory_bytes)
        records = json.loads((package / "checksums.json").read_bytes())
        for name in (notice, inventory, "notices/other-NOTICE.txt"):
            self.assertEqual(
                records[name],
                {
                    "sha256": hashlib.sha256((package / name).read_bytes()).hexdigest(),
                    "mode": 0o644,
                },
            )
        self.assertEqual(
            (package / "notices/other-NOTICE.txt").read_bytes(), extra.read_bytes()
        )
        for name in ("LICENSE", "LICENSE-SCOPE.md"):
            self.assertEqual((package / name).read_bytes(), (ROOT / name).read_bytes())
        archive = base / "download.tar.gz"
        self.command("archive", "--package", package, "--output", archive)
        with tarfile.open(archive) as bundle:
            self.assertEqual(json.load(bundle.extractfile("checksums.json")), records)
            for name in records:
                self.assertEqual(
                    bundle.extractfile(name).read(), (package / name).read_bytes()
                )
            self.assertEqual(bundle.extractfile(notice).read(), notice_bytes)
            self.assertEqual(
                json.load(bundle.extractfile(inventory)), expected_inventory
            )
        self.installation(base)
        installed_records = json.loads(
            (base / "installed/.previewsign-install.json").read_bytes()
        )["files"]
        for name in (notice, inventory):
            self.assertEqual(installed_records[name], records[name])
            self.assertEqual(
                (base / "installed" / name).read_bytes(), (package / name).read_bytes()
            )
        self.installation(base, "remove")
        self.assertFalse((base / "installed").exists())

    def test_supplement_tampering_fails_closed_at_package_and_install_boundary(
        self,
    ) -> None:
        for name in ("malloc_buf-MIT.txt", "malloc_buf-0.0.6.provenance.json"):
            for mutation in ("bytes", "missing", "mode"):
                with self.subTest(name=name, mutation=mutation):
                    base = self.fixture()
                    self.installation(base)
                    target = base / "package/notices" / name
                    if mutation == "bytes":
                        target.write_bytes(target.read_bytes() + b"modified\n")
                    elif mutation == "missing":
                        target.unlink()
                    else:
                        target.chmod(0o755)
                    before = self.snapshot(base)
                    self.command(
                        "archive",
                        "--package",
                        base / "package",
                        "--output",
                        base / "download.tar.gz",
                        succeeds=False,
                    )
                    self.installation(base, succeeds=False)
                    self.assertEqual(self.snapshot(base), before)
                    installed = base / "installed/notices" / name
                    installed.write_bytes(installed.read_bytes() + b"modified\n")
                    before = self.snapshot(base)
                    self.installation(base, "remove", succeeds=False)
                    self.assertEqual(self.snapshot(base), before)

    def test_explicit_notice_cannot_overwrite_bundled_supplement(self) -> None:
        for name in ("malloc_buf-MIT.txt", "malloc_buf-0.0.6.provenance.json"):
            with self.subTest(name=name):
                base = self.fixture(assemble=False)
                notice = base / name
                notice.write_bytes(b"replacement refused\n")
                before = self.snapshot(base)
                self.command(
                    "assemble",
                    "--extension-dir",
                    base / "extension",
                    "--host-binary",
                    base / "dummy-host",
                    "--output",
                    base / "package",
                    "--workshop-origin",
                    "http://localhost:8000",
                    "--notice",
                    notice,
                    succeeds=False,
                )
                self.assertEqual(self.snapshot(base), before)

    def test_workshop_invalid_scope_has_no_output(self):
        invalid = (
            None,
            "",
            "not-an-origin",
            "http://localhost/",
            "https://example.com/path",
            "https://example.com?",
            "https://example.com#",
            "https://user@example.com",
            "https://*.example.com",
            "http://localhost:65536",
            "http://localhost:",
            "file:" + "//localhost",
            "https://example.com\\path",
            " https://example.com",
            "https://exam\nple.com",
            "https://example.com%2f",
            "https://example..com",
        )
        for origin in invalid:
            with self.subTest(origin=origin):
                base = self.fixture(assemble=False)
                output = base / "new-parent/package"
                arguments = [
                    "assemble",
                    "--extension-dir",
                    base / "extension",
                    "--host-binary",
                    base / "dummy-host",
                    "--output",
                    output,
                ]
                if origin is not None:
                    arguments.extend(["--workshop-origin", origin])
                before = self.snapshot(base)
                self.command(*arguments, succeeds=False)
                self.assertEqual(self.snapshot(base), before)
                self.assertFalse(output.parent.exists())

    def test_workshop_canonical_ports_and_manifest(self):
        base = self.fixture(assemble=False)
        manifest_path = base / "extension/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["content_scripts"] = [
            {
                "matches": ["https://*/*"],
                "js": ["content.js"],
                "all_frames": True,
                "run_at": "document_start",
            }
        ]
        manifest["web_accessible_resources"] = [
            {"matches": ["https://*/*"], "resources": ["page.js"]}
        ]
        manifest_path.write_text(json.dumps(manifest))
        self.command(
            "assemble",
            "--extension-dir",
            base / "extension",
            "--host-binary",
            base / "dummy-host",
            "--output",
            base / "package",
            "--workshop-origin",
            "HTTPS://Example.COM:443",
            "--workshop-origin",
            "https://example.com",
            "--workshop-origin",
            "http://localhost:80",
            "--workshop-origin",
            "http://localhost:8000",
        )
        packaged = base / "package/extension"
        self.assertEqual(
            json.loads((packaged / "workshop-origins.json").read_text()),
            {
                "origins": [
                    "https://example.com",
                    "http://localhost",
                    "http://localhost:8000",
                ],
            },
        )
        result = json.loads((packaged / "manifest.json").read_text())
        patterns = ["https://example.com/*", "http://localhost/*"]
        self.assertEqual(result["content_scripts"][0]["matches"], patterns)
        self.assertFalse(result["content_scripts"][0]["all_frames"])
        self.assertEqual(result["web_accessible_resources"][0]["matches"], patterns)
        self.assertEqual(json.loads(manifest_path.read_text()), manifest)
        self.installation(base)
        self.installation(base, "remove")

    def test_missing_content_asset_rejected_without_output(self):
        base = self.fixture()
        for name in EXPECTED_EXTENSION_ASSETS:
            source = (base / "extension" / name).read_bytes()
            packaged = (base / "package/extension" / name).read_bytes()
            if name in {"background.js", "content.js", "page.js", "popup.js"}:
                self.assertIn(source, packaged)
            else:
                self.assertEqual(packaged, source)
        (base / "extension/content.js").unlink()
        output = base / "new-output-parent/package"
        before = self.snapshot(base)
        result = self.command(
            "assemble",
            "--extension-dir",
            base / "extension",
            "--host-binary",
            base / "dummy-host",
            "--output",
            output,
            "--synthetic",
            "--workshop-origin",
            "http://localhost:8000",
            succeeds=False,
        )
        self.assertIn("content.js", result.stderr)
        self.assertFalse(output.exists())
        self.assertFalse(output.parent.exists())
        self.assertEqual(self.snapshot(base), before)

    def test_package_profile_overlaps_rejected_unchanged(self):
        for overlap in ("equal", "package-ancestor", "profile-ancestor"):
            with self.subTest(overlap=overlap):
                base = self.fixture()
                package = base / "package"
                if overlap == "equal":
                    profile = package
                elif overlap == "package-ancestor":
                    profile = package / "chrome-temp"
                else:
                    profile = base / "chrome-temp"
                    profile.mkdir()
                    package = (base / "package").rename(profile / "package")
                before = self.snapshot(base)
                self.command(
                    "install",
                    "--package",
                    package,
                    "--destination",
                    base / "installed",
                    "--chrome-user-data-dir",
                    profile,
                    succeeds=False,
                )
                self.assertEqual(self.snapshot(base), before)

    def test_assembly_input_overlaps_rejected_unchanged(self):
        for overlap in (
            "extension-equal",
            "extension-ancestor",
            "extension-descendant",
            "host-equal",
            "host-ancestor",
            "host-descendant",
        ):
            with self.subTest(overlap=overlap):
                base = self.fixture()
                extension = base / "extension"
                host = base / "dummy-host"
                output = {
                    "extension-equal": extension,
                    "extension-ancestor": extension / "output",
                    "extension-descendant": base,
                    "host-equal": host,
                    "host-ancestor": host / "output",
                    "host-descendant": base,
                }[overlap]
                before = self.snapshot(base)
                self.command(
                    "assemble",
                    "--extension-dir",
                    extension,
                    "--host-binary",
                    host,
                    "--output",
                    output,
                    "--workshop-origin",
                    "http://localhost:8000",
                    succeeds=False,
                )
                self.assertEqual(self.snapshot(base), before)

    def test_partial_install_retry_and_remove(self):
        for operation in ("install", "remove"):
            for missing in ("host", "manifest", "both", "inventory-only"):
                with self.subTest(operation=operation, missing=missing):
                    base = self.fixture()
                    self.installation(base)
                    destination = base / "installed"
                    manifest = (
                        base
                        / "chrome-temp/NativeMessagingHosts/com.example.sign_extension.json"
                    )
                    neighbor = destination / "unowned.txt"
                    neighbor.write_text("keep")
                    profile_neighbor = manifest.parent / "unowned.json"
                    profile_neighbor.write_text("keep")
                    before = self.snapshot(base)
                    if missing in ("host", "both"):
                        (destination / "bin/sign-extension-host").unlink()
                        (destination / "bin").rmdir()
                    if missing == "inventory-only":
                        for path in destination.rglob("*"):
                            if path.is_file() and path.name not in (
                                ".previewsign-install.json",
                                "unowned.txt",
                            ):
                                path.unlink()
                    if missing in ("manifest", "both", "inventory-only"):
                        manifest.unlink()
                    if operation == "remove":
                        shutil.rmtree(base / "package")
                    self.installation(base, operation)
                    if operation == "install":
                        self.assertEqual(self.snapshot(base), before)
                    else:
                        self.assertFalse(manifest.exists())
                        self.assertEqual(list(destination.iterdir()), [neighbor])
                    self.installation(base, operation)
                    self.assertEqual(neighbor.read_text(), "keep")
                    self.assertEqual(profile_neighbor.read_text(), "keep")

    def test_partial_install_changes_and_damaged_inventory_preserved(self):
        for damage in ("owned-file", "inventory", "malformed-inventory"):
            with self.subTest(damage=damage):
                base = self.fixture()
                self.installation(base)
                destination = base / "installed"
                (destination / "bin/sign-extension-host").unlink()
                (
                    base
                    / "chrome-temp/NativeMessagingHosts/com.example.sign_extension.json"
                ).unlink()
                target = destination / (
                    "LICENSE" if damage == "owned-file" else ".previewsign-install.json"
                )
                target.write_bytes(
                    b"{"
                    if damage == "malformed-inventory"
                    else target.read_bytes() + b"\n"
                )
                before = self.snapshot(base)
                self.installation(base, succeeds=False)
                self.assertEqual(self.snapshot(base), before)
                self.installation(base, "remove", succeeds=False)
                self.assertEqual(self.snapshot(base), before)

    def test_synthetic_public_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            extension = base / "extension"
            extension.mkdir()
            (extension / "manifest.json").write_text(
                json.dumps(
                    {
                        "manifest_version": 3,
                        "name": "Synthetic fixture",
                        "version": "1.0",
                        "background": {"service_worker": "background.js"},
                    }
                )
            )
            for name in EXPECTED_EXTENSION_ASSETS:
                (extension / name).write_text("// synthetic fixture\n")
            host = base / "dummy-host"
            host.write_text("#!/bin/sh\nexit 99\n")
            host.chmod(0o755)
            package = base / "package"
            destination = base / "installed"
            profile = base / "chrome-temp"
            profile.mkdir()
            neighbor = profile / "unrelated.txt"
            neighbor.write_text("keep")

            def run(*arguments):
                result = subprocess.run(
                    [sys.executable, "-I", "-S", str(CLI), *map(str, arguments)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

            run(
                "assemble",
                "--extension-dir",
                extension,
                "--host-binary",
                host,
                "--output",
                package,
                "--synthetic",
                "--workshop-origin",
                "http://localhost:8000",
            )
            instructions = (package / "README.txt").read_text()
            self.assertNotIn("Capture all WebAuthn calls", instructions)
            self.assertIn(
                "Origin-scoped browser integration remains unreleased/unqualified.",
                instructions,
            )
            self.assertEqual(
                (package / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes()
            )
            run(
                "install",
                "--package",
                package,
                "--destination",
                destination,
                "--chrome-user-data-dir",
                profile,
            )
            manifest_path = (
                profile / "NativeMessagingHosts/com.example.sign_extension.json"
            )
            self.assertEqual(
                json.loads(manifest_path.read_text()),
                {
                    "name": "com.example.sign_extension",
                    "description": "previewSign FIDO Bridge Native Host",
                    "path": str(destination / "bin/sign-extension-host"),
                    "type": "stdio",
                    "allowed_origins": [
                        "chrome-extension://lcknfcjhoadggemnifljpplfjnppofdk/"
                    ],
                },
            )
            self.assertEqual(
                (destination / "bin/sign-extension-host").read_bytes(),
                host.read_bytes(),
            )
            run(
                "install",
                "--package",
                package,
                "--destination",
                destination,
                "--chrome-user-data-dir",
                profile,
            )
            shutil.rmtree(package)
            self.assertTrue(
                Path(json.loads(manifest_path.read_text())["path"]).is_file()
            )
            for _repeat in range(2):
                run(
                    "remove",
                    "--destination",
                    destination,
                    "--chrome-user-data-dir",
                    profile,
                )
            self.assertFalse(manifest_path.exists())
            self.assertFalse(destination.exists())
            self.assertEqual(neighbor.read_text(), "keep")

    def test_unmanaged_collisions_and_symlinks_preserved(self):
        for collision in (
            "destination",
            "manifest",
            "destination-symlink",
            "manifest-symlink",
            "ancestor-symlink",
        ):
            with self.subTest(collision=collision):
                base = self.fixture()
                victim = base / "victim"
                victim.mkdir()
                (victim / "keep").write_text("untouched")
                destination = base / "installed"
                manifest = (
                    base
                    / "chrome-temp/NativeMessagingHosts/com.example.sign_extension.json"
                )
                if collision == "destination":
                    destination.mkdir()
                    (destination / "keep").write_text("untouched")
                elif collision == "destination-symlink":
                    destination.symlink_to(victim, target_is_directory=True)
                elif collision == "ancestor-symlink":
                    (base / "chrome-temp").symlink_to(victim, target_is_directory=True)
                else:
                    manifest.parent.mkdir(parents=True)
                    if collision == "manifest":
                        manifest.write_text("untouched")
                    else:
                        manifest.symlink_to(victim / "keep")
                self.installation(base, succeeds=False)
                self.assertEqual((victim / "keep").read_text(), "untouched")
                if collision == "manifest":
                    self.assertEqual(manifest.read_text(), "untouched")
                if collision not in ("destination", "destination-symlink"):
                    self.assertFalse(destination.exists())

    def test_modified_owned_artifacts_fail_closed(self):
        for artifact in (
            "host",
            "manifest",
            "inventory",
            "host-symlink",
            "host-mode",
            "manifest-mode",
        ):
            with self.subTest(artifact=artifact):
                base = self.fixture()
                self.installation(base)
                destination = base / "installed"
                manifest = (
                    base
                    / "chrome-temp/NativeMessagingHosts/com.example.sign_extension.json"
                )
                host = destination / "bin/sign-extension-host"
                target = {
                    "host": host,
                    "manifest": manifest,
                    "inventory": destination / ".previewsign-install.json",
                    "manifest-mode": manifest,
                }.get(artifact, host)
                if artifact == "host-symlink":
                    target.unlink()
                    target.symlink_to(base / "dummy-host")
                elif artifact.endswith("-mode"):
                    target.chmod(0o600)
                else:
                    target.write_bytes(target.read_bytes() + b"\n")
                before = target.read_bytes()
                self.installation(base, succeeds=False)
                self.installation(base, "remove", succeeds=False)
                self.assertEqual(target.read_bytes(), before)
                self.assertTrue(manifest.exists())
                self.assertTrue((destination / "LICENSE").exists())
                if artifact == "host-symlink":
                    self.assertTrue(target.is_symlink())

    def test_changed_package_and_unrelated_neighbors(self):
        base = self.fixture()
        self.installation(base)
        neighbor = base / "installed/bin/unowned.txt"
        neighbor.write_text("keep")
        self.installation(base)
        provenance = json.loads((base / "package/PROVENANCE.json").read_text())
        self.assertTrue(provenance["host"]["synthetic"])
        self.assertFalse((base / "package/extension/credentials.json").exists())
        self.assertNotIn(
            "browser_specific_settings",
            json.loads((base / "package/extension/manifest.json").read_text()),
        )
        changed = base / "package/extension/background.js"
        changed.write_text("changed")
        self.installation(base, succeeds=False)
        self.installation(base, "remove")
        self.assertEqual(neighbor.read_text(), "keep")
        self.installation(base, "remove")
        self.assertEqual(neighbor.read_text(), "keep")

    def test_archive_manifest_is_always_unqualified(self):
        base = self.fixture()
        output = base / "previewsign-macos-arm64.tar.gz"
        self.command("archive", "--package", base / "package", "--output", output)
        manifest = json.loads((base / "manifest.json").read_text())
        self.assertFalse(manifest["qualified"])
        self.assertEqual(manifest["artifact"], output.name)
        self.assertEqual(
            manifest["sha256"], hashlib.sha256(output.read_bytes()).hexdigest()
        )
        self.assertEqual(manifest["workshopOrigins"], ["http://localhost:8000"])

    def test_explicit_paths_required_and_invalid_assembly_has_no_effects(self):
        for arguments in (("assemble",), ("install",), ("remove",)):
            with self.subTest(arguments=arguments):
                result = self.command(*arguments, succeeds=False)
                self.assertEqual(result.returncode, 2)
        base = self.fixture()
        self.command(
            "assemble",
            "--extension-dir",
            base / "extension",
            "--host-binary",
            base / "dummy-host",
            "--output",
            base / "package",
            "--workshop-origin",
            "http://localhost:8000",
            succeeds=False,
        )
        (base / "dummy-host").chmod(0o644)
        self.command(
            "assemble",
            "--extension-dir",
            base / "extension",
            "--host-binary",
            base / "dummy-host",
            "--output",
            base / "new-package",
            "--workshop-origin",
            "http://localhost:8000",
            succeeds=False,
        )
        self.assertFalse((base / "new-package").exists())


if __name__ == "__main__":
    unittest.main()
