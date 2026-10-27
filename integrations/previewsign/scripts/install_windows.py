"""Explicit-path Windows Chrome source rehearsal. No startup or machine registration."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import sys
from types import SimpleNamespace

from build_windows import reject_links
from package_macos_chrome import ASSETS, assemble, encoded, load_installation_facts

ROOT = Path(__file__).resolve().parents[1]
INSTALLATION_FACTS = load_installation_facts(ROOT / "installation.json")
NATIVE_HOST = INSTALLATION_FACTS["nativeHosts"]["windows"]
REGISTRY = "Software\\Google\\Chrome\\NativeMessagingHosts\\" + NATIVE_HOST
INVENTORY = ".previewsign-windows.json"
EXTENSION_ID = INSTALLATION_FACTS["chromeExtensionId"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def explicit(value):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("Absolute paths are required")
    reject_links(path)
    return path


def paths(args):
    destination = explicit(args.destination)
    profile = explicit(args.chrome_user_data_dir)
    for left, right in ((destination, profile), (destination, ROOT), (profile, ROOT)):
        if left == right or left in right.parents or right in left.parents:
            raise ValueError(
                "Source, destination and dedicated profile must not overlap"
            )
    return destination, profile


def registrations(registry):
    found = []
    for hive in (registry.HKEY_CURRENT_USER, registry.HKEY_LOCAL_MACHINE):
        for view in (registry.KEY_WOW64_32KEY, registry.KEY_WOW64_64KEY):
            try:
                with registry.OpenKey(
                    hive, REGISTRY, 0, registry.KEY_READ | view
                ) as key:
                    count = registry.QueryInfoKey(key)
                    try:
                        value, kind = registry.QueryValueEx(key, "")
                    except FileNotFoundError:
                        value, kind = None, None
                    found.append((hive, view, value, kind, count))
            except FileNotFoundError:
                pass
    return found


def load_owned(destination, profile):
    state = json.loads((destination / INVENTORY).read_text(encoding="utf-8"))
    if state.get("destination") != str(destination) or state.get("profile") != str(
        profile
    ):
        raise ValueError("Installation identity mismatch")
    files = state.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("Invalid ownership inventory")
    allowed = {
        "LICENSE",
        "LICENSE-SCOPE.md",
        "PROVENANCE.json",
        "README.txt",
        "installation.json",
        "windows_service_launcher.ps1",
        "native-host.json",
        "extension/manifest.json",
        "extension/workshop-origins.json",
        "bin/sign-extension-host.exe",
        "bin/sign-extension-service.exe",
        "notices/malloc_buf-MIT.txt",
        "notices/malloc_buf-0.0.6.provenance.json",
        *(f"extension/{asset}" for asset in ASSETS),
    }
    if set(files) not in (allowed, allowed - {"installation.json"}):
        raise ValueError("Ownership inventory file set changed")
    for name, expected in files.items():
        p = Path(name)
        if p.is_absolute() or ".." in p.parts or name not in allowed:
            raise ValueError("Invalid owned path")
        file = destination / p
        reject_links(file)
        if not file.is_file() or digest(file) != expected:
            raise ValueError("Owned file missing or changed; preserve for inspection")
    return state


def own_registration(registry, destination):
    entries = registrations(registry)
    for hive, view, value, kind, count in entries:
        if (
            hive != registry.HKEY_CURRENT_USER
            or view not in (registry.KEY_WOW64_32KEY, registry.KEY_WOW64_64KEY)
            or value not in (None, str(destination / "native-host.json"))
            or (value is not None and kind != registry.REG_SZ)
            or count[0] != 0
            or count[1] != (0 if value is None else 1)
        ):
            raise ValueError("Registration changed or belongs to another installation")
    return entries


def install(args, registry):
    destination, profile = paths(args)
    if destination.exists() or profile.exists():
        raise ValueError("Installation and dedicated profile must be new directories")
    if registrations(registry):
        raise ValueError(
            "Existing Chrome native registration preserved; do not overwrite it"
        )
    extension = json.loads(
        (ROOT / "extension/manifest.json").read_text(encoding="utf-8")
    )
    public_key = base64.b64decode(extension["key"], validate=True)
    derived_id = "".join(
        chr(ord("a") + int(nibble, 16))
        for nibble in hashlib.sha256(public_key).hexdigest()[:32]
    )
    if derived_id != EXTENSION_ID:
        raise ValueError("Extension key does not match the allowed native caller")
    report_path = explicit(args.build_report)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        report.get("result") != "passed"
        or report.get("lock_unchanged") is not True
        or report.get("target")
        not in ("x86_64-pc-windows-msvc", "aarch64-pc-windows-msvc")
    ):
        raise ValueError("A successful unchanged-lock Windows build report is required")
    binaries = {}
    for name in ("sign-extension-host", "sign-extension-service"):
        record = report["artifacts"][name]
        binary = explicit(record["path"])
        if (
            report_path.parent not in binary.parents
            or not binary.is_file()
            or digest(binary) != record["sha256"]
        ):
            raise ValueError("Build artifact does not match report")
        if (
            destination == binary
            or destination in binary.parents
            or binary in destination.parents
        ):
            raise ValueError("Build artifacts and installation overlap")
        binaries[name] = binary
    # Reuse the reviewed exact-origin Chrome assembly; it never runs binaries.
    assemble(
        SimpleNamespace(
            extension_dir=str(ROOT / "extension"),
            host_binary=str(binaries["sign-extension-host"]),
            output=str(destination),
            notice=[],
            synthetic=False,
            workshop_origin=[args.workshop_origin],
        )
    )
    for name in ("README.txt", "install.py", "checksums.json"):
        (destination / name).unlink()
    (destination / "README.txt").write_text(
        "Windows source rehearsal. Use scripts/install_windows.py from the matching source checkout for preflight and removal. No startup or service registration was created. Preserve this inventory. Runtime remains unqualified.\n",
        encoding="utf-8",
    )
    (destination / "bin/sign-extension-host").rename(
        destination / "bin/sign-extension-host.exe"
    )
    (destination / "bin/sign-extension-service.exe").write_bytes(
        binaries["sign-extension-service"].read_bytes()
    )
    (destination / "windows_service_launcher.ps1").write_bytes(
        (ROOT / "scripts/windows_service_launcher.ps1").read_bytes()
    )
    background = destination / "extension/background.js"
    background.write_bytes(
        f'const WORKSHOP_NATIVE_HOST = "{NATIVE_HOST}";\n'.encode()
        + background.read_bytes()
    )
    manifest = {
        "name": NATIVE_HOST,
        "description": "PreviewSign Windows source rehearsal",
        "path": str(destination / "bin/sign-extension-host.exe"),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"],
    }
    (destination / "native-host.json").write_bytes(encoded(manifest))
    # Persist recovery ownership before publishing anything in the registry.
    files = {
        str(p.relative_to(destination)).replace("\\", "/"): digest(p)
        for p in destination.rglob("*")
        if p.is_file()
    }
    (destination / INVENTORY).write_bytes(
        encoded(
            {
                "destination": str(destination),
                "profile": str(profile),
                "files": files,
                "qualification": False,
                "build_target": report["target"],
            }
        )
    )
    with registry.CreateKeyEx(
        registry.HKEY_CURRENT_USER,
        REGISTRY,
        0,
        registry.KEY_WRITE | registry.KEY_WOW64_64KEY,
    ) as key:
        registry.SetValueEx(
            key, "", 0, registry.REG_SZ, str(destination / "native-host.json")
        )
    print(
        "Installed for local source rehearsal only. No browser, service or device was started."
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "preflight", "remove", "run-human-service"):
        sub = subs.add_parser(name)
        sub.add_argument("--destination", required=True)
        sub.add_argument("--chrome-user-data-dir", required=True)
        if name == "install":
            sub.add_argument("--build-report", required=True)
            sub.add_argument("--workshop-origin", required=True)
    args = parser.parse_args(argv)
    try:
        if sys.platform != "win32":
            raise ValueError("Windows is required; nothing was changed")
        import winreg

        if args.command == "install":
            install(args, winreg)
            return 0
        destination, profile = paths(args)
        state = load_owned(destination, profile)
        entries = own_registration(winreg, destination)
        if args.command == "remove":
            for hive, view, *_ in entries:
                try:
                    winreg.DeleteKeyEx(hive, REGISTRY, view, 0)
                except FileNotFoundError:
                    pass  # Shared registry views may refer to the same key.
            for name in state["files"]:
                (destination / name).unlink()
            (destination / INVENTORY).unlink()
            owned_directories = {
                parent
                for name in state["files"]
                for parent in (destination / name).parents
                if parent != destination and destination in parent.parents
            }
            for p in sorted(
                owned_directories, key=lambda p: len(p.parts), reverse=True
            ):
                if p.is_dir() and not p.is_symlink() and not any(p.iterdir()):
                    p.rmdir()
            if not any(destination.iterdir()):
                destination.rmdir()
            print(
                "Owned registration/files removed. Browser profile and unrelated files preserved."
            )
        else:
            if not entries or any(
                entry[2] != str(destination / "native-host.json") for entry in entries
            ):
                raise ValueError(
                    "Owned registration is missing; do not start a ceremony"
                )
            if args.command == "run-human-service":
                print(
                    "Human stage only: keep this terminal open; Ctrl+C stops only this launched process. No automatic approval."
                )
                child = subprocess.Popen(
                    [
                        shutil.which("pwsh") or "powershell.exe",
                        "-NoProfile",
                        "-File",
                        str(destination / "windows_service_launcher.ps1"),
                        "-ServiceExecutable",
                        str(destination / "bin/sign-extension-service.exe"),
                        "-ServiceSha256",
                        state["files"]["bin/sign-extension-service.exe"],
                        "-HostSha256",
                        state["files"]["bin/sign-extension-host.exe"],
                    ]
                )
                try:
                    code = child.wait()
                    if code != 0:
                        raise ValueError(
                            "Helper launch was declined or failed; no automatic retry"
                        )
                except KeyboardInterrupt:
                    pass
                finally:
                    if child.poll() is None:
                        child.terminate()
                        child.wait(timeout=10)
            else:
                print(
                    "Files and owned registration match. Browser health, hardware and Windows qualification remain unverified."
                )
        return 0
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        subprocess.TimeoutExpired,
    ) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
