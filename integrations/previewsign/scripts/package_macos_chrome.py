"""Explicit-path, directory-only macOS Chrome packaging; never executes the host."""

import argparse
import hashlib
import ipaddress
import io
import tarfile
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
HOST = "bin/sign-extension-host"
INVENTORY = ".previewsign-install.json"
WORKSHOP_CONFIG = "workshop-origins.json"
WORKSHOP_SCRIPTS = {"background.js", "content.js", "page.js", "popup.js"}
FACTS = "installation.json"
ASSETS = {
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
}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def load_installation_facts(path):
    try:
        facts = json.loads(read_file(path))
    except json.JSONDecodeError as error:
        raise ValueError("invalid installation facts JSON") from error
    if not isinstance(facts, dict) or set(facts) != {
        "chromeExtensionId",
        "nativeHosts",
    }:
        raise ValueError("invalid installation facts object")
    extension_id = facts["chromeExtensionId"]
    hosts = facts["nativeHosts"]
    if (
        not isinstance(extension_id, str)
        or not re.fullmatch(r"[a-p]{32}", extension_id)
        or not isinstance(hosts, dict)
        or set(hosts) != {"macos", "windows"}
        or any(
            not isinstance(value, str)
            or not re.fullmatch(r"[a-z0-9_]+(?:\.[a-z0-9_]+)+", value)
            for value in hosts.values()
        )
    ):
        raise ValueError("invalid installation identity")
    return facts


def installation_facts_path():
    bundled = Path(__file__).resolve().with_name(FACTS)
    return bundled if bundled.is_file() else ROOT / FACTS


def explicit_path(value):
    safe_path(Path(value) if Path(value).is_absolute() else Path.cwd() / value)
    path = Path(os.path.abspath(value))
    safe_path(path)
    return path


def safe_path(path):
    for component in (*reversed(path.parents), path):
        if component.is_symlink():
            raise ValueError(f"symlink refused: {component}")
        if component != path and component.exists() and not component.is_dir():
            raise ValueError(f"directory required: {component}")


def read_file(path):
    safe_path(path)
    if not path.is_file():
        raise ValueError(f"regular file required: {path}")
    return path.read_bytes()


def record(data, mode):
    return {"sha256": hashlib.sha256(data).hexdigest(), "mode": mode}


def write_new(path, data, mode=0o644):
    safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
    path.chmod(mode)


def valid_name(name):
    path = Path(name)
    if path.is_absolute() or path.as_posix() != name or ".." in path.parts:
        raise ValueError("invalid inventory path")
    if name in {
        HOST,
        "LICENSE",
        "LICENSE-SCOPE.md",
        "README.txt",
        "PROVENANCE.json",
        "install.py",
        FACTS,
    }:
        return
    if (
        len(path.parts) == 2
        and path.parts[0] == "extension"
        and path.name in ASSETS | {"manifest.json", WORKSHOP_CONFIG}
    ):
        return
    if len(path.parts) == 2 and path.parts[0] == "notices":
        return
    raise ValueError(f"unexpected package file: {name}")


def validate_records(records, require_facts=True):
    required = {
        HOST,
        "extension/manifest.json",
        "LICENSE",
        "LICENSE-SCOPE.md",
        "README.txt",
        "PROVENANCE.json",
    }
    if require_facts:
        required.add(FACTS)
    if not isinstance(records, dict) or not required <= records.keys():
        raise ValueError("incomplete inventory")
    for name, expected in records.items():
        valid_name(name)
        if not isinstance(expected, dict) or set(expected) != {"sha256", "mode"}:
            raise ValueError("invalid file record")
        digest = expected["sha256"]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("invalid checksum")
        if expected["mode"] != (0o755 if name == HOST else 0o644):
            raise ValueError("invalid file mode")


def checked_files(directory, records, allow_missing=False):
    files = {}
    for name, expected in records.items():
        path = directory / name
        safe_path(path)
        if allow_missing and not path.exists():
            continue
        data = read_file(path)
        if record(data, stat.S_IMODE(path.stat().st_mode)) != expected:
            raise ValueError(f"modified owned artifact: {path}")
        files[name] = data
    return files


def native_manifest(destination, facts_path=None):
    facts = load_installation_facts(facts_path or installation_facts_path())
    return encoded(
        {
            "name": facts["nativeHosts"]["macos"],
            "description": "previewSign FIDO Bridge Native Host",
            "path": str(destination / HOST),
            "type": "stdio",
            "allowed_origins": [f"chrome-extension://{facts['chromeExtensionId']}/"],
        }
    )


