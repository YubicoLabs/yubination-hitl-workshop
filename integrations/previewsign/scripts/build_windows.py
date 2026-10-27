#!/usr/bin/env python3
"""Build diagnostic Windows executables without installing or executing them."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

TARGETS = ("x86_64-pc-windows-msvc", "aarch64-pc-windows-msvc")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_links(path: Path) -> None:
    for component in (path, *path.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(
            info, "st_file_attributes", 0
        ) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise ValueError("Output path contains a symlink or reparse point")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--target", required=True, choices=TARGETS)
    args = parser.parse_args()
    report = None
    output = Path(os.path.abspath(args.output))
    try:
        if sys.platform != "win32":
            raise ValueError("Windows is required; no build was started")
        if sys.version_info < (3, 11):
            raise ValueError("Python 3.11 or newer is required")
        source = Path(__file__).resolve().parents[1]
        repository = source.parents[1]
        native = source / "native"
        lock = native / "Cargo.lock"
        if not (native / "Cargo.toml").is_file() or not lock.is_file():
            raise ValueError("Native Cargo.toml and Cargo.lock are required")
        reject_links(output)
        if output.exists():
            raise ValueError("Output must be a new directory")
        if (
            output == repository
            or repository in output.parents
            or output in repository.parents
        ):
            raise ValueError("Output must not overlap source")
        # Fail closed on build overrides instead of silently changing their meaning.
        overrides = [
            key
            for key in os.environ
            if key.startswith(("CARGO_", "RUST"))
            and key not in {"RUSTUP_HOME", "RUSTUP_TOOLCHAIN"}
        ]
        if overrides:
            raise ValueError(
                "Remove inherited Cargo/Rust overrides: " + ", ".join(sorted(overrides))
            )
        tools = {}
        for name in ("cargo", "rustc", "rustup", "link.exe", "rc.exe"):
            executable = shutil.which(name)
            if not executable:
                raise ValueError("Missing prerequisite: " + name)
            tools[name] = executable
        versions = {}
        for name, flags in (
            ("cargo", ["--version"]),
            ("rustc", ["-vV"]),
            ("rustup", ["target", "list", "--installed"]),
        ):
            check = subprocess.run(
                [tools[name], *flags], capture_output=True, text=True, check=True
            )
            versions[name] = check.stdout.strip()
        if args.target not in versions["rustup"].splitlines():
            raise ValueError("Requested Rust target is not installed: " + args.target)
        original_lock = digest(lock)
        revision = None
        source_dirty = None
        git = shutil.which("git")
        if git:
            commit = subprocess.run(
                [git, "-C", str(repository), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
            )
            if commit.returncode == 0:
                revision = commit.stdout.strip()
            status = subprocess.run(
                [git, "-C", str(repository), "status", "--porcelain"],
                capture_output=True,
                text=True,
            )
            if status.returncode == 0:
                source_dirty = bool(status.stdout.strip())
        output.mkdir(parents=True, exist_ok=False)
        report = {
            "result": "failed",
            "stage": "build",
            "target": args.target,
            "qualification": False,
            "source_revision": revision,
            "source_dirty": source_dirty,
            "tools": versions,
            "lock_sha256": original_lock,
            "artifacts": {},
        }
        env = os.environ.copy()
        env.update(
            {
                "CARGO_HOME": str(output / "cargo-home"),
                "CARGO_TARGET_DIR": str(output / "target"),
                "CARGO_PROFILE_DEV_DEBUG": "0",
                "CARGO_INCREMENTAL": "0",
            }
        )
        command = [
            tools["cargo"],
            "build",
            "--locked",
            "--manifest-path",
            str(native / "Cargo.toml"),
            "--target",
            args.target,
            "-p",
            "sign-extension-host",
            "-p",
            "sign-extension-service",
        ]
        with (output / "build.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(
                command, cwd=output, env=env, stdout=log, stderr=subprocess.STDOUT
            )
        report["build_exit_code"] = result.returncode
        report["lock_unchanged"] = digest(lock) == original_lock
        if result.returncode:
            return result.returncode
        report["stage"] = "artifacts"
        if not report["lock_unchanged"]:
            raise ValueError("Cargo.lock changed during build")
        for name in ("sign-extension-host", "sign-extension-service"):
            artifact = output / "target" / args.target / "debug" / (name + ".exe")
            if not artifact.is_file() or artifact.is_symlink():
                raise ValueError("Build did not produce required executable: " + name)
            report["artifacts"][name] = {
                "sha256": digest(artifact),
                "bytes": artifact.stat().st_size,
                "path": str(artifact),
            }
        report.update(result="passed", stage="complete")
        print("Build complete; executables were not run or installed. See report.json.")
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        if report is not None:
            report["error"] = str(error)
        return 1
    finally:
        if report is not None:
            (output / "report.json").write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )


if __name__ == "__main__":
    raise SystemExit(main())
