# Development environment and tasks for roc-gui, realised by Kai.
#
#     kai run check    # the repository's Roc: pins, machine code, scripts, applications
#     kai run build    # the host and every application
#     kai run test     # the application specifications
#     kai run lint     # Clippy over the host
#     kai run docs     # HTML, PDF, Markdown and compiler API reference
#     kai build freetype          # the FreeType linker input, in the Nix sandbox
#     kai build freetype --plan   # its snapshot, derivation and output, as JSON
#     kai shell        # the development environment
#     kai update       # refresh .kai/lock.json
#
# `roc-stable` is the nightly named below; it runs the scripts under scripts/.
# Bare `roc` is the latest nightly, which the machine provides: the platform,
# its applications and its benchmarks name no compiler. The scripts and docs
# environments are pinned downloads; dev and the FreeType producer take their
# tools from the nixpkgs revision dependencies/FreeType.roc pins.
app [kaifile] {
	pf: platform "https://github.com/thebrandonlucas/kai/releases/download/v0.0.12/G3CQ6Ed3h7vyvV4eDvwH1J8UqBv2wEtkb9jLJhFkU5ny.tar.zst",
	std: "https://github.com/thebrandonlucas/kai/releases/download/v0.0.12/std-6VuNBrdv6tT7ZAVD4bWGBYYwk1KJoXP7gCnFip5VSK11.tar.zst",
}

import std.Std
import dependencies/FreeType

# A Roc nightly's compiler, for each declared system.
roc_nightly = |tag| {
	nightly = |system, build| {
		top = "roc_nightly-${build}-${tag.drop_prefix("nightly-")}"
		{ system, url: "https://github.com/roc-lang/nightlies/releases/download/${tag}/${top}.tar.gz", mirrors: [], program: Archive("${top}/roc") }
	}
	[nightly("x86_64-linux", "linux_x86_64"), nightly("aarch64-darwin", "macos_apple_silicon")]
}

# The shared documentation renderer, one file per system.
docs_renderer = ["x86_64-linux", "aarch64-darwin"].map(|system| { system, url: "https://github.com/lukewilliamboswell/roc-automation/releases/download/tools-0.6.0/roc-docs-${system.to_str()}", mirrors: [], program: File })

kaifile = Std.kaifile(
	[
		Name("roc-gui"),
		Systems(["x86_64-linux", "aarch64-darwin"]),
		FetchLocked("roc-stable", roc_nightly("nightly-2026-10-23-18478ff")),
		FetchLocked("roc-docs", docs_renderer),
		Environment(
			"scripts",
			[
				Tools(["roc-stable#roc-stable"]),
				# Every bundle the scripts depend on, including dependencies of
				# dependencies: `roc-stable deps scripts/check_all.roc` lists them.
				RocPackages([
					"https://github.com/roc-lang/basic-cli/releases/download/0.25.0/CZsY7tYZwR3rj9kYbpaCfxki2yVAaRL8bBwMLvB2xkbA.tar.zst",
					"https://github.com/roc-lang/http/releases/download/1.0.0/6ZUwqYhCS8PU9Mo6MF7oV82ET2o7KYb57CLKDq4cq4sS.tar.zst",
				]),
				Expect(["roc", "git"]),
			],
		),
		# Regenerating the host bindings formats them with the repository's Rust
		# toolchain, which rustup selects from rust-toolchain.toml.
		Environment("glue", [Extend("scripts"), Expect(["cargo"])]),
		# The renderer is a verified native download; API generation uses the
		# caller's compiler, independently of the tooling compiler above.
		Environment("docs", [Tools(["roc-docs#roc-docs"]), Expect(["realpath", "sh"])]),
		Environment(
			"dev",
			[
				Extend("scripts"),
				Tools([
					"nix#rustup",
					"nix#zig_0_16",
					"nix#python3",
					"nix#pre-commit",
					"nix#pkg-config",
					"nix#clang",
					"nix#cmake",
					"nix#gnumake",
					"nix#curl",
					"nix#zstd",
				]),
				OnSystems(
					["x86_64-linux"],
					[
						Tools([
							"nix#freetype",
							"nix#fontconfig",
							"nix#wayland",
							"nix#libglvnd",
							"nix#libxkbcommon",
							"nix#alsa-lib",
							"nix#vulkan-loader",
							"nix#vulkan-headers",
						]),
					],
				),
				# build.py admits the FreeType linker input against `kai build freetype --plan`.
				Expect(["kai"]),
			],
		),
		Shell("default", [Use("dev")]),
		Task("check", [Use("scripts"), Run(["scripts/check_all.roc"])]),
		Task("build", [Use("dev"), Run(["python3", "build.py"])]),
		Task("test", [Use("dev"), Run(["python3", "scripts/run_specs.py", "--roc", "roc"])]),
		Task("lint", [Use("dev"), Run(["python3", "scripts/run_cargo.py", "clippy", "--locked", "--package", "roc-gui-host", "--all-targets", "--no-deps", "--", "-D", "warnings"])]),
		Task("docs", [Use("docs"), Run(["roc-docs", "build", "--workspace", ".", "--pdf-filename", "roc-gui.pdf", "--site-url", "https://lukewilliamboswell.github.io/roc-gui/", "--api-entrypoint", "platform/main.roc"])]),
		Task("docs-path", [Use("docs"), Run(["sh", "-c", "realpath \"$(command -v roc-docs)\""])]),
		# Regenerate the committed host bindings: regenerate-glue -- <roc source>.
		Task("regenerate-glue", [Use("glue"), Run(["scripts/regenerate_glue.roc"])]),
		# Render a release's notes: release-notes -- <version> <bundle filename> <output>.
		Task("release-notes", [Use("scripts"), Run(["scripts/release_notes.roc"])]),
		# The tooling compiler, as release notes record it.
		Task("compiler-version", [Use("scripts"), Run(["roc-stable", "version"])]),
	].concat(FreeType.settings),
)
