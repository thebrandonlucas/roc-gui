#!/usr/bin/env python3
"""Build Roc GUI examples and run each .scm as one SQLite-backed app case."""

from __future__ import annotations

import argparse
import concurrent.futures
import atexit
from contextlib import closing, contextmanager
import fnmatch
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUPPORTED_SCHEMA = 25


@dataclass(frozen=True)
class Case:
    spec: Path
    app: Path
    executable: Path
    capture: Path


# Windows refuses a command line beyond 32767 characters, and POSIX bounds it
# by ARG_MAX. Describing the whole suite in one call once fit and silently grew
# past the Windows limit from a deeper checkout, so batches are budgeted by
# length rather than a count that would drift with path depth.
ARGV_BUDGET = 24_000


def argv_batches(arguments: list[str], reserved: int, budget: int = ARGV_BUDGET) -> list[list[str]]:
    """Group arguments into command lines the operating system will accept."""
    batches: list[list[str]] = []
    current: list[str] = []
    length = reserved
    for argument in arguments:
        extra = len(argument) + 1
        if current and length + extra > budget:
            batches.append(current)
            current = []
            length = reserved
        if not current and reserved + extra > budget:
            raise RuntimeError("a single specification path exceeds the command-line budget")
        current.append(argument)
        length += extra
    if current:
        batches.append(current)
    return batches


