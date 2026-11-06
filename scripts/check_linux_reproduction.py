#!/usr/bin/env python3
"""Require each archive's corresponding sources to reproduce its derivation."""

import argparse
import json
import os

import kai_link_inputs
from pathlib import Path
import subprocess
import tempfile

from dependency_artifacts import unpack_verified
from link_input_artifacts import COMPONENTS

ROOT = Path(__file__).resolve().parents[1]


def check(components, target="x64glibc"):
    for name, target in COMPONENTS[target]:
        recipe = "dependencies/windows-gnu-runtime/default.nix" if target == "x64mingw" else "dependencies/linux/default.nix"
        attribute = "runtime" if target == "x64mingw" else name
        with tempfile.TemporaryDirectory(prefix="roc-gui-reproduction-") as temporary:
            root = Path(temporary) / "archive"
            manifest = unpack_verified(components / f"{name}-{target}.tar", {"name": name, "target": target}, root)
            if manifest["schema_version"] == 6:
                check_kai_freetype(root / "sources/freetype", manifest)
                continue
            command = ["nix", "eval", "--impure", "--raw", "--file"]
            expected = subprocess.check_output([
                *command, str(ROOT / recipe), attribute + ".drvPath"], text=True)
            actual = subprocess.check_output([
                *command, str(root / "sources" / name / recipe),
                attribute + ".drvPath"], text=True)
            if actual != expected:
                raise ValueError(name + ": corresponding sources do not reproduce the producer derivation")
            print(name + ": corresponding sources reproduce the identical derivation", flush=True)


def check_kai_freetype(source, manifest):
    """Replan from shipped producer files and verify exact selected package pins."""
    original = kai_link_inputs.plan()
    packages = kai_link_inputs.reproduction_packages((ROOT / "Kaifile.roc").read_text(), source)
    (source / "Kaifile.roc").write_text(kai_link_inputs.reproduction_config(packages))
    for name, mode in manifest["build"]["reproduction_modes"].items():
        (source / name).chmod(mode)
    # This is an explicit reproduction operation, not ordinary consumption.
    # Immutable URL/revision fetches are verified against shipped evidence.
    subprocess.run([os.environ.get("KAI", "kai"), "--yes", "update"], cwd=source, check=True)
    pins = kai_link_inputs.command(["lock"], root=source)
    expected = json.loads((source / "kai-input-evidence.json").read_text())["packages"][0]
    locked = [entry for entry in pins.get("inputs", []) if entry.get("name") == "nix" and entry.get("section") == "nix"]
    if (pins.get("schema_version") != 1 or len(locked) != 1
            or locked[0].get("revision") != expected["rev"]
            or locked[0].get("hash", {}).get("value") != expected["narHash"]):
        raise ValueError("FreeType reproduction package pin differs from selected evidence")
    reproduced = kai_link_inputs.plan(root=source)
    if ((reproduced["backend"], reproduced["derivation"])
            != (original["backend"], original["derivation"])):
        raise ValueError("FreeType corresponding sources do not reproduce the planned build identity")
    print("freetype: corresponding sources reproduce the identical planned build", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("components", type=Path)
    parser.add_argument("--target", choices=("x64glibc", "x64mingw"), default="x64glibc")
    args = parser.parse_args()
    check(args.components.resolve(), args.target)
