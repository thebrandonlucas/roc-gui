# Issues backlog

Gaps between the documented ideal state in `docs/` and the repository as it is.
Each entry names its effect and the change that closes it. Remove an entry when
the change lands; do not soften the docs to match the gap.

## Before 0.1.0

What must happen before the final release. `0.1.0-rc1` was published on
2026-10-24 with the four defects below named as known issues in its notes.
Each item either links an entry below or is a maintainer action.

- [ ] Build Observatory with the default backend; see "RELEASE BLOCKER: the
  default backend does not finish building Observatory".
- [ ] Pass Observatory's window Timeline on macOS and Windows; see "RELEASE
  BLOCKER: Observatory's window Timeline fails on hosted macOS and Windows
  runners".
- [ ] Build on Windows without the compiler crashing; see "RELEASE BLOCKER:
  the compiler intermittently crashes on Windows".
- [ ] Make Observatory's folder rewatch deterministic and unskip it; see
  "RELEASE BLOCKER: Observatory's folder rewatch sometimes counts a change".
- [ ] Dispatch `release.yml` with `0.1.0` once the items above are closed,
  from the commit of the candidate that stood without change.

## Linux producer toolchain verification

- [ ] **Restore Meson's fortify fixture under the Nix compiler wrapper.** Meson
  1.12.0's `common/282 -D_FORTIFY_SOURCE=2 and -O0` fixture conflicts with the
  locked nixpkgs wrapper's injected fortify flags. The Nix override excludes
  this fixture while retaining the other upstream project tests. Adapt the
  fixture to the wrapper or adopt an upstream fix, then remove the exclusion.

## Kai verification and compiler watching

- [ ] **Support NixOS executable loading.** Linux executables select the native
  system ELF loader. The Nix development shell supplies build dependencies, but
  running examples requires compatible native desktop runtime libraries. Do
  not inject newer Nix glibc-dependent libraries into the system loader through
  `LD_LIBRARY_PATH`; add and verify a coherent NixOS loader/runtime path.

## Resource broker and confinement foundation

- [ ] **The linked process is not an untrusted-application boundary.** Implement
  Linux application-process confinement and an out-of-process trusted broker.
  Define the compiler, runtime, native-library and packaging trust base; prevent
  syscall, inherited-descriptor, dynamic-library, IPC and dependency escape
  routes; and verify denial outside grants. The audited starting point and
  platform matrix are in `wip/resource-access-inventory.md`.

- [ ] **No grant is enforced, and no trusted surface lists them.**
  `crates/host/src/grant.rs` is the one model `docs/resource-access.adoc`
  describes — resource identity, rights, origin, lifetime, parent, root,
  revocation — with one acceptance point and one revocation linearisation for
  the whole platform. All twelve resources record their grants in it, and
  `(expect-grants ...)` states what an application is holding. Two things the
  contract asks for remain, and neither is something a resource can supply on
  its own.

  Every grant records `consent-only`. Every chooser reopens the chosen resource
  with the process's own authority, and every other origin is a command-line
  flag, so nothing is `brokered` until the confined-process work above lands.
  The specification vocabulary already distinguishes the two, so the day a grant
  becomes brokered is a specification change rather than a claim in prose.

  The trusted *App access* surface now exists: the host's own chord opens it, it
  lists every grant from `grant::enumerate` with the same rendering the evidence
  uses, and each root carries a control that calls `grant::revoke`. Pressing that
  control is not yet driven by a specification — the surface has no locator by
  construction, so a window case cannot name the button — and until it is, the
  withdrawal path is covered only by `revoke-file-grants` and `expect-grants`.
  Close that with a way to drive host-owned controls, not by giving the surface
  a node.

  Adopting the kernel found three things worth keeping in mind for the rest of
  this work, each recorded in `grant.rs` where it was fixed: rights are not
  comparable across resource shapes, a handle may be consumed by the very
  operation that derives from it, and derivation crosses resource kinds — a
  database snapshot descends from the directory its bytes were read through, and
  matching a child on its own kind left that snapshot readable after the project
  was revoked.

- [ ] **Trusted identity, access review, and revocation are absent.** Define
  stable publisher/package identity, remembered-grant storage and migration,
  expiry and a protected App access surface. Files now carry root/child ancestry
  and a host-owned revocation linearization rule; extend that rule to other
  resources and certify cross-process queued/running races and already-returned
  byte policy under confinement.

- [ ] **Trusted file workflows remain incomplete.** Open Project is presented by
  the operating system on both hosts: the XDG Desktop Portal on Linux Wayland and
  the window-owned native directory panel on macOS. Both record grant origin and
  parent lineage through `crates/host/src/grant.rs`, and `--host-cap-dir` remains
  development provisioning.

  Neither host is a powerbox yet, and the entry previously said this only of
  macOS. `open_selected` (`crates/host/src/files.rs`) is shared by both and
  reopens the chosen path with `ambient_authority()`: the portal hands back a URI
  and this host takes the path rather than the descriptor, so on Linux too the
  grant carries no authority the process did not already hold. Both are recorded
  as `Enforcement::ConsentOnly`, which is honest consent and a real record of a
  real decision, but not confinement. Closing that needs the confined-process
  work above, after which the broker returns a descriptor and the constant
  becomes `Brokered` with no change to the Roc API.

  Open Document's single-file read grant (`pick_file!`, recorded as a
  `document` root) shares the same `ConsentOnly` enforcement, as does a dropped
  file (origin `drop`): the host takes the path GPUI's drag-and-drop reports and
  opens it with the process's own authority. A remembered grant is reopened the
  same way, after the recent list compares the file's identity (device and
  inode) with the one remembered; a file swapped in between that check and the
  open is reached by name, not by the identity checked. Brokered reopening needs
  a descriptor or a document-portal identity kept by the broker. Add edit
  grants, and brokered atomic Save As with overwrite, race, disk-full, cleanup,
  cancellation and retry semantics.

  Drag-and-drop is exercised through GPUI's own file-drop events on Linux
  Wayland, from a specification; certify a person dragging from a file manager
  on Wayland and macOS, including a drag that leaves the window and returns.

- [ ] **Portal parenting and protected consent need external certification.**
  GPUI does not expose an xdg-foreign Wayland surface handle to this host,
  so the portal request cannot yet name its parent window. Export that handle,
  attribute focus, and certify compositor placement, protected portal identity,
  cancellation and accessibility on a packaged confined application. Headless
  semantic specifications cannot supply this evidence.

- [ ] **Platform enforcement remains unverified.** Implement and test the
  complete confinement/broker boundary on Linux Wayland. Define and verify
  macOS sandbox, entitlement, trusted-panel, signing and notarization behavior
  before adding that target; other platforms require equivalent evidence.

- [ ] **Absent native effects have not been proven unreachable.** Audit secure
  randomness, URI opening, webviews, microphone/camera/screen capture,
  drag-and-drop/sharing, file clipboard, global input/automation, accessibility,
  native extensions, IPC/listening sockets, inherited descriptors and linked
  dependencies. Add no public API until its complete broker policy and tests
  land.

- [ ] **Broker trusted TCP destinations and revocation.** Numeric exact-endpoint
  provisioning deliberately performs no DNS and serves development and
  automation. Add named user-approved destinations, revocation that closes
  owned streams, and lifecycle evidence through a trusted connection broker
  before applications present a general-purpose Connect UI.

- [ ] **Broker trusted HTTP destinations at runtime.** The provisioned origin
  grant pins non-literal DNS resolution, disables ambient proxies, rejects
  credential-bearing URLs, and rechecks redirects against the granted origin.
  Add user-visible named destination setup and consent backed by an OS
  credential store. Audit platform-specific resolver behavior and IPv4-mapped
  IPv6 classification before treating provisioning flags as user consent.

## Platform API gaps

Shapes the platform's own API presents wrongly or cannot present at all,
independent of any one application.

- [ ] **A resource handle captured by a task closure cannot be stored by its
  completion.** Writing `Tcp.Stream` back into application state from
  inside `resolve`, using the handle the surrounding `Action.task` captured,
  segfaults the process non-deterministically — the capture is released when the
  task's closure is, so the completion stores a dangling resource. Recovering the
  same handle from the state the completion is given is safe and is what Redis
  Explorer now does, but nothing in the API says which of the two is correct, and
  the wrong one fails as a crash rather than as a type error. Either the capture
  must keep the resource alive for the completion, or storing one must be
  rejected at compile time.

- [ ] **No asset root resolves relative to the application itself.** The three
  roots are the executable's directory, the process working directory, and the
  host-provisioned content directory. None of them is "the directory this
  application ships in", which is what `roc app.roc` actually wants: the
  executable is a build output in a temporary directory, and the working
  directory is wherever the shell happens to be. `music-player` therefore reads
  its cover from `working_directory("examples/music-player/assets")`, which is
  correct when an example is run from the checkout root as the README says and
  wrong from anywhere else. Closing this needs the application's own location to
  reach the host, which is packaging identity rather than an asset-surface
  change.

  It also cost a specification. `specs/cover-art-denied.scm` proved the missing
  cover state by withholding the content-directory grant; with a root that
  resolves without provisioning there is no way to make the read fail from a
  specification, so the case was removed rather than left asserting something it
  no longer caused. The refused open and refused read are still covered by the
  asset host's own tests.

- [ ] **A content directory is not an application identity.** A
  `ContentDirectory` store resolves to whatever `--host-cap-assets` names, which
  is development and packaging provisioning, not a stable per-application
  installed location. Until packaging identity exists, two applications run from
  the same host configuration share one content root, and an installed layout
  has nothing to resolve against.

- [ ] **Asset stores have no scaling case.** The manifest check is constant-time
  in the number of assets by construction, and one read is bounded at 64 MiB,
  but nothing measures an application reading many assets across many tasks.
  A scaling case belongs with the example that adopts the API.

- [ ] **A very long list scrolls in coarse steps.** GPUI places a uniform
  list's content with `f32` logical pixels, which are exact only to about
  16.7 million. A million 28-pixel rows are 28 million pixels tall, where
  adjacent offsets are 2 pixels apart; ten million rows would be 32 pixels
  apart, more than a row. Close by positioning a list of rows produced on demand
  relative to its mounted window rather than by an absolute offset.

