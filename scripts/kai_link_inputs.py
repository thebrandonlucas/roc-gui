"""Kai build adapter and selected FreeType reproduction evidence.

Build identity is supplied by Kai's build plan. The archive never embeds its
own identity; an external sidecar binds that identity to the measured archive
bytes.
"""

import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from dependency_artifacts import sha256, validate_kai_freetype_evidence

ROOT = Path(__file__).resolve().parents[1]
HEX256 = re.compile(r"[0-9a-f]{64}")
STORE_PATH = re.compile(r"/nix/store/[a-z0-9]{32}-[^/]+")
SELECTED_FILES = (
    "dependencies/FreeType.roc", "dependencies/freetype.json",
    "dependencies/nixpkgs-pin.nix",
    "dependencies/linux/zig-toolchain.cmake", "scripts/build_freetype.py",
    "scripts/kai_link_inputs.py", "scripts/dependency_archive.py",
    "scripts/dependency_artifacts.py", "test/dependencies/freetype.c",
)


def kai(arguments, *, root=ROOT):
    """Run kai in `root` and return what it prints on stdout."""
    return subprocess.check_output([os.environ.get("KAI", "kai"), *arguments], cwd=root, text=True)


def command(arguments, *, root=ROOT):
    result = json.loads(kai(arguments, root=root))
    if not isinstance(result, dict):
        raise ValueError("Kai did not return a result object")
    return result


def validate_binding(result):
    """Admit Kai's plan (schema 1) of the FreeType build.

    The snapshot is the store path Nix names by the SHA-256 of the selected
    files; the derivation and output path are the build's exact identity.
    """
    if (result.get("schema_version") != 1 or result.get("name") != "freetype"
            or result.get("system") != "x86_64-linux" or result.get("backend") != "nix"
            or not STORE_PATH.fullmatch(result.get("snapshot") or "")
            or not re.fullmatch(r"/nix/store/[a-z0-9]{32}-[^/]+\.drv", result.get("derivation") or "")
            or not STORE_PATH.fullmatch(result.get("output_path") or "")
            or list(result.get("files") or []) != list(SELECTED_FILES)):
        raise ValueError("invalid Kai FreeType build plan")
    return result


def plan(*, root=ROOT):
    return validate_binding(command(["build", "freetype", "--plan"], root=root))


def build(output, *, rebuild=False):
    destination = output / "freetype-x64glibc.tar"
    sidecar = destination.with_suffix(destination.suffix + ".kai.json")
    if destination.exists() or sidecar.exists():
        raise FileExistsError(destination)
    arguments = ["build", "freetype"]
    if rebuild:
        arguments.append("--rebuild")
    lines = kai(arguments).split()
    if len(lines) != 1 or not STORE_PATH.fullmatch(lines[0]):
        raise ValueError("Kai must print one FreeType output path")
    archive = Path(lines[0]) / destination.name
    if archive.is_symlink() or not archive.is_file():
        raise ValueError("Kai FreeType output is not an ordinary archive")
    # The plan of the same checkout names the output path the build produced,
    # which binds its snapshot and derivation to the bytes that ran.
    current = plan()
    if current["output_path"] != lines[0]:
        raise ValueError("Kai plan differs from the FreeType build it produced")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output, prefix=".kai-candidate-") as temporary:
        pending = Path(temporary) / destination.name
        shutil.copyfile(archive, pending)
        binding = {key: current[key] for key in ("backend", "derivation", "snapshot")}
        binding.update(schema_version=2, artifact={
            "name": destination.name, "sha256": sha256(pending), "size": pending.stat().st_size})
        record = Path(temporary) / sidecar.name
        record.write_text(json.dumps(binding, sort_keys=True, separators=(",", ":")) + "\n")
        os.link(pending, destination)
        try:
            os.link(record, sidecar)
        except BaseException:
            destination.unlink()
            raise
    return destination


def nixpkgs_pin(text):
    """The revision and NAR hash dependencies/nixpkgs-pin.nix fetches."""
    found = {key: re.search(key + r' = "([^"]+)";', text) for key in ("rev", "narHash")}
    if any(match is None for match in found.values()):
        raise ValueError("dependencies/nixpkgs-pin.nix must name one rev and narHash")
    return {key: match.group(1) for key, match in found.items()}


