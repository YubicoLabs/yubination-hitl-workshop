"""Assemble an exact-origin Windows x64 participant ZIP; never run executables."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import zipfile

from build_windows import reject_links
from package_macos_chrome import (
    ROOT,
    assemble,
    encoded,
    load_installation_facts,
    workshop_origin,
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def package(args):
    facts = load_installation_facts(ROOT / "installation.json")
    reject_links(args.build_report.absolute())
    reject_links(args.output.absolute())
    report_path = Path(os.path.abspath(args.build_report))
    output = Path(os.path.abspath(args.output))
    reject_links(report_path)
    reject_links(output)
    if output.exists():
        raise ValueError("Output must be a new directory")
    if output == ROOT or ROOT in output.parents or output in ROOT.parents:
        raise ValueError("Output must not overlap source")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        report.get("result") != "passed"
        or report.get("lock_unchanged") is not True
        or report.get("target") != "x86_64-pc-windows-msvc"
    ):
        raise ValueError("Successful locked Windows x64 build required")
    binaries = {}
    for name in ("sign-extension-host", "sign-extension-service"):
        record = report["artifacts"][name]
        binary = Path(record["path"])
        reject_links(binary)
        if not binary.is_absolute() or report_path.parent not in binary.parents:
            raise ValueError("Build artifacts must be inside the report directory")
        data = binary.read_bytes()
        if digest(data) != record["sha256"] or not data.startswith(b"MZ"):
            raise ValueError("Windows executable does not match build report")
        binaries[name] = (binary, data)
    origins = sorted(set(workshop_origin(value) for value in args.workshop_origin))
    # Reuse workshop-mode assembly and its license/notice inventory.
    with tempfile.TemporaryDirectory() as temporary:
        staged = Path(temporary) / "package"
        assemble(
            SimpleNamespace(
                extension_dir=str(ROOT / "extension"),
                host_binary=str(binaries["sign-extension-host"][0]),
                output=str(staged),
                notice=[],
                synthetic=False,
                workshop_origin=origins,
            )
        )
        files = {
            p.relative_to(staged).as_posix(): p.read_bytes()
            for p in staged.rglob("*")
            if p.is_file()
        }
    for name in ("install.py", "checksums.json", "bin/sign-extension-host"):
        del files[name]
    files["extension/background.js"] = (
        f'const WORKSHOP_NATIVE_HOST = "{facts["nativeHosts"]["windows"]}";\n'.encode()
        + files["extension/background.js"]
    )
    for name, (_, data) in binaries.items():
        files[f"bin/{name}.exe"] = data
    files["install.ps1"] = (ROOT / "scripts/windows_participant.ps1").read_bytes()
    files["windows_service_launcher.ps1"] = (
        ROOT / "scripts/windows_service_launcher.ps1"
    ).read_bytes()
    files["PROVENANCE.json"] = encoded(
        {
            "build": {
                key: report.get(key)
                for key in (
                    "target",
                    "source_revision",
                    "source_dirty",
                    "lock_sha256",
                    "tools",
                )
            },
            "artifacts": {
                name: {"sha256": digest(data)} for name, (_, data) in binaries.items()
            },
            "qualification": "not performed",
            "notices": "See bundled notices/malloc_buf-0.0.6.provenance.json.",
        }
    )
    files["README.txt"] = (
        "PreviewSign Windows x64 evaluation package\n"
        "Requires Windows x64, PowerShell 5.1+ and Google Chrome installed under Program Files.\n"
        "Extract into a NEW stable folder; keep it there until cleanup.\n"
        "Compare the ZIP SHA-256 with the workshop page before extraction.\n"
        "In PowerShell, from this extracted folder:\n"
        "  .\\install.ps1 -Command Install -ChromeUserDataDir C:\\Work\\previewsign-chrome\n"
        "  .\\install.ps1 -Command Preflight -ChromeUserDataDir C:\\Work\\previewsign-chrome\n"
        "Load this folder's extension subfolder in that dedicated Chrome profile.\n"
        "Check device-free helper health before the human ceremony.\n"
        "  .\\install.ps1 -Command RunHumanService -ChromeUserDataDir C:\\Work\\previewsign-chrome\n"
        "Keep that terminal open; Ctrl+C stops its process. Review action and supply PIN/touch yourself.\n"
        "After the exercise remove only this extension, restore Developer mode, close Chrome, then:\n"
        "  .\\install.ps1 -Command Remove -ChromeUserDataDir C:\\Work\\previewsign-chrome\n"
        "HKCU Chrome registration is user-wide. Existing registration blocks installation.\n"
        "No compilation, Python or persistent startup is required.\n"
        "The human signing stage requires explicit UAC consent for the temporary helper only.\n"
        "Keep Chrome unelevated. Alternate-admin credentials are unsupported.\n"
        "Stop if Windows, PowerShell or Chrome policy blocks the workflow.\n"
        "This experimental package is unsigned; assembly does not establish Windows hardware acceptance.\n"
    ).encode("utf-8")
    files["checksums.json"] = encoded(
        {name: digest(data) for name, data in files.items()}
    )
    output.mkdir(parents=True, exist_ok=False)
    archive = output / "previewsign-windows-x64.zip"
    with zipfile.ZipFile(
        archive, "x", compression=zipfile.ZIP_DEFLATED
    ) as package_file:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            package_file.writestr(info, data)
    (output / "manifest.json").write_bytes(
        encoded(
            {
                "schemaVersion": 1,
                "platform": "windows-x64",
                "artifact": archive.name,
                "format": "zip",
                "byteSize": archive.stat().st_size,
                "sha256": digest(archive.read_bytes()),
                "workshopOrigins": origins,
                "sourceRevision": report.get("source_revision"),
                "sourceDirty": report.get("source_dirty"),
                "distribution": "local-evaluation",
                "qualified": False,
            }
        )
    )
    print(f"Created {archive}; Windows participant qualification remains pending.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workshop-origin", required=True, action="append")
    try:
        package(parser.parse_args())
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