def workshop_origin(value):
    match = re.fullmatch(
        r"(https?)://(\[[0-9a-f:.]+\]|[a-z0-9.-]+)(?::([0-9]+))?", value, re.IGNORECASE
    )
    if not match:
        raise ValueError(
            "workshop origin must be an HTTP(S) origin without credentials, path, query or fragment"
        )
    scheme, host, port = match.groups()
    scheme, host = scheme.lower(), host.lower()
    if host.startswith("["):
        host = f"[{ipaddress.IPv6Address(host[1:-1]).compressed}]"
    else:
        if len(host) > 253 or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in host.split(".")
        ):
            raise ValueError("invalid workshop origin hostname")
        if re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", host.rsplit(".", 1)[-1]):
            host = str(ipaddress.IPv4Address(host))
    if port is not None:
        port = int(port)
        if port > 65535:
            raise ValueError("invalid workshop origin port")
        if port == (443 if scheme == "https" else 80):
            port = None
    return f"{scheme}://{host}" + (f":{port}" if port is not None else "")


def assemble(arguments):
    facts_path = ROOT / FACTS
    load_installation_facts(facts_path)
    facts_data = read_file(facts_path)
    origins = list(
        dict.fromkeys(workshop_origin(value) for value in arguments.workshop_origin)
    )
    if not origins:
        raise ValueError("at least one workshop origin is required")
    patterns = []
    for origin in origins:
        parsed = urlsplit(origin)
        hostname = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        pattern = f"{parsed.scheme}://{hostname}/*"
        if pattern not in patterns:
            patterns.append(pattern)
    extension = explicit_path(arguments.extension_dir)
    host = explicit_path(arguments.host_binary)
    output = explicit_path(arguments.output)
    for source in (extension, host):
        if output == source or output in source.parents or source in output.parents:
            raise ValueError(
                "assembly output and extension/host inputs must not overlap"
            )
    if output.exists():
        raise ValueError(f"output collision: {output}")
    host_data = read_file(host)
    if not host.stat().st_mode & 0o111:
        raise ValueError("host must have an executable mode; it will not be executed")
    manifest = json.loads(read_file(extension / "manifest.json"))
    if (
        manifest.get("manifest_version") != 3
        or manifest.get("background", {}).get("service_worker") != "background.js"
    ):
        raise ValueError("Chrome MV3 background.js service worker required")
    manifest["background"] = {"service_worker": "background.js"}
    manifest.pop("browser_specific_settings", None)
    for entry in manifest.get("content_scripts", []):
        entry["matches"] = patterns
        entry["all_frames"] = False
        entry.pop("match_about_blank", None)
        entry.pop("match_origin_as_fallback", None)
    for entry in manifest.get("web_accessible_resources", []):
        entry["matches"] = patterns
        entry.pop("extension_ids", None)
    files = {
        "extension/manifest.json": encoded(manifest),
        HOST: host_data,
        f"extension/{WORKSHOP_CONFIG}": encoded({"origins": origins}),
        FACTS: facts_data,
    }
    for name in sorted(ASSETS):
        data = read_file(extension / name)
        if name in WORKSHOP_SCRIPTS:
            data = (
                b"(function () {\nconst WORKSHOP_MODE = true;\n" + data + b"\n})();\n"
            )
        files[f"extension/{name}"] = data
    for name in ("LICENSE", "LICENSE-SCOPE.md"):
        files[name] = read_file(ROOT / name)
    for name in ("malloc_buf-MIT.txt", "malloc_buf-0.0.6.provenance.json"):
        files[f"notices/{name}"] = read_file(ROOT / "notices" / name)
    for notice in arguments.notice:
        path = explicit_path(notice)
        name = f"notices/{path.name}"
        valid_name(name)
        if name in files:
            raise ValueError(f"notice collision: {name}")
        files[name] = read_file(path)
    files["PROVENANCE.json"] = encoded(
        {
            "host": {
                "input": host.name,
                "sha256": hashlib.sha256(host_data).hexdigest(),
                "synthetic": arguments.synthetic,
                "qualification": "not performed",
            },
            "sbx": {"provenance": "not supplied", "qualification": "not performed"},
            "notices": (
                "Bundled malloc_buf 0.0.6 later-upstream MIT supplementation: "
                "see notices/malloc_buf-0.0.6.provenance.json. Additional notices "
                "are explicitly declared; completeness and legal approval not claimed."
            ),
        }
    )
    files["install.py"] = read_file(Path(__file__).resolve())
    files["README.txt"] = (
        "macOS Chrome development assembly directory only; not a qualified release or zip.\n"
        + (
            "SYNTHETIC fixture host; no real-binary qualification.\n"
            if arguments.synthetic
            else "Supplied host is unqualified.\n"
        )
        + "No complete dependency-notice claim. Original LICENSE and scope are preserved.\n"
        "Manual setup is the default and needs no Python. Follow the matching workshop page or PARTICIPANT-ARCHIVE guide.\n"
        "The native helper runs directly. Python 3 is required only for this optional installer.\n"
        "Optional: use python3 -I -S install.py install --package PACKAGE --destination STABLE_DIR "
        "--chrome-user-data-dir TEMP_CHROME_DIR.\n"
        "Use python3 -I -S install.py remove --destination STABLE_DIR "
        "--chrome-user-data-dir TEMP_CHROME_DIR.\n"
        "All paths must be supplied. Use only a temporary Chrome user-data directory.\n"
        "Workshop assembly requires repeated --workshop-origin HTTP(S)://HOST[:PORT] inputs.\n"
        "Only the configured exact origins in top-level frames can reach native messaging.\n"
        "Origin-scoped browser integration remains unreleased/unqualified.\n"
        "No host/browser execution or device validation performed. Linux fixture tests only.\n"
        "Signing, notarization, real macOS registration, real-binary qualification, complete "
        "notices and Windows remain release gates; Safari sync is excluded.\n"
    ).encode()
    records = {
        name: record(data, 0o755 if name == HOST else 0o644)
        for name, data in files.items()
    }
    output.mkdir(parents=True)
    for name, data in files.items():
        write_new(output / name, data, records[name]["mode"])
    write_new(output / "checksums.json", encoded(records))