- [ ] **Rows produced on demand are exercised on Linux only.** The viewport
  turns, deferred frame settlement, and scroll requests run through GPUI's
  uniform list on every platform, but `window-rows.scm` and
  `window-provide-1m.scm` have run only on Linux. Run them on macOS and
  Windows.

## Element appearance

- [ ] **Run `expect-ink` in a window on Linux and Windows.** It passes on
  arm64 macOS for Counter's numeral and Observatory's palette chord.

- [ ] **Three macOS window specifications fail on the migrated GPUI host.**
  `clipboard-history/specs/window-history.scm` reports "Cancel private next"
  laid out at x 929–983 but not on screen, locally and on CI.
  `clipboard-history/specs/window-denied.scm` and
  `system-monitor/specs/window-plot-width.scm` fail on the hosted arm64 runner
  (producer run 35943508264) but pass locally. The linker-input producer and
  the CI window job exclude them. Recheck them once text draws, since text
  that is not shaped also changes layout widths, then remove the excludes.

- [ ] **No letter spacing.** A small muted caption above a large numeral is
  conventionally tracked out, and tracking is what distinguishes an eyebrow
  label from ordinary body text once family is unavailable. `counter`'s per-card
  captions are plain small grey text instead. GPUI has no letter-spacing
  concept at all: neither `TextStyle` nor `TextStyleRefinement` carries one, and
  the shaper takes none, so this needs an upstream field before a
  `Gui.Style` letter-spacing field can mean anything.

- [ ] **A border is one colour on all four sides.** Per-side widths have
  landed, and `terminal-workspace` now draws one hairline on the edge that faces
  the next region instead of boxing every region and holding the boxes apart
  with a 1-point seam. Per-side colour is not expressible: GPUI's `Style`
  carries `border_widths` as `Edges` but a single `border_color`, so a side
  cannot have a colour of its own without an upstream change.

- [ ] **A large SVG is rasterized at its own size and then never painted.**
  GPUI decodes an image-asset SVG through
  `SvgRenderer::render_single_frame(&bytes, 1.0)` (`crates/gpui/src/platform.rs`,
  `ImageFormat::Svg`), a scale-factor raster, so the raster follows the file's intrinsic
  size and the element's box is never an input: `SvgSize::Size(_)` exists but the
  image-asset path never uses it. `image-library`'s 8000x6000 fixtures therefore
  produce a 48-megapixel frame that nothing paints, while the 24x24 glyph in
  `icons/unreadable.svg` paints correctly — proved by
  `examples/image-library/specs/window-unreadable.scm` against a gallery whose
  thumbnails are blank. The element geometry is right: the same window run
  measures each thumbnail at exactly 88x88 and the viewer image on screen. This
  needs `SvgSize::Size` at the laid-out box upstream, or a host-side SVG
  rasterizer, and should not be worked around by shrinking the fixtures, which
  are deliberately larger than any box they are put in.

- [ ] **Image decode status is not represented in the mounted graph.** GPUI's
  image asset decoder owns asynchronous success and failure after mounting, but
  does not expose that state to the host element. Add an owner callback that
  records decoded dimensions/frames or a content-free failure category and
  renders a semantic per-image fallback; do not duplicate GPUI's decoder in the
  semantic runner.

## Input and accessibility

- [ ] **The multi-line textarea has no selection, IME, or clipboard.** The
  production textarea accepts ordinary character, Enter, and Backspace input
  and routes complete controlled values through Roc. Close the desktop-editor
  gap with GPUI `EntityInputHandler` selection/marked-text ownership, mouse hit
  testing, copy/cut/paste, and specifications driven through the same route.

- [ ] **The single-line text input has no clipboard or undo history.** It
  already supports focus, caret motion, selection, keyboard deletion, controlled
  updates, submission, and IME composition, so this is a narrower gap than the
  textarea's above. Close by routing platform clipboard
  operations and a bounded per-editor undo/redo history through the production
  GPUI input actions, with semantic specifications that never record contents.

- [ ] **Native accessibility roles and names are not exported.** Buttons,
  checkboxes, and scroll regions have stable semantics in the canonical graph,
  but the GPUI host does not yet publish them to each operating system's
  accessibility API. Close with platform accessibility nodes verified by an
  external accessibility client, while retaining the same semantic names used
  by specifications.

- [ ] **Popover content cannot be operated.** A popover's surface presents
  while the pointer rests on its anchor or focus is inside it, so moving the
  pointer from the anchor onto the surface closes it. Tooltip-style notes need
  nothing more, but a popover holding controls needs the surface to count as
  part of the hover region, with a grace period for the pointer's travel
  between them, decided by the graph so both runners share it.

- [ ] **Nested hover regions are delivered in the semantic runner's order.** A
  `hover-enter` step delivers each target the pointer rests on, outermost first,
  and a target a handler's rebuild retired is skipped because its state moved to
  its replacement. GPUI orders the same callbacks by its own hitbox traversal.
  No example nests two handler-bearing regions yet; when one does, pin the
  order GPUI uses and make the runner follow it.

- [ ] **Popover placement is verified on Linux only.** The surface is a
  deferred, window-anchored layer that flips to the opposite side when the
  window lacks room. Verify placement, flipping, and focus-driven opening on
  macOS and Windows, including a window whose content is scaled.

