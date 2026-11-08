#!/usr/bin/env python3
"""Fetch locked dependency releases and verify reviewed content before extraction.

A cache is transport storage, never a trust authority: every use checks the
locked size and digest. Published attestations provide optional provenance
evidence, but consuming a reviewed lock does not depend on an online service.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile
from urllib.request import urlopen

MAX_ARCHIVE_BYTES = 2 * 1024 ** 3
MAX_FILES = 4096
HEX256 = re.compile(r"[0-9a-f]{64}")
HEX160 = re.compile(r"[0-9a-f]{40}")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read_lock(path):
    lock = json.loads(path.read_text())
    if set(lock) != {"schema_version", "artifacts"} or lock["schema_version"] != 1:
        raise ValueError("unsupported dependency lock")
    if not isinstance(lock["artifacts"], dict) or not lock["artifacts"]:
        raise ValueError("dependency lock must contain artifacts")
    for identity, entry in lock["artifacts"].items():
        fields = {"name", "target", "repository", "release", "asset", "sha256", "size",
                  "source_sha", "source_ref", "signer_workflow"}
        optional = {"input_fingerprint"}
        if not IDENTIFIER.fullmatch(identity) or not fields <= set(entry) <= fields | optional:
            raise ValueError("invalid dependency lock entry")
        for field in ("name", "target", "release", "asset"):
            if not isinstance(entry[field], str) or not IDENTIFIER.fullmatch(entry[field]):
                raise ValueError(f"invalid dependency {field}")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", entry["repository"]):
            raise ValueError("invalid dependency repository")
        if not HEX256.fullmatch(entry["sha256"]) or not HEX160.fullmatch(entry["source_sha"]):
            raise ValueError("invalid dependency digest")
        if "input_fingerprint" in entry and not HEX256.fullmatch(entry["input_fingerprint"]):
            raise ValueError("invalid dependency input fingerprint")
        if entry["repository"] == "lukewilliamboswell/roc-gui" and "input_fingerprint" not in entry:
            raise ValueError("roc-gui dependency locks require an input fingerprint")
        if type(entry["size"]) is not int or not 0 < entry["size"] <= MAX_ARCHIVE_BYTES:
            raise ValueError("invalid dependency archive size")
        if entry["source_ref"] != "refs/heads/main":
            raise ValueError("dependency provenance must identify the trusted main branch")
        prefix = entry["repository"] + "/.github/workflows/"
        if not entry["signer_workflow"].startswith(prefix) or not re.fullmatch(
                r"[A-Za-z0-9_-]+\.yml", entry["signer_workflow"][len(prefix):]):
            raise ValueError("invalid dependency signer workflow")
    return lock


def verify_archive(path, entry):
    if path.is_symlink() or path.stat().st_size != entry["size"] or sha256(path) != entry["sha256"]:
        raise ValueError("dependency archive differs from its locked digest or size")


def fetch(entry, cache):
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / (entry["sha256"] + ".tar")
    if not archive.exists():
        url = (f"https://github.com/{entry['repository']}/releases/download/"
               f"{entry['release']}/{entry['asset']}")
        with tempfile.NamedTemporaryFile(dir=cache, delete=False) as pending:
            path = Path(pending.name)
        try:
            with path.open("wb") as output, urlopen(url, timeout=60) as response:
                remaining = entry["size"]
                while remaining:
                    chunk = response.read(min(1024 ** 2, remaining))
                    if not chunk:
                        raise ValueError("truncated dependency download")
                    output.write(chunk)
                    remaining -= len(chunk)
                if response.read(1):
                    raise ValueError("dependency download exceeds locked size")
            # Close the writer before another process reads the file and before
            # publication or cleanup: Windows does not allow unlinking it open.
            verify_archive(path, entry)
            try:
                os.link(path, archive)
            except FileExistsError:
                pass
        finally:
            path.unlink(missing_ok=True)
    verify_archive(archive, entry)
    return archive


def unpack_verified(archive, entry, destination):
    """Validate a verified archive completely before creating its destination.

    Callers must verify_archive first. Only regular files with canonical paths
    are accepted; tar links, special files, duplicates, and undeclared files fail.
    """
    if destination.exists():
        raise ValueError("dependency extraction destination already exists")
    with tarfile.open(archive, "r:") as packed:
        members = {}
        total = 0
        for member in packed:
            name = member.name
            path = PurePosixPath(name)
            if (not member.isfile() or path.is_absolute() or ".." in path.parts
                    or str(path) != name or "\\" in name or name in members):
                raise ValueError("unsafe or duplicate dependency archive member")
            if member.size < 0:
                raise ValueError("negative dependency member size")
            members[name] = member
            total += member.size
            if len(members) > MAX_FILES or total > MAX_ARCHIVE_BYTES:
                raise ValueError("dependency archive exceeds extraction limits")
        metadata = members.get("dependency.json")
        if metadata is None or metadata.size > 1024 ** 2:
            raise ValueError("missing or oversized dependency manifest")
        manifest = json.load(packed.extractfile(metadata))
        if (manifest.get("name") != entry["name"]
                or manifest.get("target") != entry["target"]):
            raise ValueError("dependency manifest identity mismatch")
        if entry["name"] == "freetype" and manifest["schema_version"] != 6:
            raise ValueError("FreeType archives require Kai schema 6")
        native_linux = {"alsa", "glibc", "unwind", "xkbcommon"}
        allowed = ({4} if entry["name"] in native_linux else
                   {3, 4} if entry["name"] == "windows-gnu-runtime" else
                   {6} if entry["name"] == "freetype" else {1})
        if manifest["schema_version"] not in allowed:
            raise ValueError("dependency manifest is not the producer's current format")
        if manifest["schema_version"] == 4:
            pin_field = "nixpkgs_pin_sha256"
            build = manifest.get("build", {})
            if ((entry["name"], entry["target"]) not in {
                    (name, "x64glibc") for name in ("alsa", "glibc", "unwind", "xkbcommon")}
                    | {("windows-gnu-runtime", "x64mingw")}
                    or not re.fullmatch(r"/nix/store/[a-z0-9]{32}-[^/]+\.drv", build.get("builder_derivation", ""))
                    or not re.fullmatch(r"[0-9a-f]{40}", build.get("nixpkgs_revision", ""))
                    or not re.fullmatch(r"sha256-[A-Za-z0-9+/]{43}=", build.get("nixpkgs_nar_hash", ""))
                    or any(not HEX256.fullmatch(build.get(key, "")) for key in
                           (pin_field, "nix_recipe_sha256"))
                    or "builder_image" in build or "builder_recipe_sha256" in build):
                raise ValueError("invalid Nix dependency provenance")
        if manifest["schema_version"] == 6:
            build = manifest.get("build", {})
            if ((entry["name"], entry["target"]) != ("freetype", "x64glibc")
                    or build.get("builder_kind") != "kai-nix"
                    or not HEX256.fullmatch(build.get("input_evidence_sha256", ""))
                    or any(key in build for key in ("builder_derivation", "kai_lock_sha256", "nix_recipe_sha256"))):
                raise ValueError("invalid Kai dependency provenance")
        if manifest["schema_version"] == 3:
            build = manifest.get("build", {})
            source = manifest.get("source", {})
            pin = source.get("native_toolchain", {})
            if ((entry["name"], entry["target"]) != ("windows-gnu-runtime", "x64mingw")
                    or build.get("builder_kind") != "native-windows-zig"
                    or not HEX256.fullmatch(build.get("toolchain_sha256", ""))
                    or build["toolchain_sha256"] != pin.get("sha256")
                    or "builder_image" in build or "builder_derivation" in build):
                raise ValueError("invalid native Windows dependency provenance")
        files = manifest.get("files")
        if not isinstance(files, dict) or set(files) != set(members) - {"dependency.json"}:
            raise ValueError("dependency file inventory differs from archive")
        for name, record in files.items():
            if not (name.startswith(f"targets/{entry['target']}/")
                    or name.startswith(f"licenses/{entry['name']}/")
                    or name.startswith(f"sources/{entry['name']}/")):
                raise ValueError("dependency file is outside its target, license, or source directory")
            if (set(record) != {"size", "sha256"} or record["size"] != members[name].size
                    or not HEX256.fullmatch(record["sha256"])):
                raise ValueError("invalid dependency file record")
            with packed.extractfile(members[name]) as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != record["sha256"]:
                    raise ValueError("dependency file digest mismatch")
        if manifest["schema_version"] == 4:
            pinned = "dependencies/nixpkgs-pin.nix"
            for field, relative in ((pin_field, pinned),
                                    ("nix_recipe_sha256", "dependencies/windows-gnu-runtime/default.nix"
                                     if entry["name"] == "windows-gnu-runtime" else "dependencies/linux/default.nix")):
                source = files.get(f"sources/{entry['name']}/{relative}")
                if source is None or source["sha256"] != build[field]:
                    raise ValueError("Nix provenance differs from corresponding source")
        if manifest["schema_version"] == 6:
            evidence_path = "sources/freetype/kai-input-evidence.json"
            evidence_record = files.get(evidence_path)
            if evidence_record is None or evidence_record["sha256"] != build["input_evidence_sha256"]:
                raise ValueError("Kai evidence differs from corresponding source")
            evidence = json.load(packed.extractfile(members[evidence_path]))
            validate_kai_freetype_evidence(evidence)
            if evidence["files"][0]["sha256"] != manifest.get("source", {}).get("sha256"):
                raise ValueError("Kai source pin differs from archive source")
            original = files.get("sources/freetype/source.tar.xz")
            if original is None or original["sha256"] != evidence["files"][0]["sha256"]:
                raise ValueError("Kai upstream source differs from archive source")
            reproduction = build.get("reproduction_sha256", {})
            modes = build.get("reproduction_modes", {})
            expected_sources = freetype_kai_source_inventory()
            expected_reproduction = {path.removeprefix("sources/freetype/") for path in expected_sources}
            expected_reproduction -= {"source.tar.xz", "kai-input-evidence.json"}
            if set(reproduction) != expected_reproduction or set(modes) != expected_reproduction:
                raise ValueError("incomplete Kai reproduction inventory")
            for relative, expected in reproduction.items():
                record = files.get("sources/freetype/" + relative)
                if (record is None or not HEX256.fullmatch(expected) or record["sha256"] != expected
                        or type(modes[relative]) is not int or modes[relative] not in (0o644, 0o755)):
                    raise ValueError("Kai reproduction differs from corresponding source")
        if manifest["schema_version"] in (3, 4) and entry["name"] == "windows-gnu-runtime":
            build = manifest["build"]
            reproduction = build.get("reproduction_sha256", {})
            if not reproduction or not HEX256.fullmatch(build.get("recipe_sha256", "")):
                raise ValueError("missing Windows runtime reproduction provenance")
            for relative, expected in reproduction.items():
                record = files.get(f"sources/windows-gnu-runtime/{relative}")
                if record is None or record["sha256"] != expected:
                    raise ValueError("Windows runtime provenance differs from corresponding source")
            recipe = files.get("sources/windows-gnu-runtime/dependencies/windows-gnu-runtime.json")
            if recipe is None or recipe["sha256"] != build["recipe_sha256"]:
                raise ValueError("Windows runtime recipe differs from corresponding source")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".dependency-") as temporary:
            stage = Path(temporary) / "contents"
            stage.mkdir()
            for name, member in members.items():
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with packed.extractfile(member) as source, path.open("xb") as output:
                    shutil.copyfileobj(source, output)
            stage.rename(destination)
    return manifest


def materialize(lock_path, identities, cache, output):
    lock = read_lock(lock_path)
    if output.exists():
        raise ValueError("dependency output already exists")
    if not identities or len(set(identities)) != len(identities):
        raise ValueError("select distinct dependency artifacts")
    entries = {identity: lock["artifacts"][identity] for identity in identities}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".dependencies-") as temporary:
        stage = Path(temporary) / "contents"
        stage.mkdir()
        for identity, entry in entries.items():
            archive = fetch(entry, cache)
            unpack_verified(archive, entry, stage / identity)
        (stage / "dependencies.lock.json").write_text(json.dumps(
            {"schema_version": 1, "artifacts": entries}, indent=2) + "\n")
        stage.rename(output)


def nix_source_inventory(name):
    """Exact corresponding-source inventory for the Linux Nix-built archives."""
    common = {"dependencies/nixpkgs-pin.nix", "dependencies/linux/default.nix", "scripts/nix_link_inputs.py",
              "scripts/dependency_archive.py", "scripts/dependency_artifacts.py"}
    common.update({f"scripts/build_{'alsa_interface' if name == 'alsa' else name}.py",
                   f"dependencies/{'alsa-interface' if name == 'alsa' else name}.json"})
    if name == "alsa":
        common.update({"test/dependencies/alsa.c", "PROVENANCE.md"})
    elif name == "xkbcommon":
        common.update({"test/dependencies/xkbcommon.c", "source.tar.gz",
                       "dependencies/xkbcommon/zig.ini", "dependencies/xkbcommon/cc.sh"})
    elif name == "glibc":
        common.update({"source.tar.xz", "test/dependencies/glibc.c", "dependencies/glibc/COPYING.LIB"})
        common.update("dependencies/glibc/LICENSE-LINUX-" + suffix for suffix in
                      ("GPL-2.0", "GPL-1.0", "LGPL-2.0", "LGPL-2.1", "Linux-syscall-note", "MIT", "BSD-3-Clause"))
    elif name == "unwind":
        common.update({"source.tar.xz", "scripts/build_glibc.py", "scripts/test_unwind_rust.py",
                       "test/dependencies/unwind.cpp", "test/dependencies/unwind.rs", "test/dependencies/unwind-rust.c"})
    else:
        raise ValueError("unknown Nix component")
    return {f"sources/{name}/{path}" for path in common}


def validate_kai_freetype_evidence(evidence):
    """Accept only selected native evidence, never whole-lock or final-identity data."""
    if (not isinstance(evidence, dict) or evidence.get("format") != 2
            or set(evidence) != {"format", "packages", "files", "tools"}
            or not isinstance(evidence["tools"], list)):
        raise ValueError("invalid selected Kai reproduction evidence")
    packages, files = evidence["packages"], evidence["files"]
    if (not isinstance(packages, list) or len(packages) != 1 or not isinstance(packages[0], dict)
            or set(packages[0]) != {"name", "provider", "rev", "narHash"}
            or packages[0]["name"] != "nix" or packages[0]["provider"] != "nix"
            or not HEX160.fullmatch(packages[0]["rev"])
            or not re.fullmatch(r"sha256-[A-Za-z0-9+/]{43}=", packages[0]["narHash"])
            or not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict)
            or set(files[0]) != {"name", "provider", "sha256"}
            or files[0]["name"] != "freetype-source" or files[0]["provider"] != "file"
            or not HEX256.fullmatch(files[0]["sha256"])):
        raise ValueError("invalid selected Kai reproduction pins")
    for tool in evidence["tools"]:
        if (not isinstance(tool, dict) or set(tool) != {"name", "path"}
                or not isinstance(tool["name"], str) or not isinstance(tool["path"], str)
                or not re.fullmatch(r"/nix/store/[a-z0-9]{32}-[^/]+", tool["path"])):
            raise ValueError("invalid selected Kai tool root")


def freetype_kai_source_inventory():
    return {"sources/freetype/" + path for path in (
        "source.tar.xz", "kai-input-evidence.json", "dependencies/FreeType.roc",
        "dependencies/freetype.json", "dependencies/nixpkgs-pin.nix", "dependencies/linux/zig-toolchain.cmake",
        "scripts/build_freetype.py", "scripts/kai_link_inputs.py",
        "scripts/dependency_archive.py", "scripts/dependency_artifacts.py", "test/dependencies/freetype.c",
    )}


def component_inventory(expected, manifest):
    """Select the corresponding-source inventory for the current producer contract."""
    if manifest["schema_version"] == 1 or (manifest["schema_version"] == 3 and manifest["name"] == "windows-gnu-runtime"):
        return expected
    sources = (freetype_kai_source_inventory() if manifest["schema_version"] == 6
               else nix_source_inventory(manifest["name"]))
    return {path for path in expected if not path.startswith("sources/")} | sources


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--artifact", action="append", required=True)
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache/roc-gui/dependencies")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    materialize(args.lock, args.artifact, args.cache, args.output)