def describe(cases: list[Case]) -> dict[Path, dict]:
    """Ask the host what each specification needs.

    The host owns the `.scm` vocabulary, so it is the only parser: it reports
    the runner a case needs and the very capability flags its declared grants
    become. Duplicating that vocabulary here would be a second source of truth
    that could drift.

    Each record is keyed by its own path, so answering in several batches is
    the same answer as one call.
    """
    executable = next((case.executable for case in cases if case.executable.is_file()), None)
    if executable is None:
        raise RuntimeError("no built executable available to describe specifications")
    flag = "--host-describe-specs"
    described: dict[Path, dict] = {}
    batches = argv_batches([str(case.spec) for case in cases], len(str(executable)) + len(flag) + 2)
    for batch in batches:
        completed = subprocess.run(
            [str(executable), flag, *batch],
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if completed.returncode != 0:
            diagnostic = completed.stderr.decode(errors="replace").strip()
            raise RuntimeError(f"specification description failed: {diagnostic}")
        for line in completed.stdout.decode(errors="replace").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            described[Path(record["path"])] = record
    missing = [case.spec for case in cases if case.spec not in described]
    if missing:
        raise RuntimeError(f"host did not describe {len(missing)} specification(s)")
    return described


@contextmanager
def fixture_services(cases: list[Case], described: dict[Path, dict], output: Path):
    """Run the loopback services the selected cases declare."""
    output.mkdir(parents=True, exist_ok=True)
    processes: list[subprocess.Popen[bytes]] = []
    servers = set()
    for case in cases:
        for server in described[case.spec]["servers"]:
            servers.add((server["script"], int(server["port"])))
    try:
        for script, port in sorted(servers):
            ready_file = output / f"fixture-ready-{port}"
            environment = os.environ.copy()
            environment["ROC_GUI_FIXTURE_READY_FILE"] = str(ready_file)
            process = subprocess.Popen(
                [sys.executable, script], cwd=ROOT,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                env=environment,
            )
            processes.append(process)
            atexit.register(lambda process=process: process.poll() is None and process.terminate())
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if ready_file.is_file():
                    break
                if process.poll() is not None:
                    diagnostic = process.stderr.read().decode(errors="replace").strip()
                    suffix = f": {diagnostic}" if diagnostic else ""
                    raise RuntimeError(f"local fixture failed to start{suffix}")
                time.sleep(0.02)
            else:
                process.terminate()
                process.wait(timeout=5)
                diagnostic = process.stderr.read().decode(errors="replace").strip()
                suffix = f": {diagnostic}" if diagnostic else ""
                raise RuntimeError(f"local fixture did not report readiness{suffix}")
        yield
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


def discover(patterns: list[str], output: Path, excludes: list[str] | None = None, roc_opt: str = "dev") -> list[Case]:
    specs = sorted(
        [*ROOT.glob("examples/*/specs/*.scm"), *ROOT.glob("benchmarks/*/specs/*.scm")]
    )
    if patterns:
        specs = [
            spec
            for spec in specs
            if any(fnmatch.fnmatch(spec.relative_to(ROOT).as_posix(), pattern) for pattern in patterns)
        ]
    if excludes:
        specs = [
            spec
            for spec in specs
            if not any(fnmatch.fnmatch(spec.relative_to(ROOT).as_posix(), pattern) for pattern in excludes)
        ]
    for spec in [spec for spec in specs if spec.relative_to(ROOT).as_posix() in INTERMITTENT]:
        print(f"SKIP {spec.relative_to(ROOT).as_posix()}: {INTERMITTENT[spec.relative_to(ROOT).as_posix()]}", flush=True)
        specs.remove(spec)
    blocked = [spec for spec in specs if (spec.parent.parent.relative_to(ROOT).as_posix(), roc_opt) in COMPILER_BLOCKED]
    for directory in sorted({spec.parent.parent.relative_to(ROOT).as_posix() for spec in blocked}):
        count = sum(spec.parent.parent.relative_to(ROOT).as_posix() == directory for spec in blocked)
        print(f"SKIP {directory} --opt={roc_opt}: {count} specs ({COMPILER_BLOCKED[(directory, roc_opt)]})", flush=True)
    specs = [spec for spec in specs if spec not in blocked]
    cases = []
    for spec in specs:
        app = spec.parent.parent / "main.roc"
        if not app.is_file():
            raise SystemExit(f"spec has no adjacent example main.roc: {spec}")
        slug = app.parent.name
        cases.append(
            Case(
                spec=spec,
                app=app,
                executable=output / "bin" / slug,
                capture=output / spec.relative_to(ROOT).with_suffix(".rgstats"),
            )
        )
    return cases


# Use one explicit application backend across examples and benchmarks. The
# selected compiler's LLVM callback/state corruption is tracked in the backlog;
# --roc-opt allows intentional compiler diagnostics without an automatic retry
# or fallback. The Rust host's build profile is independent of this option.
SKIP_HOST_BUILD = "ROC_GUI_SKIP_HOST_BUILD"
SELECTED_APPS = "ROC_GUI_SELECTED_APPS"
# Applications the current nightly cannot build, by build mode. Their
# specifications are skipped and named on every run; each is tracked in
# wip/issues-backlog.md under "Compiler and toolchain defects" and removed when
# its fix lands.
COMPILER_BLOCKED = {
    # TODO(release blocker): nightly-2026-10-23-18478ff segfaults in
    # post-check lambda_solve building Observatory with --no-cache
    # --opt=speed after 9 s; nightly-2026-10-21-5349569 was killed by signal
    # 9 after 38 s at 24.4 GiB peak RSS. See the backlog for earlier nightly
    # results. Reduce, report upstream, and remove this entry once a nightly
    # builds it and its specifications pass.
    ("examples/observatory", "speed"): "the speed backend does not finish building it; see the backlog",
}
# Specifications that fail intermittently, skipped everywhere they would run and
# named on every run. Each is tracked in wip/issues-backlog.md and removed when
# its cause is fixed.
INTERMITTENT = {
    # TODO(release blocker): Observatory's folder rewatch sometimes counts one
    # change, [2, 1, 0, 0, 1] where [2, 0, 0, 0, _] is expected, on the hosted
    # macOS runner (run 39515606523) and the Linux build job (run
    # 39522990540); it never failed locally. The suspected cause is SQLite
    # creating and removing -wal/-shm files beside the captures Observatory
    # opens. Find the cause, fix it, and remove this entry.
    "examples/observatory/specs/folder-rewatch.scm": "fails intermittently in CI; see the backlog",
}


def build(cases: list[Case], roc: str, skip_host_build: bool, roc_opt: str = "dev") -> None:
    from toolchain import compiler_version
    print(f"Roc compiler: {compiler_version(roc)}", flush=True)
    print(f"Roc application build mode: {roc_opt}", flush=True)
    if not skip_host_build:
        subprocess.run([sys.executable, str(ROOT / "build.py")], cwd=ROOT, check=True)
    # A generator that runs specifications itself builds with this compiler,
    # against the host just built, so its nested runs never build it again.
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/bootstrap.py")],
        cwd=ROOT,
        check=True,
        env={**os.environ, "ROC": roc, SKIP_HOST_BUILD: "1",
             SELECTED_APPS: os.pathsep.join(sorted({case.app.parent.relative_to(ROOT).as_posix() for case in cases}))},
    )
    by_app = {case.app: case.executable for case in cases}
    for app, executable in sorted(by_app.items()):
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.unlink(missing_ok=True)
        # Every application is compiled from source, never from Roc's shared
        # build cache: a result must describe the program the sources define,
        # not whatever an earlier build left cached (see the backlog).
        for attempt in range(2):
            result = subprocess.run(
                [roc, "build", "--no-cache", f"--opt={roc_opt}", f"--output={executable}", str(app)],
                cwd=ROOT,
                capture_output=True,
                # The compiler writes UTF-8 whatever the console's code page; a
                # diagnostic that quotes source must not end the run on Windows.
                encoding="utf-8",
                errors="replace",
            )
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            # TODO(release blocker): the compiler intermittently crashes on
            # Windows while type-checking platform/Session.roc (see the
            # backlog). Retry that one crash once, loudly, until a nightly
            # fixes it; remove this before 0.1.0-rc1 is cut.
            if not (attempt == 0 and sys.platform == "win32"
                    and "Access violation in the Roc compiler" in result.stdout + result.stderr):
                break
            print(f"RETRY {app.relative_to(ROOT).as_posix()}: the compiler crashed on Windows; see the backlog",
                  flush=True)
        # Roc exits with code 2 for warnings even if it writes an executable.
        # A produced executable does not exempt its source from the warning gate.
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, result.args)