- [ ] **Shortcuts are verified on Linux only.** Chords are parsed and matched
  by GPUI, and `secondary` resolves to Ctrl on Linux. Verify on macOS (Cmd as
  `secondary`, Option producing characters) and Windows (AltGr layouts, where a
  chord's character arrives with Ctrl and Alt held) that the root listener
  receives the keystrokes a person means as shortcuts, and that a focused text
  field still keeps every character it types.

- [ ] **A focus request into rows GPUI has not drawn moves nothing.** The graph
  chooses the first enabled control inside the requesting region and counts it
  as focused, but a control inside a virtual list has no native view until GPUI
  draws its row, so the window cannot focus one mounted just outside the
  viewport. Close by bringing the row into view before focusing it, as a scroll
  request does, and count the request only once the window has focused it.

- [ ] **Composite directory navigation has no roving focus.** A user can reach
  and activate every folder with Tab and Enter or Space. Close with a semantic
  list/list-item element whose Up, Down, Home, and End behavior, selected state,
  scroll-into-view behavior, scaling case, and operating-system accessibility
  mapping all use the production event path.

## Application feature slices

Each example proves a complete production slice. These are the slices not yet
built on top of them; none is a defect in what is there.

- [ ] **File Explorer writable powerbox and desktop integration.** The read-only
  explorer navigates capability-scoped child folders, preserves back/forward
  history, selects files and folders, reports typed failures, and virtualizes a
  realistic directory. Add a separately approved writable-directory grant and
  direct-child create, rename, copy, move, trash, and restore operations with
  collision policy, partial-result recovery, cancellation, and undo. Add tabs,
  split views, multi-selection, drag-and-drop, clipboard file operations,
  previews, metadata, operating-system open/reveal, watching, and durable grant
  restoration only as complete production slices.
  Replace development `--host-cap-dir` provisioning with trusted native/portal
  Open Project selection for interactive use, record grant ancestry, define a
  revocation linearization point for roots and derived children, and verify
  denial outside the grant and revocation during queued work through the real
  GPUI/trusted-chooser boundary.

- [ ] **Music library metadata, persistence, and media integration.** The music
  player foundation provides explicit folder/output capabilities, Rodio and
  Symphonia decoding, a bounded playback state machine, queue navigation,
  seeking, stale-load suppression, corrupt-media isolation, and a virtualized
  ordinary-use library. Add metadata and artwork extraction, durable roots and
  playlists, filesystem reconciliation, volume and repeat policy, automatic
  end-of-track queue advancement, device-loss recovery, and operating-system
  media controls as complete production slices.

- [ ] **Animation Studio project assets and export.** The editor proves native
  retained vector painting, captured direct manipulation, state-owned undo/redo,
  position keyframes, scrubbing, and cancellable playback. Add capability-scoped
  project save/open, image assets, text, grouping, easing, and deterministic
  frame-sequence export with cancellation before presenting it as a complete
  presentation authoring tool.

- [ ] **Clipboard image formats, durable pins, and global activation.** The
  clipboard-history slice provides explicitly granted, bounded text capture,
  privacy exclusion, restore, cancellation, stale suppression, virtualization,
  and content-free semantic evidence. Add bounded image representations,
  encrypted durable pinned entries, compositor-level change notifications, and
  a globally activated overlay with focus restoration as complete production
  slices before presenting it as a full desktop clipboard manager.

- [ ] **Redis mutation, authentication, and cluster operation.** The Redis
  Explorer foundation exercises an exact-endpoint TCP grant, `roc-redis`,
  bounded incremental SCAN, native type and TTL discovery, and read-only
  inspection for strings, lists, sets, hashes, and sorted sets. Add credential
  capabilities, database selection, cluster redirection policy, optimistic
  mutation with server confirmation, destructive confirmation, expiry edits,
  reconnection, and cancellation as complete slices before presenting it as a
  general Redis administration tool. Credentials must never enter captures or
  ordinary persisted application state.

- [ ] **SQLite write transactions.** The database capability is deliberately
  read-only; it binds parameters and pages results, but cannot write. Add a
  separately granted read-write capability, cancellation, transactions,
  editable grids, and export with lifecycle and resource counters before
  presenting the example as a general database administration tool.

- [ ] **System Monitor charts and export.** The system-monitor slice has a real
  capability-scoped `sysinfo` sampler, explicit unavailable values, bounded
  history, sorting/filtering/selection, and a virtualized process table. Add
  canvas time-series charts and a separately granted privacy-safe export whose
  schema excludes process names and IDs before offering session export.

- [ ] **System Monitor platform breadth.** Validate the sampler and unavailable
  classifications on macOS and Windows, and add per-disk/per-interface identity
  only with explicit privacy policy and deterministic evidence.

- [ ] **Image-library trusted Open and capability lineage.** Development and
  automation provisioning enters the ordinary grant registry, but it is not
  trusted chooser consent. Add a platform-owned Open broker with ancestry and
  revocation semantics before describing interactive folder selection as a
  user grant.

- [ ] **Image-library cancellation and decoded-cache ownership.** Folder scans
  suppress stale task completions, but bounded Files reads do not yet expose
  cooperative cancellation and GPUI does not expose decoded-byte eviction.
  Add those production seams and owner counters before retaining much larger
  raster collections.

- [ ] **Image-library metadata and editing breadth.** Add EXIF orientation,
  color-profile and animation metadata plus production zoom, pan, rotate, crop,
  undo and slideshow primitives. Do not infer these values from filenames or
  add controls that bypass `ImageProps`.

- [ ] **Image-library export broker.** Add a trusted Save/Export broker with a
  separately selected writable grant, collision policy and revocation. The
  existing development directory provision is read-only and must not be used
  as implicit export authority.

- [ ] **HTTP cancellation and streaming.** The bounded
  asynchronous HTTP foundation supports explicit scheme, redirect, timeout,
  header, request-body, and response-body policy, and the workbench suppresses
  stale completions. Add a typed request handle with cooperative transport
  cancellation and bounded streamed upload/download progress before
  applications depend on either.

- [ ] **HTTP Workbench advanced document tools.** Add syntax-highlighted JSON
  and text response modes, cURL and collection import/export, and resizable
  split panes through `Gui.split` between the request and the response. Preserve request
  meaning and redact authentication material in every persisted or exported
  representation.

- [ ] **HTTP Workbench collections and structured validation.** Add bounded
  non-secret request history and named collections through `AppData`, excluding
  authorization, cookie, and proxy-authorization values by construction. Add
  structured JSON validation and multiple header/query rows with field-owned
  diagnostics before advertising environment or authentication editors.

## Device Configurator follow-on features

- [ ] **A device is granted by a command-line flag, not by choosing one.**
  The grant now records that honestly — `device.rs` names its origin
  `Origin::Provisioned` in one constant that says what would change it — but
  recording it is not fixing it.
  `--host-cap-device virtual|VID:PID` is the only authority path: `device.rs`
  reads one `configured` grant at process start and `Device.acquire!()` answers
  `AccessDenied` forever if there is none. Issue #1's policy row for USB/device
  services requires trusted device/function selection, and that issue states
  plainly that a development provisioning flag must not masquerade as an
  interactive chooser. So the flag is honest only while it is visibly
  development provisioning, which is what the window now says. Close this with a
  host-owned device picker whose selection is the grant, naming one device and
  no more, with ancestry, lifetime until disconnect, explicit remembered access,
  and revocation — the same broker shape the file entries above describe.
  Implementing device services is outside issue #1; the policy it states is not.

  Until then a person who launches the example without the flag can only be told
  what happened. Pressing Discover once is refused, and the control is then
  withheld rather than left to be pressed for the same answer, because the grant
  cannot change while the window is open. That is honest, not adequate.

- [ ] Add hot-plug notifications and reconnect policy to the host-owned HID
  connection lifecycle, preserving stale-completion suppression in the app.

- [ ] Add persistent named mapping profiles and per-control remapping once the
  protocol represents those fields; retain atomic acknowledged apply.

- [ ] Add a signed, integrity-checked firmware-update protocol with explicit
  cancellable and non-cancellable phases before exposing firmware controls.

- [ ] Validate physical HID behavior on macOS and Windows and add target-specific
  `hidapi` backends before advertising those hosts as supported.

## Terminal workspace follow-on features

- [ ] Propagate live pane dimensions through the layout owner to
  `Process.Pty.resize!` and specify the resulting PTY size without exposing a
  fixed-size product control.

- [ ] Add ANSI/VT cell parsing, wide and combining glyph layout, selection,
  clipboard policy, and URL recognition on top of the ordered PTY byte stream.

- [ ] Add tabs, nested split panes, focus navigation, pane zoom, and persisted
  workspace layouts using the existing mounted graph and event route. The two
  workspaces share one resizable, foldable divider (`Gui.split`); `Gui.tabs`
  and nested splits are the primitives the rest would use.

- [ ] Add user-configurable shell-profile grants without exposing executable or
  environment selection as ambient application authority.

## Observatory example

- [ ] **Run the Windows changes on Linux and macOS.** A dialog whose opener is
  gone now returns focus to the window, SQLite opens files sharing delete on
  Windows only, the Observatory fixture takes its contended run from the
  first build's executable, System Monitor's readings shrink rather than
  widening the page, and the window runner starts its pointer outside the
  window and restores it after a resize rather than taking the system
  cursor's position. Run the full suite on Linux and macOS.

- [ ] **Publish link inputs that declare CoreServices.** macOS watching uses
  File System Events, so `dependencies/macos-interfaces/interfaces.json` now
  catalogues CoreServices, and `platform/main.roc` links its interface.
  `build.py --source-inputs` generates it; the locked link-input release in
  `link-inputs.lock.json` predates it, so a default build lacks
  `CoreServices.tbd`. Produce and lock a new release.

- [ ] **A flat scaling result reads as "sub-linear".** When every step ratio of
  a trigger and metric lies within the A/A noise band of 1, Scaling reports
  `sub-linear`, which is true but hides the stronger finding that the cost did
  not grow with the workload (as for Database Browser's on-demand rows). Report
  `constant within noise` for that case.

- [ ] **The long-capture case stops at 10,000 cycles and records no frames
  (US-40).** `scale-session.scm` opens one generated 10,000-cycle Database
  Browser session and jumps through its cycle list, and `window-session.scm`
  scrolls it in the window, but the session runs on the semantic runner, so
  its capture has no `gpui_frames` rows, and at about 5 ms a cycle a
  100,000-cycle session would take eight minutes to generate. A window session
  is now recorded unattended (`window/database-browser-frames.rgstats`, at
  least 1,000 frames, which `frames-scale.scm` opens and zooms), but a window
  session occupies the person's screen while it runs and draws about three
  frames per scroll at the display's rate, so 100,000 frames would hold the
  screen for many minutes and exceed the window runner's 600-second watchdog. US-40 asks for 100,000 cycles and 100,000 frames in one
  capture; it needs a window session split across the watchdog, or a watchdog
  that measures progress rather than elapsed time.

- [ ] **Two honest-absence paths are reached only by unit expectations.** No
  fixture capture has a cycle with `roc_work_valid = 0` or
  `component_work_recorded = 0`, so the inspector's `—` for invalid spans and
  unobserved component work is proved by `expect` on `Capture.decompose` and
  `Capture.work_count`, not by a specification. A real application path that
  produces such a cycle (a rejected turn, or a callback whose span stack does
  not close) should become a fixture.

- [ ] **A folder cannot be dropped (US-4).** A dropped folder is refused as
  `NotFile`. W0's "drop .rgstats files anywhere" covers files; dropping a
  benchmark output folder to list it is the folder counterpart, and needs a
  drop target that declares it accepts folders and an event that grants a
  `Gui.FilesDirRead`.

- [ ] **No application reads a chosen file's bytes.** `Files.File.Read.read!`
  shares its bounded, no-follow read with `Dir.Read.read!` and is covered by
  host tests, but Observatory opens its file through SQLite only, so
  `expect-document-counters` has never seen a read. File Explorer's preview is
  the natural adopter: an "Open file…" that previews one chosen file.

- [ ] **The native file panel does not filter by type on macOS.** GPUI's
  `PathPromptOptions` has no allowed-types field, so `pick_file!` shows every
  file there and the host refuses a wrong type after the choice with
  `PickFileErr(Unsupported)`. Add allowed content types to the vendored
  `NSOpenPanel` prompt. The Linux portal filter and both `pick_file!` choosers
  are exercised only through `--host-cap-file`; certify them with a person
  choosing, as for Open Project.

- [ ] **SQLite cannot join two databases (P7).** Databases
  open in place, read a live write-ahead log, bind parameters, and page past
  the row limit. Observatory compares captures through a connection each and
  joins their rows in Roc, which serves a baseline and a scaling set; a query
  that must join two captures in one statement still needs a
  capability-scoped `ATTACH` of a second granted database (plain `ATTACH` is
  refused, because it names a path). Opening in place derives the directory's path from
  its descriptor on Linux, macOS, and Windows; only the Linux path has been
  exercised, so verify macOS and Windows, including a verbatim `\\?\UNC` share,
  which is refused.


- [ ] **Tabs cannot be reordered (P5).** `Gui.tabs` selects and closes tabs
  by pointer and keyboard, but a tab cannot be dragged to another place in its
  strip, and there is no keyboard chord to move one. Add a reorder request the
  application owns, carried by a pointer drag over the strip and a chord,
  with a specification on both runners.

- [ ] **A split's size is bounded by the application, not by the window
  (P5).** A divider asks for sizes within the split's `min` and `max`; when the
  window is narrower than `max` allows, a drag can still ask for a size that
  leaves the other pane nothing. The host knows the split's own extent when it
  lays it out; clamp a drag to it as well, and say so in the event.

- [ ] **A capture being recorded is not watched while its tab is parked
  (P5).** Observatory watches only the capture on screen. A capture still
  being recorded that is left in another tab is read again, and watched again,
  when it comes back, so its tab says nothing of the rows written meanwhile.
  Keep a watch per open capture, bounded in number, and mark a parked tab that
  has grown.

- [ ] **Copy covers six tables (US-37).** The triggers, cycles, waterfall,
  allocations by trigger, steps, and measurement families tables copy their
  rows as Markdown with each value's family, status, and reason. The Overview
  tiles, the inspector's component work, graph work, and span allocations, the
  run lifecycle and process resources, the Frames and Timeline tables, and the
  Compare and Scaling sheets have no Copy button. Give each one, building its
  Markdown from the rows it draws, with a specification that copies it.

- [ ] **The palette finds no frame or source line (US-35).** `cycle N` and
  `step N` name a cycle and a step of the selected run; `frame N` and `line N`
  find nothing. Add both, reading the frame by ordinal and opening its work in
  Frames, and showing the step at a source line in Spec.

- [ ] **Compare and Scaling draw an absent value as plain text (US-7).** Their
  `—` cells come from `Widgets.roc` and carry their reason in a neighbouring
  column, but neither shows it on hover nor opens Health at the family. Draw
  them with the same pressable, hoverable dash the other views use.

- [ ] **A baseline applies to three views, and no chart overlays it (US-32).**
  The triggers table, the cycle inspector, and Memory's allocations by trigger
  gain Δ, ratio, and noise. The Overview tiles, the cycle list's bars, the run
  lifecycle and process resources, and the Spec step durations show no delta,
  and no chart draws the baseline in a secondary style. Each needs a baseline
  value joined to its row (runs and steps have no key shared across captures
  beyond phase and ordinal) and, for charts, a second series drawn in a
  secondary style.

- [ ] **An A/A bound is the spread of one pair.** Compare and Scaling bound
  noise by how far one A/A capture's value lies from its reference's. A single
  pair understates the spread about half the time; several A/A captures, or
  the samples within each, would give a bound with a stated coverage. Timing
  noise marks therefore vary from run to run, and the specifications assert
  them only for allocations, which repeat exactly.

- [ ] **The Compare and Scaling views draw with `Widgets.roc`, the other views
  with View.roc's own copies.** `Widgets.roc` holds the cells, rows, headings,
  and keys the new views need, drawn identically. Fold View.roc's copies onto
  it once the Frames view that is being added to View.roc has landed, so the
  two are not edited concurrently.

- [ ] **Canvas text, hover, and wheel have run only on Linux.** Text is shaped
  through GPUI's text system and hover and wheel arrive through GPUI's mouse
  events, so nothing in the host is platform-specific, but `window-frames.scm`
  and the host's live canvas tests have run only on Linux (Wayland). Run them
  on macOS and Windows, where a trackpad reports pixel deltas and a wheel
  reports lines.

- [ ] **A generated window session occasionally stalls.** Observatory's
  fixture scrolls the Database Browser's ten thousand rows a few hundred times
  in a real window. Twice in development the run stopped drawing and reached
  the host watchdog with its last milestone `driver-started`, while the same
  session passed in about thirty seconds on other runs. The generator now caps
  the run at ninety seconds and retries once. Find the step that waits: the
  window report is written only after the driver finishes, so the watchdog
  exits before a stalled step is reported. Both attempts also stalled in the
  Windows scaling job of CI run `36482945498`. Bound frame waits and preserve
  the failing step's report before diagnosing the frame scheduling defect;
  another retry or a larger timeout does not establish its cause.

- [ ] **The frame strip draws one run's frames as one sequence.** Frames number
  in run and ordinal order across every run of a capture, so a capture of
  several window runs draws them end to end with no mark where one run ends.
  No fixture has more than one window run; when one does, draw a rule and a
  caption at each run's first column.

- [ ] **A finalised capture chosen as one file is not watched.** Observatory
  watches the folder it lists, and a capture still being recorded, but not a
  finalised capture opened from a single file grant, so replacing that file
  shows no "Capture changed" until it is opened again. Closing or replacing
  the capture now cancels its watch without a completion, so watching one
  opened from a file no longer disturbs a specification awaiting its next task;
  what remains is the watch itself, and the grant readouts and counters of the
  specifications that open a single file.

- [ ] **A growing capture's Timeline keeps its last reading.** While a capture
  being recorded is read again, the capture, its tables, its lists, and its
  frame strip follow each commit, but the Timeline keeps the span it last read
  until it is shown again, and the frame strip returns to every frame, losing
  its zoom. Read the Timeline's span again, and the strip's, with the rest.

- [ ] **The appearance is observed only on Linux.** macOS and Windows hosts
  report a light scheme with full motion whatever the desktop asks, so adaptive
  colours never turn dark there unless the application prefers dark. Read
  GPUI's window appearance, and the platform's reduced-motion setting, through
  the same `appearance` owner.

- [ ] **The platform's own colours are not adaptive.** The host's window ground
  and control defaults, the `Elem` control defaults, and the access panel are
  one dark palette whatever the scheme. Give each an adaptive pair.

- [ ] **Appearance changes are not counted.** No counter records how many times
  the system's appearance changed or the application chose a scheme, so a
  specification can assert the resolved scheme but not how it got there. Add
  them to the `appearance` owner with an assertion step.

- [ ] **No example waits on the system appearance.** `Gui.Appearance.current!`
  and `next_change!` are exercised by the host's tests alone: Observatory
  follows the scheme through adaptive colours and never reads it. Give an
  example a reason to, such as honouring reduced motion, with its specification.

- [ ] **Observatory forgets its theme.** A scheme chosen in the palette lasts
  until the window closes. Remember it in application data and choose it again
  at startup.

- [ ] **No specification presses a frame on the Timeline itself.** A
  `click` on a canvas-item now presses a mark by its label, and list passes are
  named by their order on the clock, but a frame mark is the costliest frame of
  its column, and which frame that is follows the capture's timing, which
  changes each time the fixture is regenerated. `timeline-cause.scm` therefore
  still presses the frame in the Frames strip. Name the frame marks, or choose
  the fixture's frames, so a known frame is a mark of its own.

- [ ] **Component work is not attributed to components (E5).** Component work
  is a per-cycle total. Define a stable, non-textual component identity that
  satisfies the capture privacy rules, as `cycles.target_identity` does for a
  cycle's target, and record work per component.

## Trust: measurements that can mislead a decision

- [ ] **Memoization measurements do not isolate every ownership or equality
  cost.** The textarea append and same-length late-edit ladders exercise large
  edited children with explicit equality and without memoization. Equal,
  independently allocated inputs remain a separate comparison case. Live
  snapshot retention and copying attributable specifically to lost uniqueness
  remain unmeasured: allocator requests are not retained bytes or a copy counter.
  Measure these through their production owners before making those claims.

- [ ] **General GPUI entity lifecycle counts are not captured.** The virtual
  list reports viewport-owned entity materialisation, retention, and recycling,
  but eager native views do not yet emit general materialised, rebound, and
  retired entity counts. Direct native identity tests prove reuse semantics;
  schema-11 component and mounted-node counts do not measure native entity
  construction or rebinding. Add owner-populated counters and then their schema,
  queries, and production-window assertions together, without inferring them
  from graph retention or a timer.

- [ ] **Rows drawn before they are mounted are not counted.** A list of rows
  produced on demand draws a blank place for a visible row it has not yet
  mounted, for the frames until its viewport turn lands. `virtual_list_frames`
  counts those rows among `visible_items` but has no column saying how many of
  them were blank, so a capture cannot show how often a fast scroll outran the
  list. Add an owner-populated column at the next schema version, together with
  the Observatory and `analyze_stats.py`, which gate on schema 25.

- [ ] **Window benchmark warmup and sample orchestration.** Real-window
  hover-grid runs can record schema-14 captures containing native frames and
  live task completions. The specification runner still runs a single window
  lifecycle: `spec::check_runner` refuses benchmark steps there. Add production
  window orchestration for warmups, samples, iterations, and per-sample reset,
  then route those captures through the existing scaling and A/A reports.

- [ ] **The allocation counters are inside the spans they attribute.**
  `roc_alloc` calls `observatory::note_roc_alloc` before allocating, which loads
  `ENABLED`, adds to two atomics, then enters a thread-local and takes a
  `RefCell` borrow (`crates/host/src/observatory.rs:444-560`); `roc_dealloc`
  pays the same and then its routing. At the 3,008,082 allocation calls the
  100,000-row sparse update records, that is a per-allocation tax inside the
  very span whose share of the callback the performance plan reasons from. A/B
  comparisons survive it because both sides carry it; attribution does not.
  Size the tax with an `ENABLED`-off run timed externally, and either subtract it
  from the cost model or move the counters to per-thread cells flushed at span
  end. Until then, treat owner-span *shares* as diagnostic, not as attribution.

## Performance findings from the suite

Defects in the platform or host that the benchmark suite has exposed. Each
names the evidence so a fix can be verified against the same case.

- [ ] **Explain development-backend local callback timing growth.** Final
  schema-15 same-executable A/A row-boundary runs preserve one boundary render,
  one registry lookup, one ancestor invalidation, and three getter/one setter
  calls for unmemoized local edits at 100, 1,000, and 10,000 rows. The first
  run's callback medians nevertheless rise from 62.35 to 107.50 to 282.14 us;
  its repeat records 65.93, 108.65, and 281.35 us. Routing, application update,
  application render, and platform lowering owner spans all increase. Render
  allocation requests remain 9,880 bytes; update requests are 5,440, 5,656,
  and 5,872 bytes. Profile the remaining work before attributing the increase
  to traversal, allocation, cache behavior, or any other unmeasured mechanism.
  Bounded render/projection counts do not establish constant callback time.
  Preserve the explicit development-backend qualification and compare only
  compatible builds. Evidence: `target/adapter-cps-production/report.md`.

- [ ] **Audit native layout and arbitrary application recursion separately.**
  Host entity lifecycle walks are iterative. GPUI's element layout/paint
  calls, application render functions, and arbitrary callback closures have
  separate stack behavior. Measure and constrain those owners before claiming
  unrestricted native or application depth. A headless structural-depth result
  does not prove native layout stack safety.

- [ ] **Reuse intrinsic and flexible native container subtrees.** Fixed-size
  non-root rows, columns, and panels can cache their native subtree because
  their exact outer dimensions do not require measuring children. Intrinsic
  and flexible containers still build their contents for layout. Extend reuse
  with a layout contract that preserves content sizing, flex distribution,
  inherited styles, clipping, input, and descendant invalidation. Verify the
  production native render and element-construction counters independently;
  do not force application geometry merely to make a cache eligible.

- [ ] **Exact native render contracts need native invalidation attribution.**
  Roc patches supply the changed and retained frontier, and production native
  counters can check patch-derived expectations in controlled GPUI tests.
  Arbitrary interactive frames also include focus, pointer styling, geometry,
  inherited styles, and GPUI refreshes. GPUI keeps its dirty-view set and
  refreshing flag private, so the host cannot classify every native render
  cause. Expose those causes before treating every render outside a Roc patch
  as a production invariant violation. Keep actual counters always available;
  neither silently exempt unexplained work nor claim an unconditional contract
  from the controlled tests.

- [ ] **Reduce GPUI scene reuse and reconstruction work as the scene grows.**
  The schema-14 native hover baseline recorded 210 completed frames and exactly
  100 enter, 100 exit, and 100 task-completion cycles. Host-owned mean frame
  spans were 8.041 ms layout request, 21.876 ms prepaint, and 49.403 ms paint;
  steady frames constructed 10,000 boundary wrappers. Fixed-container subtree
  reuse addresses wrapper construction, but scene replay and reconstruction
  can still traverse retained scene data. Profile the changed production path
  and compare owner spans and native counts before attributing remaining cost.
  These timings are report-only; they do not measure retained memory or bytes
  copied, and the baseline does not establish post-change work.

  Close this gap by retaining native subtree records across frames, not merely
  suppressing `NodeView::render`. The production owners are
  the GPUI fork's `crates/gpui/src/view.rs` (cached subtree lifetime), `window.rs` (frame records,
  replay ranges, transactional prepaint, hitboxes and listener ownership),
  `scene.rs` (primitive insertion, overlap order and batching),
  `key_dispatch.rs`, `tab_stop.rs`, `text_system/line_layout.rs`, and the WGPU,
  Metal and DirectX renderers. `crates/host/src/lib.rs` supplies the mounted
  change frontier and descendant notifications; it must not build a second
  scene or event implementation.

  A candidate design uses persistent subtree segments with stable handles and
  ordered child references. Retain scene commands, interaction records, focus
  paths, element state and text resources under the same segment lifetime;
  replace only changed segments and their ancestor links. Preserve stacking and
  overlap order, clipping, inherited text, focus/tab order, moved children,
  handler revisions, modal input policy and removal. Mutable callback ownership
  and resource retirement must remain valid while prior frames still reference
  a segment. Aborted prepaint transactions must publish nothing. Flattening
  segments into the existing full-frame vectors at presentation would only move
  the global work, so renderer submission and retained buffers or damage-based
  presentation belong to the design, with each platform's buffer-age rules
  verified separately.

  Add production-owner deterministic counts before judging this change:
  scene operations replayed, primitive insertions, hitbox slots copied, listener
  slots transferred, dispatch nodes reconstructed, tab operations replayed and
  element-state entries visited. Range lengths permit one increment per replay
  batch; distinguish slots visited from callbacks invoked and operations replayed
  from primitives actually emitted. These counts are unmeasured and unavailable
  until their owners populate them; do not add empty schema columns or derive
  them from render counts. Include a schema increment and reporting tests when
  measurement lands.

  Acceptance uses the actual hover-grid application and mounted patches at
  100, 1,000 and 10,000 cells, with viewport, tree depth and affected-cell count
  controlled. Once initial construction is excluded, one local hover update or
  delayed completion must not visit, copy, rebuild or submit unrelated retained
  records in proportion to total cell count. Vary depth separately and account
  for the changed ancestor path. Include same-color updates, idle frames,
  reorder/removal, clipping/resize, overlapping surfaces, focus, window exit,
  stale callbacks and transaction retries. Gate deterministic owner work and
  semantic results; report timing and A/A noise separately. A reduced wrapper
  count alone does not close this entry.

- [ ] **Dense native hover still traverses GPUI input structures globally.**
  A user-driven 10,000-button hover-grid profile, excluding its first two seconds,
  recorded 4,456 user-CPU samples: about 19% in GPUI mouse-listener wrappers,
  4.5% in frame hit testing, and 5% in bounds-tree insertion. This exploratory
  run overlapped other work and had incomplete Rust stack unwinding; these are
  exclusive sample shares, not latency measurements or caller attribution.
  GPUI dispatch routes free pointer motion by hit path but delivers every other
  event to the whole frame listener list, and hit testing scans hitboxes. A spatial hit-test index alone would
  leave listener traversal. Profile native input separately from frame work,
  preserving hover exit, capture, stacking, clipping, drag, and removal semantics
  before changing dispatch further. Use retained ordered interaction segments
  and a spatial candidate index together; separately retain capture/outside
  listeners and the previously hovered path so exit delivery survives moving
  away or leaving the window. A native mouse event must visit only relevant
  candidates, ancestor routes and explicitly global handlers rather than every
  unrelated control. Owner counts of hitboxes examined and listeners actually
  invoked must follow real early exits and propagation stops; they remain
  unavailable until instrumented. Apply the controlled-dimension scaling and
  lifecycle acceptance cases in the scene-retention entry above.

  Ordered listener routing now partitions handlers by event type and routes
  GPUI-owned hover, focus, hover-style, click, and drag handlers through the
  current, previous, and pressed hit paths. Explicitly global user capture
  handlers retain the original capture and bubble contract. In a 10,000-cell
  mixed hover/click profile, `dispatch_event` and mouse-listener closures fell
  below the 0.1% report threshold after previously accounting for 17.38% and
  15.40% respectively. The 31,139-sample follow-up lost no samples, but remains
  exploratory CPU sampling rather than latency evidence. Frame hit testing was
  still 2.08%, and deterministic owner counts remain unavailable, so this item
  stays open for spatial indexing and production measurement.

- [ ] **Timer waits occupy the generic task workers and extend hover trails under load.**
  The hover-grid application schedules a 200 ms Timer wait per exiting cell.
  Those waits start inside the existing 4–16 blocking workers; additional jobs
  wait in an unbounded queue. Reset latency includes queue delay as well as the
  requested interval, and queued closures retain resources. The 32-cell burst
  case exposes this through production tasks. Add deadline-aware nonblocking
  timer delivery or equivalent bounded scheduling without global redraws,
  preserve boundary ownership and stale-completion suppression, and measure
  queue depth and delay at their production owner before making latency claims.

- [ ] **Every Roc free takes a mutex for each resource kind the application has
  used.** `roc_dealloc` checks the routing bitmask and then calls each active
  domain's `route_dealloc` (`crates/host/src/lib.rs:337-380`), and each of those
  locks its store — `files::route_dealloc` opens with `store().lock()`
  (`crates/host/src/files.rs:259`) before the empty-map early-out. The bitmask
  removes the cost only for a domain that has never been used, so an application
  holding audio, files and assets pays three uncontended lock/unlock pairs and
  three hash lookups on a path that fires millions of times per full-root frame.
  Resource handles are a small known population: give them a distinguishable
  allocation region and range-check the pointer, or one lock-free membership
  structure, rather than twelve mutexed maps. Measure at the allocator owner
  before and after; the counters must not change.

- [ ] **Persistent-index maintenance retains a high allocation constant.**
  Bounded route-ID chunks removed the superlinear ownership-list allocation
  term. Compact leaves and element updates further reduced the constant: a
  10k memoized ancestor selection makes 399,333 measured allocation calls,
  and the existing 100k full-root sparse update makes 3,008,082.
  Investigate indexed maintenance and reference-count
  overhead without weakening revision checks or atomic graph/session acceptance.
  See PR #23 for the measured optimization history and rejected follow-ups.
  Timing alone must not gate correctness.

- [ ] **Investigate remaining intentional full-root scaling.** Ordinary `List`
  columns intentionally retain full-root semantics; keyed columns provide the
  proportional structural alternative. A front insertion can still change the
  geometry of every following row. Keep layout, prepaint, paint, and scene
  retention as separately owned work, and do not attribute those frame costs
  to keyed graph reconciliation.

  A serial development-backend comparison against `origin/main` at `d0a98ce`,
  using byte-identical applications and specifications, the same pinned
  compiler, isolated jobs, and A/A repeats, exposed a generated-frame bug in
  the explicit lowering traversal. Large work items and recursive trampoline
  values were stored inline and the traversal resumed once per item; the
  10,000-row replacement therefore spent about 729 ms in lowering. Boxing the
  large ownership boundaries and processing a bounded batch per continuation
  reduced its callback from 773–785 ms initially to 163.93–164.76 ms, versus
  50.60–50.76 ms on main. Styled-checkbox selection is now 65.36–66.05 ms
  versus 16.43–16.59 ms; loading the unchanged 10,000-item virtual list is
  61.52–61.93 ms versus 15.17–15.41 ms. In contrast, moving one canvas layer is
  170–173 us versus 422–446 us, and an idempotent 10,000-row reselect is 47–48
  us versus 2.63–2.66 ms. The catastrophic 12–32x regression is fixed, but
  ordinary full-root reconstruction remains 3–4x slower and still allocates
  traversal/continuation state per node. Attribute and remove that residual
  cost without trading away stack safety or the bounded local path.

  Disassembly of the controlled 10,000-row development-backend executable
  shows each specialized lowering procedure still reserves about 752 KiB of
  stack and several specializations contain about 1.46 MiB of generated text.
  Moving the visited element into a boxed one-field record did not materially
  change either generated size and made a 1,000-row capture slower. Boxing all
  container-close payloads reduced measured lowering allocation bytes at 10k
  from about 82.20 MB to 58.35 MB per cycle, but added 10,003 allocation calls
  and repeatably slowed lowering from 118.77–118.98 ms to 122.67–122.79 ms.
  Both representation experiments were rejected. Continue by attributing the
  generated frame rather than adding indirection based on aggregate bytes.

  2026-09-18: attributed. The development backend never reuses stack slots
  (`allocStack` in `src/backend/dev/*/CodeGen.zig` only grows), so frame size
  tracks total temporaries: twelve ~3 MiB specializations with ~794 KiB
  page-probed frames at the pinned nightly, ~927 KiB text and ~250 KiB frames
  at compiler `main` `5982c9b2`, holding ~60% of on-CPU callback time.
  Reported upstream as roc-lang/roc#11448. The same source at the same head
  commit built with `--opt=speed` runs the 10k select callback in 197.4 ms
  against 721.5 ms, so the pin upgrade plus the LLVM backend recovers most of
  this entry once the upgrade blocker below is fixed. `wip/performance.md`
  carries the measurement detail.

  These semantic captures contain no GPUI frame work, and `origin/main` has no
  keyed-collection analogue, so they neither compare native rendering nor
  establish an A/B result for keyed insert, move, or removal.

  Historical serial schema-11 captures passed all four sparse-update scales
  and A/A repeats with the compiler/backend used for that checkpoint. The
  10k to 100k median grew from 60.863 ms to 902.451 ms; callback, validation,
  and graph-apply means grew
  14.1x, 16.6x, and 14.3x, respectively. Marked Roc allocation bytes grew
  10.8x. These owner measurements do not establish the cause of time growth.
  Investigate without weakening tree integrity or exact patch counters.
  The pre-component production 100,000-row sparse-update case showed superlinear
  work after dense validation, host-owned child streaming, and consolidation of mounted node
  and parent storage. In a serial same-executable run, 10,000 to 100,000 rows
  grew from 9.47 ms to 139 ms overall. Roc callback work grew 11.4x, validation
  19.0x, and graph apply 20.2x; both lifecycle and measured-span allocated
  bytes grew 10.0x. Further work must preserve the generic tree-integrity
  checks and exact patch counters. The full-root rebuild itself is intentional
  application semantics, with row boundaries providing the local-update
  alternative. These numbers are a historical baseline, not evidence for the
  final schema-15 implementation. Continue using serial same-executable captures
  with the pinned compiler, explicit backend, and schema-15 owner counters.
  Do not compare timings across the historical LLVM and development-backend
  checkpoints. Separate application keyed lookup, Roc comparison and rendering, fresh/frontier validation, and native
  materialisation before assigning the remaining growth to an owner.

- [ ] **Measure native text shaping and deep layout separately from headless work.**
  Text and tree-shape semantic cases measure construction, callback work,
  allocations, patch sizes, and lifecycle behavior. Schema-15 projection
  counters and reduced-stack tree cases additionally verify composed state
  adaptation, deep ownership, task resolution, veto, and teardown. These are
  useful headless measurements; they do not measure GPUI text shaping,
  wrapping, layout, or paint. Historical headless captures showed under 15%
  timing difference between long and short messages at 10,000 rows and no
  observed depth effect in that workload. Those observations do not establish
  native text or depth costs. Add controlled production-window scale ladders
  for text length, width, wrapping, and tree depth, and report owner frame spans
  and native-work counts. Isolate text shaping with a production-owner
  measurement before attributing a whole layout or paint span to shaping.

## Compiler and toolchain defects

- [ ] **Cached builds are not byte-identical to uncached ones.** With
  `nightly-2026-09-23-c7852fd` the build cache miscompiled: building
  `examples/clipboard-history` with the cache panicked (`instantiation widened
  a closed tag union`), and `examples/http-workbench` built in a cache another
  application had populated drew a wrong view (roc-lang/roc#11678, still open
  upstream). On `nightly-2026-10-20-7a8a800` neither reproduces: every example
  builds through one shared cache, cold and warm, and the full specification
  suite (Observatory aside) passes with cached builds except two Linux window
  specifications that fail identically uncached. But a cached executable
  differs from the uncached one (Counter is 6 KB smaller), while two
  `--no-cache` builds are byte-identical. Captures compare executables by
  hash, so the specification runner keeps `--no-cache`. Report the
  nondeterminism on roc-lang/roc#11678 with this evidence, and drop
  `--no-cache` once cached and uncached builds agree byte for byte.

- [ ] **A Windows link is not reproducible.** Two `roc build` runs of the same
  source differ in the PE header's `TimeDateStamp` and in one later field, so
  `executable_hash` differs between builds of one application, and an A/A
  pair must share one build rather than one source. Linux and macOS links are
  byte-identical. The Roc compiler's COFF link needs a deterministic
  timestamp (`/Brepro` or a fixed `/timestamp`). Not re-tested on
  `nightly-2026-10-20-7a8a800`; it needs a Windows machine.

- [ ] **RELEASE BLOCKER: the default backend does not finish building
  Observatory.** On `nightly-2026-10-23-18478ff`, `roc build --opt=speed
  --no-cache examples/observatory/main.roc` on Linux crashes the compiler
  with a segmentation fault after 9.1 s wall time at 1.43 GiB peak RSS, in
  `post-check lambda_solve` on the main thread, before any executable is
  written; the same nightly's `--opt=dev` build and `roc check`/`roc test`
  of Observatory pass. Earlier nightlies failed differently: on
  `nightly-2026-10-20-7a8a800` the build was killed after 17 minutes of CPU
  at 6.9 GB resident. On Linux, `nightly-2026-10-21-5349569` with
  `--no-cache --opt=speed`, after explicitly typing the themes' `face` as `Gui.FontFace`,
  was killed by signal 9 after 37.69 s wall time at 25,582,912 KiB peak RSS
  (24.4 GiB), without producing an executable. Its `--opt=dev` build, with
  the font-face annotations and dialog focus repair, passes all 79 enabled
  specifications on Linux (64 semantic and 15 window) with regenerated
  fixtures; the separately invoked folder-rewatch specification passes
  locally too.
  `nightly-2026-09-27-a3ce7f1` built it in 16 s and
  `nightly-2026-09-28-9927ba8` in 21 min 45 s; on those nightlies the result
  segfaulted as a capture opened (roc-lang/roc#11830, since closed). `--opt=dev`
  builds it in 11 s and every specification passes. The specification runner
  skips Observatory under `--roc-opt speed` (`COMPILER_BLOCKED` in
  `scripts/run_specs.py`). Reduce the slow build, report it upstream, and
  remove the skip once a nightly builds Observatory with the default backend
  and its specifications pass.

- [ ] **Every application fails ARC certification on Roc `origin/main`.** A
  Debug build of `origin/main` (`c80043e3`), and of the 2026-09-27 nightly's
  own commit `a3ce7f1`, panics building any roc-gui application:
  `ARC: released struct representation is missing exact residual-shell
  metadata` in `Internal.lower_work!`. The certifier runs only in Debug
  compilers, so release nightlies build the same code unchecked; no wrong
  behaviour was observed in them. The platform construct is reading a field of
  a boxed record in a `while` loop, reassigning the box's record in one branch
  of a `match`, then using the field:

  ```roc
  Owner : { key : U64, revision : U64, name : Str }

  lower : List(Bool), { active : Box(Owner) } -> { active : Box(Owner) }
  lower = |flags, boundaries| {
  	var $i = 0
  	var $boundaries = boundaries
  	while $i < flags.len() {
  		match flags.get($i) {
  			Ok(flag) => {
  				revision = (Box.unbox($boundaries.active)).revision
  				match flag {
  					Bool.False => {}
  					Bool.True => {
  						$boundaries = { active: Box.box({ ..Box.unbox($boundaries.active), key: $i }) }
  					}
  				}
  				$i = $i + revision
  			}
  			Err(_) => crash "unreachable"
  		}
  	}
  	$boundaries
  }
  ```

  It needs the loop, both matches, the record wrapping the box, and a
  refcounted field in `Owner`. A Debug build of `main` at `7894793d`
  (2026-10-11) still panics on it inside a basic-cli application. Only a Debug
  compiler checks this, so release nightlies are unaffected; build roc-gui with
  a release compiler. Not filed upstream by choice; a reproduction is drafted
  if that changes.

Defects outside this repository that this repository has to work around. Each
names the reproduction so the workaround can be removed when the fix lands.

- [ ] **Make the default backend the specification runner's default.** The
  LLVM backend's CPS runtime corruption, which produced wrong initial state and
  reference-count failures, is gone: on `nightly-2026-10-20-7a8a800`,
  `--roc-opt speed` passes all 361 semantic specifications of the examples and
  benchmarks other than Observatory. The runner, the guides and the example
  READMEs still use `--opt=dev`, because the default backend does not finish
  building Observatory (the release blocker above). Once it does, make the
  default backend the runner's default and drop `--opt=dev` from the guides.

- [ ] **The Windows development backend drops relocations past a 16-bit count.**
  A compile-time-evaluated top-level value is emitted as initialized data with
  one relocation per pointer it contains. Once one section's relocation count
  exceeds 65,535, the count wraps instead of switching to the extended COFF
  form, and the linker applies only `count % 65536` of them. Every relocation
  the wrap discards leaves its raw addend in place, so a list's element pointer
  reads as its `0x10` header offset and the first reference-count probe
  access-violates with Windows status `0xC0000005` (`3221225477`). Linux and
  macOS builds of the same source are unaffected.

  The boundary is exact and reproducible. An application whose `init` builds an
  `Index` of `n` entries links correctly at `n = 7650` with 83,280 image base
  relocations and faults at `n = 7700`, where the count collapses to 18,218 —
  precisely 65,536 fewer than the expected total. Count an executable's base
  relocations to observe it; a sudden drop as the baked data grows is the
  signature.

  `benchmarks/click-grid`, `benchmarks/hover-grid`, and
  `benchmarks/nested-hover-grid` crossed this boundary by initializing 10,000
  cells, which baked roughly seven megabytes of pre-evaluated state into each
  image. They now start at 100 cells and the four specifications that need the
  dense grid create it explicitly, matching every other case in those suites.
  That keeps the applications well inside the limit — the largest benchmark now
  links roughly 20,000 relocations — but it avoids the defect rather than
  fixing it.

  The compiler fix applies the extended form to `.text`, `.rdata`, and `.pdata`,
  as the DWARF sections already did. With it, `benchmarks/click-grid` links
  102,300 relocations instead of 36,676 and its specifications pass. Restore the
  dense initial grids and remove this entry once a nightly carries that
  change. Not re-tested on `nightly-2026-10-20-7a8a800`; it needs a Windows
  machine.

- [ ] **Generated Roc API pages omit record-field documentation.** Running
  `roc docs platform/main.roc` renders the `Elem.TranslateConfig` type comment
  and signature but omits the doc comments on `key`, `get`, `set`, `on_delegate`,
  and `memo`. A two-field package on `nightly-2026-10-20-7a8a800` still renders
  the record's type comment and drops both field comments. The type-level
  documentation includes the essential contracts so readers can use the
  generated reference. Report it upstream and verify the field descriptions in
  the HTML output once a nightly renders them.

- [ ] **A nominal record cannot be constructed through an alias.**
  `Gui.ColProps.{ ... }` is rejected because the alias is not nominal ("You are
  using the type ColProps like a nominal type, but it is an alias", still on
  `nightly-2026-10-20-7a8a800`), so `Gui` does not re-export the property
  record types: applications pass a bare record literal where a property or
  configuration record with defaults is expected, and lose the name at the
  construction site. A bare record fills its defaults only where the expected
  type reaches it directly: `Rectangle({ ... })` inside a `List.map` closure in
  `benchmarks/animation-canvas` is a type mismatch on the 10-20 nightly (it was
  a compiler segmentation fault on the 09-27 one), which is why
  `Gui.rectangle`, `Gui.ellipse`, and `Gui.line` exist. Report upstream; when
  it resolves, re-export the property records by name and drop the three shape
  constructors.

- [ ] **Let a string literal stand for a text element.** `Elem` can define
  `from_quote` and `from_interpolation` so a child list reads `["Ready", "Rows:
  ${count.to_str()}"]` without `Gui.text`, the way `Gui.Color` takes a
  `0xRRGGBB` literal and `Gui.Key` a quoted one. The compiler crash that kept
  them out is gone on `nightly-2026-10-20-7a8a800`: with `from_quote` on `Elem`,
  Animation Studio, Device Configurator, Review Queue and the text-rows
  benchmark check repeatedly and build with every `Gui.text` around a literal
  removed, and an unannotated helper holding a literal child list checks five
  times out of five and builds with both backends. Add both methods with
  their documentation and drop `Gui.text` around literals.

- [ ] **A record builder only finds `map2` on a module's own type.**
  `{ ... }.Builder` works when `Builder` is imported as a module and fails with
  "does not implement map2" through a `Gui` alias or as a nominal nested in
  `Gui`, on the 09-27 nightly and at compiler `main` `0d00cca8`. Not re-tested
  on `nightly-2026-10-20-7a8a800`. Nothing in the platform is a record builder
  today, so this blocks nothing; it decides where one would have to live if
  joining independent tasks into one record is ever offered. Re-test and
  report upstream.

- [ ] **RELEASE BLOCKER: the compiler intermittently crashes on Windows.**
  `nightly-2026-10-20-7a8a800` died with "Access violation in the Roc
  compiler", fault address 0x5b4, while type-checking `platform/Session.roc`,
  twice in two CI runs: building `examples/terminal-workspace` on compile
  worker 2 (run 39519565767) and `benchmarks/checkboxes` on compile worker 0
  (run 39522990540). Other jobs of the same runs built those applications from
  the same commits, and 80 Linux checks of both never crashed: a race in
  parallel type-checking that the Windows build exposes. Every release test
  builds every application on Windows, so a release fails at random. Loop the
  build on a Windows runner (or with a Debug compiler) for the worker's stack,
  report it upstream, and move to a nightly that fixes it.
  It has since crashed a third and fourth time in CI, building
  `examples/http-workbench` and `examples/counter` (run 39552628536, compile
  worker 3), always at 0x5b4 in `Session`. Yet 160 isolated `roc build
  --no-cache` loops on a Windows runner, of `benchmarks/checkboxes` and
  `examples/http-workbench` with `--jobs=1` and the default, never crashed
  (scratch run 39552608635), so a single worker is not known to avoid it and
  the trigger needs more than one build of one application. Meanwhile
  `scripts/run_specs.py` retries this one crash once on Windows and prints
  `RETRY`; remove that retry with this entry.

- [ ] **`roc test` segfaults on a module whose alias shares its type's name.**
  Observatory's `History.roc` with its `Trail(place)` alias renamed to
  `History(place)`, the name of the module's own type, is reported by
  `roc check` as "The type History is being redeclared", but `roc test` on the
  same file crashes the compiler with a segmentation fault, on
  `nightly-2026-09-27-a3ce7f1` and still on `nightly-2026-10-20-7a8a800`,
  once an `expect` calls one of the module's functions; without the
  expectations it reports the error. A module declaring only the conflicting
  alias reports it too. Reduce it, report it upstream, and remove this entry
  when `roc test` reports the error.

## Runner: test what we fly

- [ ] **RELEASE BLOCKER: Observatory's folder rewatch sometimes counts a
  change.**
  `examples/observatory/specs/folder-rewatch.scm` line 18 expects watch
  counters `[2, 0, 0, 0, _]` and observed `[2, 1, 0, 0, 1]` on the hosted macOS
  runner (CI run 39515606523) and the Linux build job (run 39522990540);
  each passed in other runs and every local run. The specification writes
  nothing, but Observatory summarizes the folder's captures, which are WAL
  databases, after the folder list is shown, and SQLite can create and remove
  `-wal` and `-shm` files beside a database it opens even read-only. Confirm
  whether those transient files are the change, then open captures so that
  they write nothing beside themselves, or exclude SQLite sidecars from the
  watch. The specification is skipped everywhere through `INTERMITTENT` in
  `scripts/run_specs.py`; remove that entry with the fix.

- [ ] **Two window specifications fail on Linux.** Under the headless sway
  compositor at 1920x1080, `examples/animation-studio/specs/window-timeline.scm`
  times out settling at line 26 with one task outstanding, and
  `examples/database-browser/specs/window-cell-tooltip.scm` never shows the
  "About the folder grant" tooltip (line 11), on `nightly-2026-09-27-a3ce7f1`
  at the pre-upgrade commit and on `nightly-2026-10-20-7a8a800` alike, built
  with or without the cache. CI runs window specifications only on macOS and
  Windows, so nothing gates them on Linux. Find each cause, then run the Linux
  window suite in CI.

- [ ] **RELEASE BLOCKER: Observatory's window Timeline fails on hosted macOS
  and Windows runners.** `examples/observatory/specs/window-timeline.scm`
  line 30 reports "Show the whole timeline" laid out at (872,239)-(978,270)
  but not on screen, where the runner opened the 1440x820 window at 1024x656
  points (macOS) or 1024x720 (Windows): CI runs 36519276403 and
  36509812236. The rectangle lies inside the window, so the check or a
  clipping ancestor disagrees with the layout. It passes on Linux at
  1920x1080. `native.yml` excludes it from the window job, and `link-inputs.yml`
  from its macOS validation. Find why the
  button reads as off screen and remove the exclusion.

- [ ] **Text in a produced row reports the next row's bounds.** In the Database
  Browser's result list, `(text "Book 00003")` in result row 2 records the
  rectangle of row 3's text, one row height lower, while the enclosing cell row
  records its own. A `screenshot :region` of that text photographs the wrong
  row, and a `hover-enter` at its centre rests on the next row's cell, so the
  popover specifications there locate cells by their rows. Find why a text
  node's probe marker inside a virtual-list row lags or leads its row, and add
  a window specification that crops a produced row's text.

- [ ] **Two hover-grid window specifications failed intermittently and no
  longer reproduce.** `benchmarks/nested-hover-grid/specs/window-trail.scm`
  line 20 once observed 8 button renders in one completed frame against its
  bound of 7, and `benchmarks/hover-grid/specs/window-trail.scm` line 22 once
  observed the trailing colour (0xd58aff) for 0x66e0ff under `--jobs 4`. Both
  passed 50 of 50 loops, 30 of them beside 32 busy CPU workers, once
  `hover-enter`, `click`, and `scroll` waited for the window to draw the graph
  before locating their target; one loaded run before that change had failed
  line 30 of the flat grid as a stale generation. What remains unexplained is
  a cell leaving hover while the runner's pointer rests on it, which only a
  pointer event the runner did not send — a compositor `wl_pointer` motion or
  leave for the real cursor, or the GPUI fork re-routing hover to a stationary
  pointer after paint — could cause. If either recurs, record the step's
  `native_work_since_mark` per frame with the node ids rendered, and log every
  `MouseMove` GPUI dispatches with its origin, to say which button rendered
  the eighth time and whose pointer event exited the cell.

- [ ] **A canvas node's probe bounds disagree with its painted surface.** In
  Observatory's scrolled Frames view, `probe::Frame::bounds` for a canvas node
  reported a rectangle one canvas-height below where the canvas painted, so a
  `:region (role canvas ...)` screenshot photographed the table beneath it.
  Canvas regions now use the painted surface (`canvas_surfaces`), as canvas
  items and pointer steps already did, but `expect-on-screen` and
  `expect-bounds` on a canvas still read the probe. Find why the probe's
  prepaint rectangle for a canvas differs and make one rectangle serve all.

- [ ] **The window runner cannot drag or press a canvas.** `drag` is
  semantic-only (`crates/host/src/spec.rs`), so no window specification
  exercises the interactive canvas pointer path or its recorded `drag` cycles
  end to end, and Observatory's press on a frame or a bucket is proved only on
  the semantic runner. `pointer-move`, `pointer-leave`, and `wheel` already
  move the window's own pointer; drive pointer begin, move, and end the same
  way.

- [ ] **Native frame focus work still scans unaffected controls.**
  `Runtime::render` walks focus handles and computes the graph's focus order on
  focused frames. Deleted-focus and canvas-drag recovery also reverse-search
  native identities. These preexisting paths are separate from graph patch
  work, so bounded component renders and validation visits do not establish
  end-to-end work proportional to changed nodes. Index focus/identity recovery
  and update it from accepted graph deltas, while preserving dialog focus and
  native interaction behavior through production window specifications.

- [ ] **A control that reorders under the finger can hand its press to its
  neighbour.** Element identity is a path of sibling keys, and a node with no
  name of its own — `Elem.text`, and any container an application left unnamed
  — is keyed by its position. If such a node is pressed and its siblings are
  reordered or one before it is removed in the same patch, the identity that
  was pressed now belongs to a different node, and the release completes on
  that one. Explicit keyed components establish a stronger scoped identity,
  but they do not grant arbitrary reparenting: named controls retain identity
  only while their structural ancestor scope survives. Keep this gap for
  anonymous positional control ancestry until a production pointer regression
  proves the required behavior. Do not treat named component reorder coverage
  as proof that every unnamed layout path is safe.

- [ ] **Complete native pointer routing in window specifications.** The local
  GPUI patch exposes `DispatchEventResult`, enabling `hover-enter` and
  `hover-exit` to inject mouse-move events into the real GPUI window. Click
  still uses the production handler after geometry validation, and scroll
  writes the production scroll handle. Migrate those commands to native
  button and wheel events to exercise dispatch order, unrelated occlusion,
  press/release continuity, and wheel routing. This seam does not test
  operating-system pointer delivery or compositor sampling.

- [ ] **A window specification cannot run while the screen is locked.** A
  locked macOS session presents no frame, so every window case reaches
  `driver-started` and waits for one that never arrives until the watchdog
  fires. The watchdog now names the cause rather than reporting only a
  deadline, which is the difference between an environmental note and an
  apparent defect in the host, but the constraint stands: window evidence needs
  an unlocked session. This is why continuous integration needs the headless
  compositor lane below rather than a desktop session.

- [ ] **A window specification cannot wait for an HTTP request.** In the window
  runner `await-task` is `settle 2`, and a real `Http.Client.send!` over loopback does
  not land inside it: the readout is still "in flight" when the next step runs.
  Asking for more settling makes it worse rather than better — repeated
  `await-task` steps, or one `settle :frames 45`, leave the windowed host
  hanging until the 45-second watchdog kills it, and a run that ends with the
  request still outstanding aborts with `roc-gui host error: RocHost is not
  initialized`, so a worker completion is reaching a torn-down host. File and
  TCP worker tasks in the same runner settle normally, so this is specific to
  the HTTP path. The effect is that no window case can photograph a response, a
  status line, or a granted-authority readout that only a real reply produces:
  HTTP Workbench's window cases therefore cover the first frame and the refusal,
  which is everything reachable before the network, and its granted state is
  asserted only by the semantic runner.

- [ ] **Two concurrent worker completions have no ordered wait.** `await-task`
  applies one accepted completion, but when an application has two identical
  requests in flight the order they land in is not deterministic. Image
  Library's superseded folder scan is only observable while the older
  completion is being suppressed, so the claim cannot be asserted: a
  specification that checks the gallery is still empty after the first
  `await-task` passes or fails depending on which scan finished first.
  Suppression there is therefore covered only by the final state and the file
  counters, which are identical with and without the guard. An ordered or
  request-selective wait step would close it.

- [ ] **Shared steps the window runner does not implement.** `drag`,
  `replace-text`, and `submit` are still classified semantic-only because the
  window runner refuses them, not because they would be dishonest there.

  The value and ordering assertions have since landed and are no longer on this
  list. They cost almost nothing, because each is answered from the mounted
  graph alone: `runner::graph_claim` now holds the only implementation and both
  runners call it, so the five words cannot come to mean two things.
  `revoke-file-grants` and the owner counter assertions have since landed the
  same way: `runner::resource_claim` is the only reading of the host's one files
  registry, clipboard, audio device table and the rest, and both runners call
  it, so `examples/file-explorer/specs/window-listing.scm` now photographs the
  listing and asserts the picks, lists and reads that produced it in the same
  run. File operation counts are differences from the start of a lifecycle, of
  which the window runner has exactly one.

  The two that remain are each a different problem rather than two of the same
  one. `drag` and `submit` want a pointer and a submit route the window runner
  reaches only by simulation, which is the entry above; `replace-text` sets a
  value directly, which in a window would bypass the editing path `type`
  exists to exercise, so it needs a decision about whether that is worth
  offering at all.

  `clipboard-text` and `await-ticks` have since landed in the window runner and
  are no longer on this list. They are worth reading before the next one is
  attempted, because each needed a different answer than settling: a clipboard
  watcher rearms its read inside the completion that delivers the last one, so
  one task is outstanding at every instant and quiescence never arrives, and
  `await-ticks` therefore counts timer *fires* rather than completions, since a
  fire can only be one that started after the step did.

- [ ] **CI compositor.** Benchmark jobs run the real Wayland backend under a
  headless compositor such as sway or cage. For Sway this requires a headless
  wlroots output, software rendering on workers without a GPU, and pointer
  movement plus press/release over its IPC or virtual-pointer protocol. The job
  must prove that GPUI receives the real Wayland event before benchmark captures
  are accepted; merely opening a window is insufficient.

- [ ] **Demote the headless runner to smoke.** Remove benchmark policy from it
  and make the scaling and compare views refuse `semantic-headless` captures.
  Strictly after window sample orchestration and compositor verification:
  the automated benchmark matrix uses `semantic-headless`, while individual
  window captures already measure native work. Preserve the explicit backend
  distinction until the sampled native matrix replaces it.

- [ ] **Capture the window, not the screen region, on macOS.** Linux reads back
  the presented frame from the WGPU renderer and Windows uses `PrintWindow`;
  the equivalent on macOS is a readback from the Metal renderer's drawable,
  which GPUI does not yet offer. `screencapture -R` takes a
  screen rectangle, so anything drawn over the window lands in the evidence; a
  1280x800 window on a display with the dock visible photographs the dock. A
  window-targeted capture (`screencapture -l<windowid>`, which reads the
  window's own contents) would be immune, at the cost of cropping in process
  from the returned image rather than in the request. The `image` crate is
  already a dependency; the missing piece is the window id, which GPUI does not
  expose and which would need the pid-to-window mapping the capture currently
  avoids needing.

- [ ] **Wayland window specifications in continuous integration.** The window
  runner is platform-neutral and screenshots read back the host's own frame,
  but no Linux runner has a compositor. This needs the headless lane (`sway --headless`,
  `WLR_BACKENDS=headless`, software rendering) described above.

- [ ] **Golden-image comparison.** Window specifications photograph state but
  never compare images. Comparison needs a storage, review, and update story of
  its own, and should not be bolted onto the capture step.

- [ ] **Multi-display screenshots.** GPUI hard-zeroes the macOS display
  origin (`platform/mac/display.rs`) and computes window bounds relative to the
  window's own `NSScreen`, so a window on a secondary display has no recoverable
  global coordinates. Capture reports `unavailable` rather than guessing.

## Release infrastructure

- [ ] **A release tests only the semantic specifications of its bundle.**
  `scripts/check_platform_bundle.py` builds every application from the
  published bundle on each target but runs only the specifications the host
  describes as semantic. Window specifications run in CI's native jobs against
  the same host, not against the bundle. Run them in the release test too:
  under `scripts/headless_wayland.py` on Linux, and serially on macOS and
  Windows with the exclusions CI's native window job applies.

- [ ] **Validate Windows host packaging.** The unified linker-input release
  supplies the GNU runtime and `roc-gui.res`; the host derives its own
  `windows-imports.lib` with a schema 2 normalization receipt. The Windows host
  candidate (`prepare_host_build.py`, `host_notice_payload.py`) has been
  changed but not yet run in a release; confirm it in the release dry run.

- [ ] **Keep Metal shader debug paths free of build-machine identity.**
  The host pins the GPUI fork at
  `252b436e332f68c9ac2d6c785dd075fd19b69785`, based on Zed commit
  `7fecbb2c4b0cb296e8bb91dc6ff654c4a076c8ff`. Its `gpui_apple` build script
  compiles a copy of `shaders.metal` staged in Cargo's `OUT_DIR` with
  `-gline-tables-only`, so the shader library records a path under the build's
  target directory, which is normally beneath a home directory. The former
  vendored build remapped the source root to `/workspace` with
  `-fdebug-prefix-map`. Remap `OUT_DIR` to a neutral prefix in the fork, then
  verify on macOS that the produced `shaders.metallib` contains no build path.

- [ ] **Read back presented frames on macOS and Windows.**
  `Window::request_frame_capture` reads back the presented frame through the
  WGPU renderer on Wayland and X11. The Metal and DirectX windows report no
  support, so window-specification screenshots on those platforms use their
  existing fallback. Implement the same presented-frame readback in the fork's
  Metal and DirectX renderers and verify it on each platform.

- [ ] **Remove superseded linker-input migration machinery.** The unified
  `link-inputs.lock.json` is published and adopted, and every Linux component
  archive that `dependencies.lock.json` names is an obsolete format the
  archive policy refuses, so Linux has no development inputs outside a
  producer run. The component lock's remaining consumers are the Windows
  runtime and import installers, the macOS interfaces and the web musl inputs
  in `scripts/prepare_dependencies.py`, with `scripts/release_dependencies.py`
  and `scripts/release_windows_inputs.py` as their publication helpers. Move
  each onto the unified release, then delete the component lock and those
  helpers; retain the independently required host and notice inputs.

## Continuous integration

- [ ] **Take the host toolchain from Kai on every runner.** The host and
  linker-input jobs install Zig 0.16 and Rust 1.95.0 through
  `.github/actions/setup-toolchain`, repeating versions `Kaifile.roc` and
  `rust-toolchain.toml` declare, with nothing checking they agree. Kai runs
  on Linux only for now, so the macOS and Windows jobs, whose `build.py`
  admits the FreeType linker input with `kai build freetype --plan`, wait for
  a Kai release that runs there. When it does, add `x86_64-windows` to
  `Systems`, fetch Zig there, and delete `setup-toolchain`.

- [ ] **Read the linker inputs' nixpkgs pin from Kai.**
  `dependencies/nixpkgs-pin.nix` repeats the revision and `narHash` that
  `.kai/lock.json` locks, and `scripts/check_all.roc` compares only the
  revision `dependencies/FreeType.roc` declares, so a disagreement in
  `narHash` goes unnoticed. `kai lock` reports both, and
  `scripts/check_linux_reproduction.py` already reads it; the FreeType
  build's evidence takes the pin from `nixpkgs-pin.nix` because Kai's input
  record lists no package sources. Derive the pin from that report,
  fingerprint that entry alone, and delete the duplicate. FreeType is
  produced through a Kai `Build`; move the ALSA, glibc, unwind and xkbcommon
  producers onto it the same way.

- [ ] **Port the remaining automation to Roc scripts.** roc-automation keeps
  repository automation in `scripts/*.roc` run by `roc-stable`. The checks,
  host-bindings regeneration and release notes are Roc scripts; the
  specification runner, the headless compositor wrapper, the host and
  linker-input producers and the release bundling are
  still Python, with their unit tests. Port each with its tests carried across
  as `expect` tests, consolidating where scripts overlap, and delete the
  Python once the replacement runs in CI.

- [ ] **Call roc-automation's shared nightly and run the archived examples'
  specifications.** roc-automation's reusable
  `.github/workflows/nightly-compatibility.yml` owns selection, archive
  admission, compilation, execution and reporting, and its manual asks each
  repository to call it rather than keep a local copy. `nightly.yml` here is
  that local copy without execution: it builds every application of the
  latest release's examples archive against the published bundle on each
  target, but runs no specification. The shared runner reads
  `<package-name>-examples-<tag>.zip` with a `spec.json` of
  stdout/stderr/exit-code cases, and a GUI application needs a `run` runtime
  helper there that drives its specifications headlessly and exits. Publish
  the examples archive in that shape, run the specifications through the
  release's own runner as `release.yml` does for the bundle it is about to
  publish, and replace `nightly.yml` with the one-job caller.