def installation_paths(arguments):
    destination = explicit_path(arguments.destination)
    profile = explicit_path(arguments.chrome_user_data_dir)
    if (
        destination == profile
        or destination in profile.parents
        or profile in destination.parents
    ):
        raise ValueError("destination and Chrome directory must not overlap")
    owned_facts = destination / FACTS
    facts = load_installation_facts(
        owned_facts if owned_facts.is_file() else installation_facts_path()
    )
    manifest = (
        profile / "NativeMessagingHosts" / f"{facts['nativeHosts']['macos']}.json"
    )
    safe_path(manifest)
    return destination, profile, manifest


def load_installation(destination, profile, manifest):
    inventory_path = destination / INVENTORY
    inventory_data = read_file(inventory_path)
    inventory = json.loads(inventory_data)
    if (
        inventory_data != encoded(inventory)
        or stat.S_IMODE(inventory_path.stat().st_mode) != 0o644
    ):
        raise ValueError("modified installation inventory")
    if inventory.get("destination") != str(destination) or inventory.get(
        "chrome_user_data_dir"
    ) != str(profile):
        raise ValueError("installation ownership/path mismatch")
    records = inventory["files"]
    checksum_record = records.get("checksums.json")
    package_records = {
        name: expected for name, expected in records.items() if name != "checksums.json"
    }
    # Historical owned installs predate bundled installation facts. Their exact
    # inventories and checksums remain sufficient for conservative removal.
    validate_records(package_records, require_facts=False)
    if checksum_record != record(encoded(package_records), 0o644):
        raise ValueError("invalid installed checksums")
    checked_files(destination, records, allow_missing=True)
    owned_facts = destination / FACTS if FACTS in package_records else None
    safe_path(manifest)
    if manifest.exists() and (
        read_file(manifest) != native_manifest(destination, owned_facts)
        or stat.S_IMODE(manifest.stat().st_mode) != 0o644
    ):
        raise ValueError(f"modified owned artifact: {manifest}")
    return inventory


def install(arguments):
    package = explicit_path(arguments.package)
    destination, profile, manifest = installation_paths(arguments)
    if (
        package == destination
        or package in destination.parents
        or destination in package.parents
    ):
        raise ValueError("package and destination must not overlap")
    if package == profile or package in profile.parents or profile in package.parents:
        raise ValueError("package and Chrome directory must not overlap")
    checksum_data = read_file(package / "checksums.json")
    records = json.loads(checksum_data)
    validate_records(records)
    if checksum_data != encoded(records):
        raise ValueError("noncanonical package checksums")
    files = checked_files(package, records)
    files["checksums.json"] = checksum_data
    records["checksums.json"] = record(checksum_data, 0o644)
    inventory = {
        "destination": str(destination),
        "chrome_user_data_dir": str(profile),
        "files": records,
    }
    if destination.exists():
        if load_installation(destination, profile, manifest) != inventory:
            raise ValueError("changed installation refused")
    elif manifest.exists():
        raise ValueError(f"unmanaged manifest collision: {manifest}")
    for directory in (destination.parent, profile, manifest.parent):
        if directory.exists() and not directory.is_dir():
            raise ValueError(f"directory required: {directory}")
    if not destination.exists():
        destination.mkdir(parents=True)
        write_new(destination / INVENTORY, encoded(inventory))
    for name, data in files.items():
        if not (destination / name).exists():
            write_new(destination / name, data, records[name]["mode"])
    if not manifest.exists():
        write_new(manifest, native_manifest(destination, destination / FACTS))