def validate_capture(path: Path) -> None:
    uri = path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as database:
        database.execute("PRAGMA query_only=ON")
        database.execute("PRAGMA trusted_schema=OFF")
        metadata = dict(database.execute("SELECT key,value FROM metadata"))
        if int(metadata.get("schema_version", "-1")) != SUPPORTED_SCHEMA:
            raise RuntimeError("unsupported or missing schema version")
        if metadata.get("clean_shutdown") != "1" or metadata.get("final_state") != "complete":
            raise RuntimeError("capture did not finalize cleanly")
        if metadata.get("application_outcome") != "success":
            raise RuntimeError("application outcome is not success")
        bad_status = list(
            database.execute(
                "SELECT name,status,reason FROM measurement_status "
                "WHERE status='unfinalized' OR (status='partial' AND name<>'timing_environment') ORDER BY name"
            )
        )
        if bad_status:
            raise RuntimeError(f"incomplete evidence: {bad_status!r}")
        failed_runs = database.execute("SELECT count(*) FROM runs WHERE outcome<>'pass'").fetchone()[0]
        if failed_runs:
            raise RuntimeError(f"capture contains {failed_runs} failed run(s)")
        foreign_keys = list(database.execute("PRAGMA foreign_key_check"))
        if foreign_keys:
            raise RuntimeError(f"capture contains foreign-key violations: {foreign_keys!r}")


