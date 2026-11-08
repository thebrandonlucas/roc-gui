# The one nixpkgs revision the linker-input producers build from, as
# `builtins.fetchTree` takes it. `narHash` makes the fetch fail if the tree
# differs. Kaifile.roc's development environment names the same revision, and
# `kai run check` fails if the two disagree; a Kai change therefore never
# changes a linker input's provenance. The FreeType build records it as the
# package pin of its tools.
{
  type = "github";
  owner = "NixOS";
  repo = "nixpkgs";
  rev = "6774f7bc253789b113a4f39285dc0fa100abeacc";
  narHash = "sha256-MYiI+CzL0tuWgRPjGsKCDHqYs2T3OzMlMQWOYWG0qso=";
  lastModified = 1790046670;
}
