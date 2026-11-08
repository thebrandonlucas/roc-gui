# roc-gui

Build native, state-driven GUI applications in [Roc](https://www.roc-lang.org),
hosted by [GPUI](https://www.gpui.rs). 

Read the [manual](https://lukewilliamboswell.github.io/roc-gui/) to get started.

- Cross-platform native UI (macOS, Linux Wayland, Windows)
- Builtin behavioural and performance testing harness using a S-expression format
- Builtin performance observatory streaming to a SQLite db 

**Work In Progress / Experimental** this platform combines a lot of experimental ideas, and is early in development. The docs are BETA and needs a lot of refinement -- if you want to help let me know! I have chosen to include LLM generated docs and am gradually refining things and rapidly iterate on ideas, expect significant breaking changes.

| | | |
|:---:|:---:|:---:|
| [![HTTP Workbench](https://lukewilliamboswell.github.io/roc-gui/gallery/http-workbench.gif)](examples/http-workbench/) <br> [HTTP Workbench](examples/http-workbench/) | [![Database Browser](https://lukewilliamboswell.github.io/roc-gui/gallery/database-browser.gif)](examples/database-browser/) <br> [Database Browser](examples/database-browser/) | [![File Explorer](https://lukewilliamboswell.github.io/roc-gui/gallery/file-explorer.gif)](examples/file-explorer/) <br> [File Explorer](examples/file-explorer/) |
| [![Terminal Workspace](https://lukewilliamboswell.github.io/roc-gui/gallery/terminal-workspace.gif)](examples/terminal-workspace/) <br> [Terminal Workspace](examples/terminal-workspace/) | [![Image Library](https://lukewilliamboswell.github.io/roc-gui/gallery/image-library.gif)](examples/image-library/) <br> [Image Library](examples/image-library/) | [![Music Player](https://lukewilliamboswell.github.io/roc-gui/gallery/music-player.gif)](examples/music-player/) <br> [Music Player](examples/music-player/) |
| [![Clipboard History](https://lukewilliamboswell.github.io/roc-gui/gallery/clipboard-history.gif)](examples/clipboard-history/) <br> [Clipboard History](examples/clipboard-history/) | [![System Monitor](https://lukewilliamboswell.github.io/roc-gui/gallery/system-monitor.gif)](examples/system-monitor/) <br> [System Monitor](examples/system-monitor/) | [![Settings Center](https://lukewilliamboswell.github.io/roc-gui/gallery/settings-center.gif)](examples/settings-center/) <br> [Settings Center](examples/settings-center/) |
| [![Device Configurator](https://lukewilliamboswell.github.io/roc-gui/gallery/device-configurator.gif)](examples/device-configurator/) <br> [Device Configurator](examples/device-configurator/) | [![Animation Studio](https://lukewilliamboswell.github.io/roc-gui/gallery/animation-studio.gif)](examples/animation-studio/) <br> [Animation Studio](examples/animation-studio/) | [![Redis Explorer](https://lukewilliamboswell.github.io/roc-gui/gallery/redis-explorer.gif)](examples/redis-explorer/) <br> [Redis Explorer](examples/redis-explorer/) |

Build from a checkout with `kai run build`; see the
[development setup](docs/getting-started.adoc).

Contributors should read [AGENTS.md](AGENTS.md). Licensed under
[LICENSE](LICENSE); third-party notices are in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