def report_window_failure(artifacts: Path) -> None:
    """Print the failing step and any screenshots, so the next look is one read away."""
    try:
        report = json.loads((artifacts / "report.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(f"    no report written to {artifacts / 'report.json'}", file=sys.stderr)
        return
    for step in report.get("steps", []):
        if step.get("status") in {"fail", "unavailable"}:
            print(f"    {step['status']}: {step.get('message', step.get('kind'))}", file=sys.stderr)
    for shot in sorted(artifacts.glob("*.png")):
        print(f"    screenshot: {shot}", file=sys.stderr)


def window_artifacts(case: Case) -> Path:
    """Where a window case writes its report and screenshots."""
    return case.capture.with_suffix("")


def case_identity(case: Case) -> str:
    """Repository-relative case identity safe to print and retain in CI."""
    return case.spec.relative_to(ROOT).as_posix()


def failure_record(case: Case) -> Path:
    """Privacy-safe machine-readable failure evidence beside a case capture."""
    return case.capture.with_suffix(".failure.json")


def sanitize_debugger_output(output: str) -> str:
    """Remove machine and user identity from a debugger's textual backtrace."""
    sanitized = output.replace(str(ROOT), "/workspace")
    home = str(Path.home())
    if home:
        sanitized = sanitized.replace(home, "/home/user")
    temporary = tempfile.gettempdir()
    if temporary:
        sanitized = sanitized.replace(temporary, "/tmp")
    # Windows debugger output can use either separator and is produced on a
    # different machine from this Python source.
    sanitized = re.sub(r"(?i)[A-Z]:[\\/]Users[\\/][^\\/\s]+", "C:/Users/user", sanitized)
    sanitized = re.sub(
        r"(?i)[A-Z]:[\\/]a[\\/](?:_temp|[^\\/\s]+[\\/][^\\/\s]+)",
        "C:/runner/workspace",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)[A-Z]:[\\/]actions-runner[\\/]_work[\\/][^\\/\s]+[\\/][^\\/\s]+",
        "C:/runner/workspace",
        sanitized,
    )
    return sanitized


def windows_debugger() -> Path | None:
    """Find cdb without recording host-specific installation paths."""
    if found := shutil.which("cdb.exe") or shutil.which("cdb"):
        return Path(found)
    kits = Path("C:/Program Files (x86)/Windows Kits/10/Debuggers/x64/cdb.exe")
    return kits if kits.is_file() else None


def capture_windows_crash_report(case: Case, command: list[str], returncode: int, timeout: float) -> None:
    """Rerun an access violation under cdb and retain only sanitized text.

    Raw process dumps contain stack memory, command lines, and machine paths,
    so CI never uploads them. The debugger is restricted to stack and module
    commands, and this function removes runner and user identity before writing.
    """
    if os.name != "nt" or returncode & 0xFFFFFFFF != 0xC0000005:
        return
    debugger = windows_debugger()
    if debugger is None:
        return
    report = case.capture.with_suffix(".crash.txt")
    report.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            [str(debugger), "-o", "-g", "-G", "-c", "kp;lm;q", *command],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        trace = completed.stdout.decode(errors="replace")
    except subprocess.TimeoutExpired as error:
        trace = (error.stdout or b"").decode(errors="replace") + "\nDEBUGGER TIMEOUT\n"
    report.write_text(
        "privacy: sanitized textual debugger report; no process memory retained\n"
        f"spec: {case_identity(case)}\n"
        f"status: 0x{returncode & 0xFFFFFFFF:08X}\n\n"
        + sanitize_debugger_output(trace),
        encoding="utf-8",
    )


def finish_case(
    case: Case,
    started: float,
    runner: str,
    outcome: str,
    error: str | None,
    returncode: int | None = None,
) -> tuple[Case, str | None]:
    """Report duration immediately and retain bounded, non-secret failure facts."""
    elapsed = time.monotonic() - started
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(
        f"END {case_identity(case)} runner={runner} outcome={outcome} "
        f"elapsed={elapsed:.3f}s utc={now}",
        flush=True,
    )
    if error is not None:
        record = {
            "schema_version": 1,
            "spec": case_identity(case),
            "application": case.app.relative_to(ROOT).as_posix(),
            "runner": runner,
            "outcome": outcome,
            "elapsed_seconds": round(elapsed, 3),
            "exit_status": None if returncode is None else f"0x{returncode & 0xFFFFFFFF:08X}",
        }
        path = failure_record(case)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        if case.capture.is_file():
            shutil.copy2(
                case.capture,
                case.capture.with_name(f"{case.capture.stem}.failure{case.capture.suffix}"),
            )
    return case, error


def run_case(
    case: Case,
    grants: dict,
    timeout: float,
    jobs: int,
    detail: str = "summary",
    runner: str = "semantic",
    allow_missing_shots: bool = False,
) -> tuple[Case, str | None]:
    """Run one specification on the runner its steps require.

    Both runners share this function so a case is wired to the capabilities its
    specification declares exactly once, whichever runner it needs.
    """
    started = time.monotonic()
    print(
        f"START {case_identity(case)} runner={runner} "
        f"utc={datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        flush=True,
    )
    case.capture.parent.mkdir(parents=True, exist_ok=True)
    if runner == "window":
        artifacts = window_artifacts(case)
        artifacts.mkdir(parents=True, exist_ok=True)
        command = [
            str(case.executable),
            "--host-run-window-spec",
            str(case.spec),
            f"--host-window-report={artifacts / 'report.json'}",
            f"--host-window-shot-dir={artifacts}",
        ]
        if allow_missing_shots:
            command.append("--host-window-allow-missing-shots")
    else:
        command = [
            str(case.executable),
            "--host-run-spec",
            str(case.spec),
            f"--host-stats-output={case.capture}",
            f"--host-stats-job-count={jobs}",
            f"--host-stats-detail={detail}",
        ]
    command.extend(grants["flags"])
    with tempfile.TemporaryDirectory(prefix="roc-gui-app-data-") as temporary, \
            tempfile.TemporaryDirectory(prefix="roc-gui-copy-") as scratch:
        storage = Path(temporary)
        # Application data is granted as a fresh private copy, so a case writes
        # through the production capability without mutating checked-in data.
        if seed := grants["app_data_seed"]:
            shutil.copytree(seed, storage, dirs_exist_ok=True)
            command.extend(["--host-cap-app-data", str(storage)])
        # A directory a case may change is granted as a disposable copy of its
        # files, beside which the host stages every replacement it makes.
        if source := grants.get("directory_copy"):
            copy = Path(scratch) / Path(source).name
            copy.mkdir()
            for entry in Path(source).iterdir():
                if entry.is_file() and not entry.is_symlink():
                    shutil.copy2(entry, copy / entry.name)
            command.extend(["--host-cap-dir-copy", str(copy)])
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            error = f"timed out after {timeout:g}s"
            return finish_case(case, started, runner, "timeout", error)
    if completed.returncode != 0:
        diagnostic = completed.stderr.decode(errors="replace").strip()
        capture_windows_crash_report(case, command, completed.returncode, timeout)
        error = f"exit {completed.returncode}: {diagnostic}"
        return finish_case(
            case, started, runner, "process_exit", error, completed.returncode
        )
    if runner == "window":
        # A window run's evidence is its report, not a SQLite capture, which it
        # does not produce.
        report = window_artifacts(case) / "report.json"
        try:
            written = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            message = f"unreadable window report: {error}"
            return finish_case(case, started, runner, "invalid_evidence", message)
        outcome = written.get("outcome")
        # A run that captured no screenshot proved nothing visual. Tolerating
        # that is a decision this suite makes explicitly, never a silence: the
        # unavailable steps are named either way.
        if outcome == "degraded" and allow_missing_shots:
            missing = [
                f"{shot.get('name')}: {shot.get('reason')}"
                for shot in written.get("screenshots", [])
                if not shot.get("file")
            ]
            print(f"DEGRADED {case.spec.relative_to(ROOT)}: "
                  f"{written.get('unavailable_shots', 0)} screenshot(s) unavailable"
                  + (f" ({'; '.join(missing)})" if missing else ""), file=sys.stderr)
            return finish_case(case, started, runner, "degraded", None)
        if outcome != "pass":
            error = f"window report outcome {outcome!r}"
            return finish_case(case, started, runner, "semantic_failure", error)
        return finish_case(case, started, runner, "pass", None)
    try:
        validate_capture(case.capture)
    except (OSError, sqlite3.Error, RuntimeError, ValueError) as error:
        message = f"invalid capture: {error}"
        return finish_case(case, started, runner, "invalid_evidence", message)
    return finish_case(case, started, runner, "pass", None)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patterns", nargs="*", help="glob(s) matched against repository-relative spec paths")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="exclude repository-relative spec paths matching this glob; repeatable")
    parser.add_argument("--jobs", type=int, default=1,
                        help="concurrent cases (default: 1; values above 1 make timing evidence partial)")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--detail", choices=("summary", "full"), default="summary",
                        help="omit setup cycles (summary) or record them too (full)")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--aa", action="store_true",
                        help="repeat each passing case with the same executable for an A/A noise capture")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-host-build", action="store_true",
                        default=os.environ.get(SKIP_HOST_BUILD) == "1")
    parser.add_argument("--only", choices=("all", "semantic", "window"), default="all",
                        help="run only the specifications a given runner handles")
    parser.add_argument("--allow-missing-shots", action="store_true",
                        help="report unavailable screenshots instead of failing; hosted CI "
                             "runners cannot grant screen recording")
    parser.add_argument("--window-retries", type=int, default=0,
                        help="retry a failed window case this many times with fresh artifacts")
    parser.add_argument("--roc", default=os.environ.get("ROC", "roc"))
    parser.add_argument("--roc-opt", choices=("dev", "speed", "size"), default="dev",
                        help="Roc application backend (default: dev); speed and size are LLVM diagnostic builds")
    args = parser.parse_args()
    if args.jobs < 1 or args.timeout <= 0 or args.window_retries < 0:
        parser.error("jobs and timeout must be positive; window retries cannot be negative")
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        parser.error("shard index must be within shard count")
    return args