def remove(arguments):
    destination, profile, manifest = installation_paths(arguments)
    if not destination.exists() or not (destination / INVENTORY).exists():
        safe_path(destination / INVENTORY)
        if manifest.exists():
            raise ValueError("unowned manifest preserved")
        return
    inventory = load_installation(destination, profile, manifest)
    manifest.unlink(missing_ok=True)
    directories = set()
    for name in inventory["files"]:
        path = destination / name
        path.unlink(missing_ok=True)
        directories.update(
            parent
            for parent in path.parents
            if parent != destination and destination in parent.parents
        )
    (destination / INVENTORY).unlink()
    for directory in sorted(
        directories, key=lambda path: len(path.parts), reverse=True
    ):
        if directory.exists() and not any(directory.iterdir()):
            directory.rmdir()
    if not any(destination.iterdir()):
        destination.rmdir()


def archive(arguments):
    package = explicit_path(arguments.package)
    output = explicit_path(arguments.output)
    if output.exists() or package == output or package in output.parents:
        raise ValueError("archive output must be a new file outside the package")
    manifest_path = output.parent / "manifest.json"
    safe_path(manifest_path)
    if manifest_path.exists():
        raise ValueError("archive manifest collision")
    records = json.loads(read_file(package / "checksums.json"))
    validate_records(records)
    if "install.py" not in records:
        raise ValueError("participant installer missing; assemble a current package")
    files = checked_files(package, records)
    files["checksums.json"] = read_file(package / "checksums.json")
    origins = json.loads(files[f"extension/{WORKSHOP_CONFIG}"])["origins"]
    if (
        not isinstance(origins, list)
        or not origins
        or any(workshop_origin(origin) != origin for origin in origins)
    ):
        raise ValueError("invalid packaged workshop origins")
    revision = getattr(arguments, "source_revision", None)
    if revision is not None and not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("exact 40-character source revision required")
    if revision is None and any(
        urlsplit(origin).scheme == "https" for origin in origins
    ):
        raise ValueError("source revision required for hosted HTTPS origins")
    # Validate every input before opening the destination. No extra files ship.
    with output.open("xb") as stream:
        with tarfile.open(fileobj=stream, mode="w:gz") as bundle:
            for name, data in sorted(files.items()):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = records[name]["mode"] if name in records else 0o644
                info.mtime = 0
                bundle.addfile(info, io.BytesIO(data))

    write_new(
        manifest_path,
        encoded(
            {
                "schemaVersion": 1,
                "platform": "macos-arm64",
                "distribution": "local-evaluation",
                "qualified": False,
                "artifact": output.name,
                "format": "tar.gz",
                "byteSize": output.stat().st_size,
                **({"sourceRevision": revision} if revision is not None else {}),
                "sha256": hashlib.sha256(read_file(output)).hexdigest(),
                "workshopOrigins": origins,
            }
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    assembly = commands.add_parser("assemble")
    for name in ("extension-dir", "host-binary", "output"):
        assembly.add_argument(f"--{name}", required=True)
    assembly.add_argument("--notice", action="append", default=[])
    assembly.add_argument("--synthetic", action="store_true")
    assembly.add_argument("--workshop-origin", action="append", required=True)
    assembly.set_defaults(action=assemble)
    for name, action in (("install", install), ("remove", remove)):
        command = commands.add_parser(name)
        command.add_argument("--destination", required=True)
        command.add_argument("--chrome-user-data-dir", required=True)
        if name == "install":
            command.add_argument("--package", required=True)
        command.set_defaults(action=action)
    package_archive = commands.add_parser("archive")
    package_archive.add_argument("--package", required=True)
    package_archive.add_argument("--output", required=True)
    package_archive.add_argument("--source-revision")
    package_archive.set_defaults(action=archive)
    arguments = parser.parse_args()
    try:
        arguments.action(arguments)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
