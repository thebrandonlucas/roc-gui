#!/usr/bin/env python3
"""Build, admit, cache, and install the unified native linker-input release."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import re

import kai_admission

from dependency_archive import write_archive
from dependency_artifacts import fetch, unpack_verified

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "link-inputs.lock.json"
CACHE = Path.home() / ".cache/roc-gui/link-inputs"
REPOSITORY = "lukewilliamboswell/roc-gui"
HEX256 = re.compile(r"[0-9a-f]{64}")
HEX160 = re.compile(r"[0-9a-f]{40}")
TARGETS = ("x64glibc", "arm64mac", "x64mingw")
COMPONENTS = {
    "x64glibc": (
        ("alsa", "x64glibc"), ("freetype", "x64glibc"), ("glibc", "x64glibc"),
        ("unwind", "x64glibc"), ("xkbcommon", "x64glibc"),
    ),
    "arm64mac": (("macos-interfaces", "macos-sysroot"),),
    # The Windows host derives its DLL import library from its own link, so
    # the target's external inputs are only the GNU runtime and its resource.
    "x64mingw": (("windows-gnu-runtime", "x64mingw"),),
}
SOURCE_PATHS = (
    "dependencies/nixpkgs-pin.nix", "scripts/nix_link_inputs.py", "scripts/dependency_artifacts.py",
    "test/dependencies", "scripts/test_unwind_rust.py", "scripts/test_linux_link_inputs.py",
    "scripts/check_linux_reproduction.py",
    "dependencies/alsa-interface.json", "dependencies/freetype.json", "dependencies/glibc",
    "dependencies/glibc.json", "dependencies/linux", "dependencies/macos-interfaces",
    "dependencies/unwind", "dependencies/unwind.json", "dependencies/windows-gnu-runtime",
    "dependencies/windows-gnu-runtime.json", "dependencies/xkbcommon", "dependencies/xkbcommon.json",
    "crates/host/windows/roc-gui.rc", "crates/host/windows/roc-gui.manifest.xml",
    "scripts/build_alsa_interface.py", "scripts/build_freetype.py", "scripts/build_glibc.py",
    "scripts/build_macos_interfaces.py", "scripts/build_macos_stubs.py", "scripts/build_unwind.py",
    "scripts/build_windows_gnu_runtime.py", "scripts/build_windows_resource.py",
    "scripts/windows_runtime_validation.py", "scripts/audit_windows_archive.py",
    "scripts/test_windows_gnu_runtime_artifact.py",
    "scripts/build_xkbcommon.py", "scripts/dependency_archive.py", "scripts/link_input_artifacts.py",
    ".github/workflows/link-inputs.yml",
)


# Shared files and the reviewed native package pin remain producer inputs.
# Exclude only paths whose ownership has moved wholly to the FreeType Build.
FREETYPE_ONLY = (
    "dependencies/freetype.json", "scripts/build_freetype.py",
    "test/dependencies/freetype.c", "dependencies/linux/zig-toolchain.cmake",
)


class StaleLinkInputs(ValueError):
    """A valid release lock describes different producer inputs."""


class UncommittedLinkInputs(ValueError):
    """Local producer edits cannot be represented by a release fingerprint."""


def development_requires_source_inputs(root=ROOT):
    """Require current reviewed authority; source builds require --source-inputs."""
    read_lock(root / "link-inputs.lock.json", root=root)
    return False


def source_fingerprint(root=ROOT):
    """Hash the committed tree records for every input that may affect the set."""
    paths = SOURCE_PATHS + tuple(":(exclude)" + path for path in FREETYPE_ONLY)
    changed = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *paths], cwd=root).returncode
    if changed not in (0, 1):
        raise ValueError("could not inspect linker-input producer changes")
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z", "--", *paths], cwd=root)
    if changed or untracked:
        raise UncommittedLinkInputs("linker-input releases require clean committed producer inputs")
    tree = subprocess.check_output(
        ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD", "--", *SOURCE_PATHS], cwd=root)
    excluded = {path.encode() for path in FREETYPE_ONLY}
    records = [record for record in tree.split(b"\0") if record and record.split(b"\t", 1)[1] not in excluded]
    tree = b"\0".join(records) + (b"\0" if records else b"")
    if not tree:
        raise ValueError("linker-input source inventory is empty")
    return hashlib.sha256(tree).hexdigest()


def _component_files(archive, name, target, stage):
    tree = stage / f"{name}-{target}"
    manifest = unpack_verified(archive, {"name": name, "target": target}, tree)
    return manifest, {path: (tree / path).read_bytes() for path in manifest["files"]}


def _unified_path(path, name, component_target, target):
    prefix = f"targets/{component_target}/"
    if path.startswith(prefix):
        if target == "arm64mac":
            macos_prefix = "targets/macos-sysroot/"
            if path.startswith(macos_prefix) and path.endswith(".tbd"):
                return "targets/arm64mac/macos-sysroot/" + path[len(macos_prefix):]
            return "sources/link-inputs/macos/" + path
        return f"targets/{target}/" + path[len(prefix):]
    if path.startswith(f"licenses/{name}/"):
        return "licenses/link-inputs/" + name + "/" + path[len(f"licenses/{name}/"):]
    if path.startswith(f"sources/{name}/"):
        return "sources/link-inputs/" + name + "/" + path[len(f"sources/{name}/"):]
    raise ValueError(f"component archive contains an unexpected path: {path}")


def compose(components, output, resource=None, *, root=ROOT, source=None):
    """Compose target archives from freshly tested component archives."""
    output.mkdir(parents=True, exist_ok=False)
    archives = {}
    fingerprint = source_fingerprint(root)
    archive = components / "freetype-x64glibc.tar"
    freetype = kai_admission.read_record(archive.with_suffix(".tar.kai.json"))
    kai_admission.verify_bytes(archive, freetype)
    kai_admission.check_current(freetype, root=root)
    component_builds = {"freetype": freetype}
    with tempfile.TemporaryDirectory(prefix="roc-gui-link-inputs-") as temporary:
        stage = Path(temporary)
        for target in TARGETS:
            files = {}
            identities = {}
            for name, component_target in COMPONENTS[target]:
                archive = components / f"{name}-{component_target}.tar"
                manifest, payload = _component_files(archive, name, component_target, stage)
                if name == "freetype" and manifest["schema_version"] != 6:
                    raise ValueError("new linker-input releases require a Kai FreeType candidate")
                identities[name] = {key: value for key, value in manifest.items() if key != "files"}
                for path, data in payload.items():
                    destination = _unified_path(path, name, component_target, target)
                    if destination in files:
                        raise ValueError(f"duplicate unified linker input: {destination}")
                    files[destination] = data
            if target == "x64mingw":
                if resource is None or not resource.is_file():
                    raise ValueError("Windows linker inputs require freshly generated roc-gui.res")
                files["targets/x64mingw/roc-gui.res"] = resource.read_bytes()
                for relative in ("crates/host/windows/roc-gui.rc", "crates/host/windows/roc-gui.manifest.xml"):
                    files["sources/link-inputs/" + relative] = (root / relative).read_bytes()
            archive = output / f"link-inputs-{target}.tar"
            write_archive(archive, {
                "schema_version": 1, "name": "link-inputs", "target": target,
                "input_fingerprint": fingerprint, "components": identities, "component_builds": component_builds,
            }, files)
            archives[target] = archive
    source = source or {
        "repository": os.environ.get("GITHUB_REPOSITORY", REPOSITORY),
        "sha": os.environ.get("GITHUB_SHA", subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()),
        "ref": os.environ.get("GITHUB_REF", "refs/heads/main"),
        "workflow": REPOSITORY + "/.github/workflows/link-inputs.yml",
        "input_fingerprint": fingerprint,
    }
    manifest = {
        "schema_version": 2, "kind": "roc-gui-link-inputs", "source": source,
        "component_builds": component_builds,
        "assets": {target: {"asset": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "size": path.stat().st_size} for target, path in archives.items()},
    }
    (output / "build-input-release.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
    return manifest


def read_lock(path=LOCK, *, root=ROOT):
    value = json.loads(path.read_text())
    version = value.get("schema_version")
    fields = {"schema_version", "kind", "repository", "release", "manifest", "source", "targets"}
    if version == 2:
        fields.add("component_builds")
    if (set(value) != fields
            or version != 2 or value["kind"] != "roc-gui-link-inputs"
            or value["repository"] != REPOSITORY or set(value["targets"]) != set(TARGETS)):
        raise ValueError("invalid unified linker-input lock")
    if (not re.fullmatch(r"link-inputs-sha256-[0-9a-f]{64}", value["release"])
            or value["manifest"].get("asset") != "build-input-release.json"
            or not HEX256.fullmatch(value["manifest"].get("sha256", ""))):
        raise ValueError("invalid unified linker-input release identity")
    source = value["source"]
    if (set(source) != {"repository", "sha", "ref", "workflow", "input_fingerprint"}
            or source["repository"] != REPOSITORY or not HEX160.fullmatch(source["sha"])
            or not source["ref"].startswith("refs/heads/")
            or source["workflow"] != REPOSITORY + "/.github/workflows/link-inputs.yml"
            or not HEX256.fullmatch(source["input_fingerprint"])):
        raise ValueError("invalid unified linker-input source identity")
    for target, record in value["targets"].items():
        if (set(record) != {"asset", "sha256", "size"}
                or record["asset"] != f"link-inputs-{target}.tar"
                or not HEX256.fullmatch(record["sha256"])
                or type(record["size"]) is not int or not 0 < record["size"] <= 2 * 1024 ** 3):
            raise ValueError("invalid unified linker-input target record")
    if version == 2:
        builds = value["component_builds"]
        if not isinstance(builds, dict) or set(builds) != {"freetype"}:
            raise ValueError("missing FreeType admission in linker-input lock")
        try:
            kai_admission.check_current(builds["freetype"], root=root)
        except kai_admission.StaleAdmission as error:
            raise StaleLinkInputs(str(error)) from error
    fingerprint = source_fingerprint(root)
    if source["input_fingerprint"] != fingerprint:
        raise StaleLinkInputs("linker-input lock is stale for this checkout")
    return value


def _entry(lock, target):
    record = lock["targets"][target]
    return {
        "name": "link-inputs", "target": target, "repository": lock["repository"],
        "release": lock["release"], "asset": record["asset"], "sha256": record["sha256"],
        "size": record["size"], "source_sha": lock["source"]["sha"],
        "source_ref": lock["source"]["ref"], "signer_workflow": lock["source"]["workflow"],
        "input_fingerprint": lock["source"]["input_fingerprint"],
    }


def install(target, destination, lock_path=LOCK, cache=CACHE):
    """Install one exact target archive, verifying cache hits and all members."""
    lock = read_lock(lock_path)
    entry = _entry(lock, target)
    archive = fetch(entry, cache)
    with tempfile.TemporaryDirectory(prefix="roc-gui-link-input-install-") as temporary:
        tree = Path(temporary) / "tree"
        manifest = unpack_verified(archive, entry, tree)
        if manifest.get("input_fingerprint") != lock["source"]["input_fingerprint"]:
            raise ValueError("linker-input archive has a different producer fingerprint")
        if lock["schema_version"] == 2 and manifest.get("component_builds") != lock["component_builds"]:
            raise ValueError("linker-input archive has different component admission evidence")
        source = tree / "targets" / target
        if not source.is_dir():
            raise ValueError("linker-input archive has no selected target payload")
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination, prefix=".link-inputs-") as staged_name:
            staged = Path(staged_name)
            for path in source.rglob("*"):
                if path.is_dir() and not path.is_symlink():
                    continue
                if not path.is_file() or path.is_symlink():
                    raise ValueError("linker-input payload must contain ordinary files")
                relative = path.relative_to(source)
                (staged / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, staged / relative)
            for path in staged.iterdir():
                target_path = destination / path.name
                if target_path.exists():
                    if target_path.is_dir():
                        shutil.rmtree(target_path)
                    else:
                        target_path.unlink()
                path.replace(target_path)
    return lock


def cache_key(target, lock_path=LOCK):
    lock = read_lock(lock_path)
    return lock["targets"][target]["sha256"]
