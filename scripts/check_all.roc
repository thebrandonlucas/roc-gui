#!/usr/bin/env roc-stable
app [main!] {
	cli: platform "https://github.com/roc-lang/basic-cli/releases/download/0.25.0/CZsY7tYZwR3rj9kYbpaCfxki2yVAaRL8bBwMLvB2xkbA.tar.zst",
	roc: "nightly-2026-10-23-18478ff",
}

import cli.Cmd
import cli.OsStr
import cli.Path
import cli.Stderr
import cli.Stdout
import src/MachineCode
import src/Pins

## Everything `kai run check` checks of the repository's Roc.
##
##     kai run check                    # every section below
##     scripts/check_all.roc -- --staged   # the machine-code section, over the Git index
##
## `roc-stable`, which Kaifile.roc fetches, runs this script and checks the
## others. Bare `roc` is the latest nightly: the platform, its applications and
## its benchmarks carry no compiler pin and must check, warning-free, with it.
main! = |args| {
	if args.map(|arg| OsStr.from_raw(arg).display()) == ["--staged"] {
		return machine_code!(Staged)
	}

	Stdout.line!("\n== Compilers")?
	stable!(["version"])?
	nightly!(["version"])?

	Stdout.line!("\n== Compiler pins")?
	tag = match Pins.stable_tag(read!("Kaifile.roc")?) {
		Ok(found) => found
		Err(NoStableCompiler) => return fail!("Kaifile.roc does not fetch roc-stable with FetchLocked(\"roc-stable\", roc_nightly(\"<tag>\"))")
	}
	scripts = roc_files!("scripts")?
	for script in scripts {
		if Pins.roc_pin(read!(script)?) != Ok(tag) {
			return fail!("${script}: the app header must declare roc: \"${tag}\", the roc-stable release in Kaifile.roc")
		}
	}
	for retired in [".roc-version", ".github/roc-nightly.json"] {
		if Path.exists!(Path.unix(retired))? {
			return fail!("${retired}: the platform and its applications float on the latest nightly; remove it")
		}
	}
	applications = roots!()?
	for root in ["Kaifile.roc"].concat(applications) {
		if Pins.roc_pin(read!(root)?) != Err(NoPin) {
			return fail!("${root}: only scripts/ names a compiler; remove the roc header field")
		}
	}
	platform_header = match Str.split_first(read!("platform/main.roc")?, "provides") {
		Ok({ before, .. }) => before
		Err(_) => return fail!("platform/main.roc: no provides clause ends the platform header")
	}
	if platform_header.contains("roc:") {
		return fail!("platform/main.roc: only scripts/ names a compiler; remove the roc header field")
	}
	for root in applications {
		if Pins.platform_of(read!(root)?) != Ok("../../platform/main.roc") {
			return fail!("${root}: an application in this repository depends on ../../platform/main.roc")
		}
	}
	Stdout.line!("PASS every script names ${tag}; ${applications.len().to_str()} applications name no compiler and use the working tree")?

	# The bindings root stands in for platform/main.roc when generating glue, so
	# the targets the compiler validates there must be the platform's own.
	Stdout.line!("\n== Host bindings root")?
	platform_targets = targets_of(read!("platform/main.roc")?)
	if platform_targets == "" or targets_of(read!("platform/main-glue.roc")?) != platform_targets {
		return fail!("platform/main-glue.roc: copy the targets section of platform/main.roc")
	}
	Stdout.line!("PASS platform/main-glue.roc declares the platform's targets")?

	# The development shell and the linker-input producers build from one
	# nixpkgs revision, held twice so that a Kai change never alters a
	# linker input's provenance.
	Stdout.line!("\n== Nix package set")?
	nixpkgs = match (Pins.kaifile_nixpkgs(read!("dependencies/FreeType.roc")?), Pins.pinned_nixpkgs(read!("dependencies/nixpkgs-pin.nix")?)) {
		(Ok(declared), Ok(pinned)) if declared == pinned => pinned
		(Ok(declared), Ok(pinned)) => return fail!("Kaifile.roc takes Nix tools from nixpkgs ${declared}, but dependencies/nixpkgs-pin.nix pins ${pinned}; move both together")
		_ => return fail!("dependencies/FreeType.roc and dependencies/nixpkgs-pin.nix must each name one nixpkgs revision")
	}
	Stdout.line!("PASS Kaifile.roc and the linker inputs build from nixpkgs ${nixpkgs}")?

	machine_code!(Tracked)?

	Stdout.line!("\n== Scripts")?
	# The modules without effects carry the tests of the scripts' logic.
	for source in roc_files!("scripts/src")? {
		stable!(["test", source])?
	}
	for script in scripts {
		stable!(["check", script])?
	}
	stable!(["fmt", "--check", "scripts"])?

	# `roc check` exits nonzero on a warning as well as an error, and `roc test`
	# on an application runs the expectations of every module it reaches,
	# the platform's among them. Every root runs, so one report names them all.
	Stdout.line!("\n== Applications")?
	var $failed = []
	for root in applications {
		for command in [["check", "--no-cache", root], ["test", "--no-cache", root]] {
			Stdout.line!("+ roc ${Str.join_with(command, " ")}")?
			if Cmd.new_str("roc").args_str(command).exec_exit_code!()? != 0 {
				$failed = $failed.append("roc ${Str.join_with(command, " ")}")
			}
		}
	}
	if !$failed.is_empty() {
		return fail!("errors, warnings or failed expectations from:\n  ${Str.join_with($failed, "\n  ")}")
	}
	Stdout.line!("PASS ${applications.len().to_str()} applications check without warnings and pass their tests")
}

