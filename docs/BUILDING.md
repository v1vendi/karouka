# Building and contributing

karouka renders an HTML page into an IOSurface (or a host Metal texture) with Ladybird's engine,
in one process, with no networking: an `http(s)` fetch rejects with a TypeError, `XMLHttpRequest`
and `WebSocket` aren't exposed, and no sockets open. `README.md` has the overview, the C API, the
patch table and the viewer's flags.

## Requirements

macOS on Apple silicon with Xcode or the Command Line Tools, plus the Homebrew packages
`tools/dev.sh bootstrap` checks for: `autoconf autoconf-archive automake ccache libtool nasm ninja
pkgconf llvm` (the build compiles with Homebrew's clang). Qt isn't needed: karouka's build leaves
out Ladybird's `UI/` (the Qt browser).

## Bootstrap, build, check

```bash
git submodule update --init third_party/ladybird   # Ladybird, pinned
tools/dev.sh bootstrap   # CMake 3.30+, Ladybird's pinned Rust and sccache into .toolchain/
tools/dev.sh build       # patch, configure, build the Ladybird libraries, karouka, the viewer and tests
tools/dev.sh check       # build, then unit tests, a WPT subset, every test and demo page, startup gate
tools/dev.sh run [page]  # build, then open the page, or the start page (pages/index.html)
```

The first build compiles Ladybird's libraries and their vcpkg dependencies, which takes a while;
afterwards `third_party/ladybird/Build/` holds about 5 GB. Build only through `tools/dev.sh`:
it applies the patch series, points the build at this checkout's `src/` and takes the build lock.

Everything runs at `nice 10` with `KR_JOBS` parallel jobs (default 4). `check` runs its tests and
renders `KR_CHECK_JOBS` at a time (default 3, at most `KR_JOBS`). The comment at the top of
`tools/dev.sh` describes every command and its options; `README.md` lists them.

## Build layout

Ladybird is a submodule (`third_party/ladybird`) with `patches/ladybird/` applied to its working
tree. karouka's `src/` builds inside Ladybird's CMake tree (patch 0003) into
`third_party/ladybird/Build/release/karouka/{bin,lib}`.

- **One Ladybird build serves every checkout.** A git worktree of this repository uses the main
  checkout's submodule, `.toolchain/` and build dir (`tools/env.sh`, via
  `git rev-parse --git-common-dir`). `dev.sh` points the build at the running checkout's `src/`
  through the symlink `Build/release/karouka-src` (no CMake rerun; karouka recompiles from ccache),
  and holds `Build/karouka.lock` while it builds.
- **Overlay ports.** vcpkg installs the manifest while CMake configures, and CMake doesn't track
  `Meta/CMake/vcpkg/overlay-ports/`. `dev.sh build` hashes that directory (`Build/karouka.overlay-ports`)
  and reruns the configure when it changed since the last build, so an edit to e.g. ICU's
  `karouka-data-keep.txt` rebuilds ICU (then cached in the vcpkg binary cache) with no
  `touch vcpkg.json`. An unchanged directory costs nothing.
- **Rust crates go through sccache.** `dev.sh bootstrap` builds sccache 0.18 (local disk only) into
  `.toolchain/sccache`; `env.sh` puts it on `PATH` with its cache in `Build/caches/sccache` (4 GB);
  Ladybird's `rust_crate.cmake` finds it and gives cargo `RUSTC_WRAPPER`, and `dev.sh build`
  reconfigures once to set it. Cargo already keeps one stable target dir (`Build/release/cargo/build`),
  so sccache only matters when cargo's fingerprints go stale with the code unchanged (a patch-series
  switch or branch change rewrites source mtimes): the crates then recompile through sccache and hit.
  Patch 0088 drops an extra `--emit=dep-info` that made sccache skip each top crate. `dev.sh` starts
  the sccache server with no inherited descriptors, or the server would keep the build lock's flock
  for its 10 min idle timeout.
- **Locks and snapshots.** `check`, `run`, `python`, `bench`, `mem`, `wpt`, `libweb`, `orderfile`,
  `census` and `startup` hold the build lock only to build and snapshot the build
  (`tools/snapshot_build.py`: bin, lib, the dylibs they load, Base/res, every Mach-O repointed at the
  snapshot's lib), then run from the snapshot while other checkouts build. `check` snapshots into its
  check dir and prints `build lock: waited X s, held Y s`; a second `check` in the same checkout
  waits for the first, and so does a second `wpt`, `libweb` or `census`. The others snapshot into
  `Build/release/karouka/snapshots/`, removed when they exit. `bench`, `mem` and `startup` then
  measure holding `Build/karouka-measure.lock`, as `check`'s startup gate does, so no two
  measurements overlap, though a build may run beside one. `bench --save`, `package` (its dsymutil
  reads the build's object files) and every other command but `bootstrap` hold the build lock
  until they exit.

## Changing Ladybird

A Ladybird change is a change to the patch series `patches/ladybird/`, which must match the
submodule's working tree. Each patch is a plain `git diff` of the Ladybird tree, applied in the
order of its `NNNN-` prefix by `tools/apply_patches.sh`; two patches with one number are refused.

1. `tools/dev.sh own` before the first edit in `third_party/ladybird`. While a checkout owns the
   tree, other checkouts build against it as the owner left it, and the owner's builds keep its
   unsaved edits. One owner at a time.
2. Edit the tree, then save the change as a patch: a new one is
   `patches/ladybird/NNNN-<Lib>-<summary>.patch` with the next free number. Regenerate the matching
   patch before every `dev.sh build`/`check`, and commit it with the change that needs it.
3. `tools/apply_patches.sh --check` must print `ladybird tree matches the series`.
4. Add the patch's row to the Patches table in `README.md` (`tools/readme_sync.py --patch-table`
   prints the table with a TODO row for each patch it lacks; `check` fails until it is there).
5. `tools/dev.sh release` gives the tree back. It refuses while the tree differs from the series.

`tools/dev.sh patches [--reset]` applies this checkout's series to the tree by hand (`--reset`
discards hand edits too).

## Where to look next

- `docs/ENGINE.md`: the engine map, partial raster, clocks and timers, fonts, and the LibWeb
  pitfalls already found (each fails silently).
- `docs/PYTHON.md`: the Python integration's design and decisions.
- `docs/STARTUP.md`, `docs/MEMORY.md`: startup and memory breakdowns and baselines.
- `docs/COMMAND-LIST.md`: the display-list command census.
- `README.md`: the C API, the build commands, the patch table, the viewer's flags and keys.
