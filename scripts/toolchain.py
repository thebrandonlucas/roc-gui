#!/usr/bin/env python3
"""Rewrite an application's platform dependency and report the compiler in use.

Compiler pins are policy of `scripts/check_all.roc`, run by `kai run check`;
nothing here repeats that check.
"""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
# Roc source as comments, string literals, names and single marks: a narrow
# reader for an app header. The compiler remains the grammar authority.
TOKEN = re.compile(r'#[^\n]*|"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z_0-9!]*|[^\s]', re.DOTALL)


def app_platform_span(source: str):
    """Locate the app header's platform literal, excluding comments and bodies."""
    tokens = iter(token for token in TOKEN.finditer(source) if not token.group().startswith("#"))
    first = next(tokens, None)
    if first is None or first.group() != "app":
        return None
    stack = []
    record = False
    found = []
    previous = None
    for token in tokens:
        value = token.group()
        if not stack and value == "{":
            record = True
        if record and len(stack) == 1 and previous == ":" and value == "platform":
            literal = next(tokens, None)
            if literal is None or not re.fullmatch(r'"[^"\\\n]+"', literal.group()):
                raise ValueError("platform dependency must be one unescaped literal")
            found.append((literal.start() + 1, literal.end() - 1))
            previous = literal.group()
            continue
        if value in {"[", "{", "("}:
            stack.append({"[": "]", "{": "}", "(": ")"}[value])
        elif value in {"]", "}", ")"}:
            if not stack or stack.pop() != value:
                raise ValueError("malformed app header")
            if record and not stack:
                if len(found) != 1:
                    raise ValueError("app header must contain exactly one platform")
                return found[0]
        previous = value
    raise ValueError("incomplete app header")


def replace_platform(source: str, reference: str) -> str:
    span = app_platform_span(source)
    if span is None:
        return source
    if any(character in reference for character in '\\"\n\r'):
        raise ValueError("platform reference cannot contain escapes or newlines")
    start, end = span
    return source[:start] + reference + source[end:]


def compiler_version(roc: str) -> str:
    """The compiler's own report of which build it is, as release notes record it."""
    return subprocess.check_output([roc, "version"], text=True).strip()


def verify_compiler(roc: str, recorded: str) -> None:
    """Require the compiler that recorded a release artifact."""
    actual = compiler_version(roc)
    if actual != recorded:
        raise ValueError(f"compiler differs from the one that bundled this release: {actual} != {recorded}")


def relocate_for_ci():
    """Move setup-roc's download out of the checkout without shell path comparisons.

    Windows Git Bash and native environment variables spell the same path
    differently. Native Path resolution keeps the containment check consistent.
    """
    executable = shutil.which("roc")
    if executable is None:
        raise ValueError("setup-roc did not install a compiler on PATH")
    directory = Path(executable).resolve().parent
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    if directory.parent != workspace:
        raise ValueError("downloaded compiler must be an immediate child of the checkout")
    destination = Path(os.environ["RUNNER_TEMP"]) / "roc-toolchain"
    if destination.exists() or destination.is_symlink():
        raise ValueError("compiler relocation destination already exists")
    shutil.move(str(directory), str(destination))
    with Path(os.environ["GITHUB_PATH"]).open("a", encoding="utf-8") as output:
        output.write(str(destination) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relocate-for-ci", action="store_true", required=True)
    parser.parse_args()
    relocate_for_ci()