# Every example and benchmark application root, in a stable order.
roots! : () => Try(List(Str), _)
roots! = || {
	var $found = []
	for directory in ["examples", "benchmarks"] {
		for entry in Path.list!(Path.unix(directory))? {
			main = Path.unix("${Path.display(entry)}/main.roc")
			if Path.is_dir!(entry)? and Path.is_file!(main)? {
				$found = $found.append(Path.display(main))
			}
		}
	}
	Ok($found.sort_with(by_name))
}

# Machine code is produced by a verified release, never committed. `Staged`
# reads what the next commit would record; `Tracked` reads every tracked file
# in the checkout.
machine_code! : [Staged, Tracked] => Try({}, _)
machine_code! = |scope| {
	Stdout.line!("\n== Machine code")?
	listing = match scope {
		Staged => ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
		Tracked => ["ls-files", "-z"]
	}
	paths = Cmd.new_str("git").args_str(listing).exec_output!()?.stdout_utf8.split_on("\u(0)").keep_if(|path| !path.is_empty())
	var $rejected = []
	for path in paths {
		bytes = match scope {
			Staged => Cmd.new_str("git").args_str(["show", ":${path}"]).exec_output_bytes!()?.stdout_bytes
			Tracked => if (Path.is_sym_link!(Path.unix(path))?) [] else Path.read_bytes!(Path.unix(path))?
		}
		match MachineCode.kind(bytes) {
			Some(kind) => {
				$rejected = $rejected.append("${path}: ${kind}")
			}
			None => {}
		}
	}
	if !$rejected.is_empty() {
		return fail!("compiled machine code must be produced by a verified release, not committed:\n  ${Str.join_with($rejected, "\n  ")}")
	}
	Stdout.line!("PASS ${paths.len().to_str()} files hold no machine code")
}

# The `.roc` files directly inside `directory`, in a stable order.
roc_files! : Str => Try(List(Str), _)
roc_files! = |directory| Ok(Path.list!(Path.unix(directory))?.map(Path.display).keep_if(|path| path.ends_with(".roc")).sort_with(by_name))

# Byte order, so listings are the same on every file system.
by_name : Str, Str -> [Before, Same, After]
by_name = |a, b| by_bytes(a.to_utf8(), b.to_utf8())

by_bytes : List(U8), List(U8) -> [Before, Same, After]
by_bytes = |a, b|
	match (a, b) {
		([], []) => Same
		([], _) => Before
		(_, []) => After
		([x, .. as rest_a], [y, .. as rest_b]) => if (x < y) Before else if (x > y) After else by_bytes(rest_a, rest_b)
	}

# A platform header's targets section, as written.
targets_of : Str -> Str
targets_of = |source|
	match Str.split_first(source, "\ttargets: {") {
		Ok({ after, .. }) =>
			match Str.split_first(after, "\n\t}") {
				Ok({ before, .. }) => before
				Err(_) => ""
			}
		Err(_) => ""
	}

read! : Str => Try(Str, _)
read! = |path| Path.read_utf8!(Path.unix(path))

# Print a compiler command, then run it with inherited output.
stable! : List(Str) => Try({}, _)
stable! = |args| {
	Stdout.line!("+ roc-stable ${Str.join_with(args, " ")}")?
	Cmd.new_str("roc-stable").args_str(args).exec_cmd!()
}

nightly! : List(Str) => Try({}, _)
nightly! = |args| {
	Stdout.line!("+ roc ${Str.join_with(args, " ")}")?
	Cmd.new_str("roc").args_str(args).exec_cmd!()
}

fail! = |message| {
	Stderr.line!("error: ${message}")?
	Err(Exit(1))
}
