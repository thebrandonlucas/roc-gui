## Which compiler each Roc root is written for, read from text without running
## one. Adapted from roc-automation's scripts/src/Pins.roc.
Pins := [].{

	## The nightly tag that the text of `Kaifile.roc` fetches as `roc-stable`.
	stable_tag : Str -> Try(Str, [NoStableCompiler])
	stable_tag = |kaifile|
		match Str.split_on(kaifile, "FetchLocked(\"roc-stable\", roc_nightly(\"") {
			[_, after] =>
				match Str.split_first(after, "\"") {
					Ok({ before, .. }) if before != "" => Ok(before)
					_ => Err(NoStableCompiler)
				}
			_ => Err(NoStableCompiler)
		}

	## The nixpkgs revision `Kaifile.roc` takes its Nix tools from.
	kaifile_nixpkgs : Str -> Try(Str, [NoNixpkgs])
	kaifile_nixpkgs = |kaifile| quoted_after(kaifile, "NixPackages(\"github:NixOS/nixpkgs/").map_err(|_| NoNixpkgs)

	## The nixpkgs revision `dependencies/nixpkgs-pin.nix` pins for the linker
	## inputs.
	pinned_nixpkgs : Str -> Try(Str, [NoNixpkgs])
	pinned_nixpkgs = |pin| quoted_after(pin, "rev = \"").map_err(|_| NoNixpkgs)

	## Whether `source` is an application, which has an `app` header.
	is_app : Str -> Bool
	is_app = |source| header(Str.split_on(source, "\n")) != ""

	## The release named by the `roc` field of an app header.
	roc_pin : Str -> Try(Str, [NoPin])
	roc_pin = |source|
		match header_field(source, "roc") {
			Ok(value) => quoted(value).map_err(|_| NoPin)
			Err(_) => Err(NoPin)
		}

	## The platform an app header depends on, as written.
	platform_of : Str -> Try(Str, [NoPlatform])
	platform_of = |source|
		match header_field(source, "pf") {
			Ok(value) if value.starts_with("platform ") => quoted(Str.drop_prefix(value, "platform ")).map_err(|_| NoPlatform)
			_ => Err(NoPlatform)
		}
}

# The text after the only occurrence of `prefix`, up to the next double quote.
quoted_after : Str, Str -> Try(Str, [Missing])
quoted_after = |text, prefix|
	match Str.split_on(text, prefix) {
		[_, after] =>
			match Str.split_first(after, "\"") {
				Ok({ before, .. }) if before != "" => Ok(before)
				_ => Err(Missing)
			}
		_ => Err(Missing)
	}

# The one value of a header field named `name`, trimmed.
header_field : Str, Str -> Try(Str, [Missing])
header_field = |source, name| {
	fields = match Str.split_first(header(Str.split_on(source, "\n")), "{") {
		Ok({ after, .. }) => Str.split_on(after, ",")
		Err(_) => []
	}
	match fields.keep_oks(|field| Str.split_first(field, ":")).keep_if(|field| field.before.trim() == name) {
		[{ after, .. }] => Ok(after.trim())
		_ => Err(Missing)
	}
}

# The text between a value's only pair of double quotes.
quoted : Str -> Try(Str, [NotQuoted])
quoted = |value|
	match Str.split_on(value.trim(), "\"") {
		["", text, ""] => Ok(text)
		_ => Err(NotQuoted)
	}

# The app header, from `app` up to the brace that closes it. A module has none.
header : List(Str) -> Str
header = |lines|
	match lines {
		[line, ..] if line.starts_with("app ") =>
			match Str.split_first(Str.join_with(lines, "\n"), "}") {
				Ok({ before, .. }) => before
				Err(_) => ""
			}
		[_, .. as rest] => header(rest)
		[] => ""
	}

script : Str
script = "#!/usr/bin/env roc-stable\napp [main!] {\n\tcli: platform \"https://example.com/cli.tar.zst\",\n\troc: \"nightly-2026-10-23-18478ff\",\n}\n\nmain! = |_| { roc: \"not a header\" }\n"

example : Str
example = "app [State, main] {\n\tpf: platform \"../../platform/main.roc\",\n\tredis: \"https://example.com/redis.tar.zst\",\n}\n"

expect Pins.stable_tag("\t\tFetchLocked(\"roc-stable\", roc_nightly(\"nightly-2026-10-23-18478ff\")),\n") == Ok("nightly-2026-10-23-18478ff")
expect Pins.stable_tag("# `roc-stable` is fetched below\n") == Err(NoStableCompiler)
expect Pins.stable_tag("FetchLocked(\"roc-stable\", roc_nightly(\"\"))") == Err(NoStableCompiler)
expect Pins.is_app(script) and Pins.is_app("app [main!] {}\n")
expect !Pins.is_app("Pins := [].{\n\tapp = 1\n}\n") and !Pins.is_app("package [A] {}\n")
expect Pins.roc_pin(script) == Ok("nightly-2026-10-23-18478ff")
expect Pins.roc_pin(example) == Err(NoPin)
expect Pins.roc_pin("app [main!] { heroc: \"nightly-1\" }\n") == Err(NoPin)
expect Pins.roc_pin("app [main!] { roc: \"a\", roc: \"b\" }\n") == Err(NoPin)
expect Pins.platform_of(example) == Ok("../../platform/main.roc")
expect Pins.platform_of(script) == Err(NoPlatform)
expect Pins.platform_of("app [config] { pf: platform \"https://example.com/p.tar.zst\" }\n") == Ok("https://example.com/p.tar.zst")
expect Pins.kaifile_nixpkgs("\tPackages(\"nix\", From(NixPackages(\"github:NixOS/nixpkgs/6774f7bc\"))),\n") == Ok("6774f7bc")
expect Pins.kaifile_nixpkgs("Packages(\"nix\", From(NixPackages(\"github:NixOS/nixpkgs/nixos-unstable\")))") == Ok("nixos-unstable")
expect Pins.kaifile_nixpkgs("Name(\"x\")") == Err(NoNixpkgs)
expect Pins.pinned_nixpkgs("{\n  type = \"github\";\n  rev = \"6774f7bc\";\n}\n") == Ok("6774f7bc")
expect Pins.pinned_nixpkgs("{ }") == Err(NoNixpkgs)