def collect_evidence():
    """The selected native reproduction payload, from inside the Kai build.

    Kai records the build's inputs in `$KAI_INPUTS/.kai-inputs.json` and links
    each tool in `$KAI_TOOLS`; the nixpkgs revision those tools come from is
    the one `kai run check` holds equal to dependencies/nixpkgs-pin.nix.
    """
    record = json.loads((Path(os.environ["KAI_INPUTS"]) / ".kai-inputs.json").read_text())
    files = []
    for entry in record.get("inputs", []):
        value = entry.get("hash", {}).get("value", "")
        if entry.get("kind") != "fetch" or not value.startswith("sha256-"):
            raise ValueError("unexpected Kai FreeType input")
        files.append({"name": entry["name"], "provider": "file",
                      "sha256": base64.b64decode(value[len("sha256-"):]).hex()})
    pin = nixpkgs_pin((ROOT / "dependencies/nixpkgs-pin.nix").read_text())
    tools_dir = Path(os.environ["KAI_TOOLS"])
    tools = [{"name": link.name, "path": os.readlink(link)} for link in sorted(tools_dir.iterdir())]
    evidence = {"format": 2, "packages": [{"name": "nix", "provider": "nix", **pin}],
                "files": files, "tools": tools}
    validate_kai_freetype_evidence(evidence)
    return evidence, (json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n").encode()


def input_evidence(path):
    """Validate shipped native reproduction evidence."""
    raw = path.read_bytes()
    evidence = json.loads(raw)
    validate_kai_freetype_evidence(evidence)
    return evidence, raw


def tool_root(name):
    name = {"bzip2": "bzip2.out", "brotli": "brotli.lib"}.get(name, name)
    return Path(os.environ["KAI_TOOLS"]) / ("nix#" + name)


def configure_environment(work):
    """Declare header/library discovery rather than depending on stdenv hooks."""
    environment = os.environ
    work.mkdir(parents=True, exist_ok=True)
    for key, name in (("HOME", "home"), ("ZIG_GLOBAL_CACHE_DIR", "zig-global"),
                      ("ZIG_LOCAL_CACHE_DIR", "zig-local")):
        directory = work / name
        directory.mkdir(exist_ok=True)
        environment[key] = str(directory)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    names = ("zlib", "bzip2", "libpng", "harfbuzz", "brotli")
    roots = [tool_root(name) for name in names]
    headers = [tool_root(name + ".dev") for name in names]
    environment["CMAKE_PREFIX_PATH"] = ":".join(map(str, headers + roots))
    environment["PKG_CONFIG_PATH"] = ":".join(str(root / "lib/pkgconfig") for root in headers + roots)
    environment["C_INCLUDE_PATH"] = ":".join(str(root / "include") for root in headers)
    environment["LIBRARY_PATH"] = ":".join(str(root / "lib") for root in roots)


def probe_command(executable):
    libraries = ("glibc", "zlib", "bzip2", "libpng", "harfbuzz", "brotli")
    return [str(tool_root("glibc") / "lib/ld-linux-x86-64.so.2"), "--library-path",
            ":".join(str(tool_root(name) / "lib") for name in libraries), str(executable)]


def portable_library(path):
    subprocess.run(["patchelf", "--remove-rpath", str(path)], check=True)
    dynamic = subprocess.check_output(["readelf", "--dynamic", str(path)], text=True)
    if (any("/" in item for item in re.findall(r"\(NEEDED\).*\[([^]]+)\]", dynamic))
            or "(RPATH)" in dynamic or "(RUNPATH)" in dynamic):
        raise ValueError("published library retains nonportable build dependencies")


def reproduction_config(packages):
    """A minimal Kaifile reuses the shipped producer declaration unchanged.

    `packages` is the body of this checkout's Kaifile.roc app header, with
    local paths made relative to the reproduction directory.
    """
    if not isinstance(packages, str) or "}" in packages:
        raise ValueError("invalid Kai reproduction header")
    return ('app [kaifile] {' + packages + '}\n\n'
            'import std.Std\n'
            'import dependencies/FreeType\n\n'
            'kaifile = Std.kaifile([Name("freetype-reproduction"), Systems(["x86_64-linux"])].concat(FreeType.settings))\n')


def reproduction_packages(kaifile, destination, root=ROOT):
    """The Kaifile's app header packages, for a Kaifile in `destination`.

    Roc takes a local package only by a relative path, so each one the
    checkout names is rewritten relative to `destination`; URLs stay.
    """
    header = re.search(r"app \[kaifile\] \{(.*?)\n\}", kaifile, re.S)
    if header is None:
        raise ValueError("missing Kaifile.roc app header")

    def relative(match):
        value = match.group(1)
        if value.startswith("https://"):
            return match.group(0)
        return '"' + os.path.relpath((root / value).resolve(), Path(destination).resolve()) + '"'
    return re.sub(r'"([^"\n]+)"', relative, header.group(1)) + "\n"