def main() -> int:
    args = parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output or ROOT / ".test-out" / "specs" / stamp).resolve()
    cases = discover(args.patterns, output, args.exclude, args.roc_opt)
    cases = [case for index, case in enumerate(cases) if index % args.shard_count == args.shard_index]
    if not cases:
        print("error: no .scm specs selected", file=sys.stderr)
        return 2
    try:
        build(cases, args.roc, args.skip_host_build, args.roc_opt)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"error: build failed: {error}", file=sys.stderr)
        return 1

    # Ask the host what each specification needs, before the loopback services
    # start, because the services a run needs come from the cases it will
    # actually execute.
    try:
        described = describe(cases)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    semantic = [case for case in cases if described[case.spec]["runner"] == "semantic"]
    window = [case for case in cases if described[case.spec]["runner"] == "window"]
    if args.only == "semantic":
        window = []
    elif args.only == "window":
        semantic = []
    if not semantic and not window:
        print(f"error: no .scm specs selected for --only {args.only}", file=sys.stderr)
        return 2
    selected = semantic + window

    results: list[tuple[Case, str | None]] = []
    failures = 0
    window_specs = {case.spec for case in window}
    try:
        with fixture_services(selected, described, output):
            if args.fail_fast:
                for case in semantic:
                    result = run_case(case, described[case.spec], args.timeout, args.jobs, args.detail)
                    results.append(result)
                    if result[1] is not None:
                        break
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
                    futures = [
                        pool.submit(run_case, case, described[case.spec], args.timeout, args.jobs, args.detail)
                        for case in semantic
                    ]
                    results.extend(future.result() for future in concurrent.futures.as_completed(futures))

            # Window cases are strictly serial: there is one screen and one
            # focused application, so concurrent runs would photograph each
            # other.
            for case in window:
                for attempt in range(args.window_retries + 1):
                    if attempt:
                        artifacts = window_artifacts(case)
                        shutil.rmtree(artifacts, ignore_errors=True)
                        print(f"RETRY {case.spec.relative_to(ROOT)} "
                              f"({attempt}/{args.window_retries})", file=sys.stderr)
                    result = run_case(
                        case,
                        described[case.spec],
                        args.timeout,
                        1,
                        args.detail,
                        runner="window",
                        allow_missing_shots=args.allow_missing_shots,
                    )
                    if result[1] is None:
                        break
                results.append(result)
                if args.fail_fast and result[1] is not None:
                    break

            for case, error in results:
                relative = case.spec.relative_to(ROOT)
                evidence = (
                    window_artifacts(case) / "report.json"
                    if case.spec in window_specs
                    else case.capture
                )
                if error is None:
                    print(f"PASS {relative} -> {evidence}")
                else:
                    failures += 1
                    print(f"FAIL {relative}: {error}", file=sys.stderr)
                    if case.spec in window_specs:
                        report_window_failure(window_artifacts(case))
            # A/A repeats measure timing noise between two captures, which a
            # window run does not produce.
            if args.aa and failures == 0:
                for case, _ in sorted(
                    (result for result in results if result[0].spec not in window_specs),
                    key=lambda result: result[0].spec,
                ):
                    aa_case = replace(
                        case,
                        capture=case.capture.with_name(f"{case.capture.stem}-aa{case.capture.suffix}"),
                    )
                    _, error = run_case(aa_case, described[case.spec], args.timeout, 1, args.detail)
                    if error is not None:
                        failures += 1
                        print(f"FAIL A/A {case.spec.relative_to(ROOT)}: {error}", file=sys.stderr)
                    else:
                        print(
                            f"A/A {case.spec.relative_to(ROOT)}: "
                            f"python3 scripts/analyze_stats.py {case.capture} --compare {aa_case.capture}"
                        )
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    passed = len(results) - failures
    print(f"{passed}/{len(results)} specs passed; evidence: {output}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
