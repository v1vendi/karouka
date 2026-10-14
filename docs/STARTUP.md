# Startup

Exec to first frame: how to measure it, where the milliseconds go, what is open. Figures are from
the dev Mac (M1 Pro, macOS 15, Release, warm file cache) with their date and load average (load
inflates wall times).

## Status

| What | Figure | Measured |
|---|---|---|
| `kr_system_create2`, empty page, check's startup gate | p50 21.5 ms, min 19.98 over 11 runs; instructions p50 152.3 M; main-thread off-CPU min 3.39 ms | 2026-10-09, load 15 |
| the same inside a full `dev.sh check` | p50 27.9 ms, min 24.27 over 11 runs | 2026-10-09, load 9 |
| pre-main (exec to `main`), `pages/tests/page.html`, under the build lock | p50 15.3-15.8 ms (min 14.8-15.2) over 31 runs; 18.7-20.1 (min 15.2-16.7) in noisier runs | 2026-10-09, load 8-60 |
| first frame's flush, five pages | p50 0.84-1.85 ms (min 0.42-1.67) | 2026-10-09, load 77-79 |
| `showcase_page` frame-2 flush (its first text), second launch | p50 1.34 ms (min 1.27), 3.25 with `KR_WEBFONT_GLYPHS=0` | 2026-10-09, load 7 |
| wall, one frame: `pages/tests/page.html` / `demo_page` / `showcase_page` | p50 98.1 / 95.8 / 131.2 ms | 2026-10-08, load 27 |

## How to measure

- **`tools/dev.sh startup`** builds and runs only check's `kr_system_create2` gate ([Budget](#budget)),
  logged to `Build/release/karouka/startup/<checkout>/startup.log`. It runs from a snapshot of the
  build holding the measure lock, so it never overlaps a `bench` or `mem`; `check`'s own gate takes that lock too, for the gate
  only.
- **Phases.** `karouka_viewer <page> --headless --frames 1 --mem-phases` prints a `karouka-mem-phase`
  line per phase with `t_ms` (since exec, so dyld counts) and `cpu_ms`: `start` (`main`),
  `host-device` (the viewer's `MTLDevice` and queue, handed to `kr_system_create2` as a game would),
  `system`, `view`, `load`, `advance-N`/`render-N` for frames 0-2, `end`, `destroyed`. Never time
  with `--mem-phases-heap`: its heap walk adds ~60 ms a phase.
- **`KR_DEBUG=1`** (or `--host-log debug`) logs `kr_system_create2 X ms` and its work and wait
  counters (below), the GPU thread's `gpu: context … warm-up … waited …`, the font thread's
  `fonts: … waited …`, and each frame's `render replay … ms, flush … ms, glyph cache +N bytes`.
- **Shader cache.** Pass `--shader-cache <file>` (`--no-shader-cache` for cold) and run once to
  write it. The viewer's own default, `~/Library/Caches/karouka/skia-shaders.bin`, holds whatever page
  ran last; `dev.sh run` and `wpt` set `KR_SHADER_CACHE_DIR` to a per-page cache under the checkout's
  build output instead.
- **Per function:** `xcrun xctrace record --template 'Time Profiler' --launch -- <viewer command>`
  samples on-CPU every 1 ms; off-CPU waits show as wall minus CPU in the phase lines.
- Discard the first launch after a relink, and interleave A/B runs, as `tools/dev.sh bench --ab` does.

## Where the time goes

`pages/tests/page.html`, median of 15, wall ms (CPU ms), 2026-10-08, load 27 (patches
0001-0052). Later patches change the first advance (0072, 0073), not the phases before it.

| Phase | ms | What and where |
|---|---:|---|
| exec → `start` | 20.6 (19.1) | dyld loading and binding libkarouka and the 25 vcpkg dylibs, and static initializers (LibWeb's generated tables, one Rust panic hook per crate, libobjc). No initializer above 2 ms |
| → `host-device` | 14.5 (10.1) | the viewer's device: `MTLCopyAllDevices` loads the AGX driver, ~9 ms. A game has its device already |
| → `system` | 24.3 (26.4) | `kr_system_create2`, on three threads (below) |
| → `view`, → `load` | 2.1, 1.5 | `kr_view_create`, `kr_view_load_file` (scripts dominate on `showcase_page`) |
| → `advance-0` | 12.2 (11.4) | first style and layout, including the UA stylesheet's first parse |
| → `render-0` | 8.8 (7.9) | display-list replay, the flush, and the headless viewer's wait for the GPU |
| `end` → `destroyed` | 0.3 | teardown |
| process exit | 13.7 | static destructors, dyld, the kernel unmapping (not yet re-timed on a quiet machine) |
| **wall** | **98.1** (88.2-133.3) | |

**Inside pre-main** (2026-10-09; four interleaved runs of 21-41 launches under the build
lock, `start`'s `t_ms`, against probe executables that only print the same figure and link a part of
the viewer's closure). Wall p50 ms, CPU in brackets, from the quietest run:

| Probe | ms | So |
|---|---:|---|
| empty C program | 2.2 (1.6) | `posix_spawn` and dyld's floor: `pbi_start` is the fork, not `main` |
| + every system framework the viewer and libkarouka link (Cocoa, Metal, CoreText, CoreLocation, ...) | 3.7 (3.1) | system frameworks ~1.5 ms; CoreLocation, OpenGL and ImageIO (skia's) add nothing measurable once Cocoa is loaded |
| + the 25 vcpkg dylibs | 11.0 (10.3) | **the vcpkg dylibs: 7.2-9.9 ms wall, 7.1-8.0 ms CPU** across the runs |
| 25 empty dylibs instead | 4.7 (4.0) | dyld's per-image cost alone is ~0.1 ms; the rest is the dylibs' content (binds, fixups, initializers, page-ins) |
| the viewer | 15.3 (14.4) | libkarouka itself (148,575 fixups, 300 initializers) and the viewer: 4.3-6.6 ms |

Alone, each vcpkg dylib costs 0.1-0.7 ms over the empty program except skia (2.5, with its
frameworks) and the ICU trio (1.4). Linking them statically could save at most those 7-8 ms, more
likely the ~2.5 ms of per-image cost plus the cross-image binds, since the code, its fixups and its
initializers move into libkarouka. libkarouka already links the Lagom libraries as object files, so
only the vcpkg target triplet has to change: `arm64-osx` from `Meta/CMake/vcpkg/distribution-triplets`
(`VCPKG_LIBRARY_LINKAGE static`) instead of today's `arm64-osx-dynamic` from `release-triplets`;
`BUILD_SHARED_LIBS` can stay on. None of the ~28 target ports (skia, ICU, harfbuzz, dav1d, …) is in
the binary cache for that triplet, every compile command's vcpkg include path changes (a full
Ladybird object rebuild for every checkout), and `tools/bundle_size.py`,
`tools/snapshot_build.py` and the order file assume the dynamic layout. At 15.3-15.8 ms on a quiet
run the 15 ms target is within the noise.

**Inside `kr_system_create2`** (`src/engine/Engine.cpp`), three threads run at once:

- **Main thread:** LibWeb's setup, then the VM (`initialize_main_thread_vm`), which is nearly all of
  it: 21-25 ms of main-thread CPU at load 48-51, ~108 M of create2's ~152 M instructions. That is
  almost entirely the kernel making LibGC's two 4 TiB `PROT_NONE` reservations in `JS::VM::VM`: the
  heap region (an 8 TiB `mmap`, then `munmap` of the unaligned head and tail) and the primitive
  storage cage (a 4 TiB `mmap`). macOS keeps an anonymous mapping as one map entry and VM object per
  128 MiB, so these cost ~1-1.5 ms per TiB (12.5 + 3.8 + 5.5 ms in a standalone test). Mapping a
  named memory entry with `mach_vm_map` instead (one object, aligned by the kernel) takes ~0.01 ms;
  emulated with an `mmap` interposer it takes create2's main-thread CPU to 0.5 ms. Slow
  runs are slow on the CPU, not waiting.
- **GPU thread** (`Karouka::set_up_gpu`, `src/engine/HostMetal.mm`): reads the shader cache, makes
  the Skia context, then warms it up: the warm list's programs precompiled and a 16x16 clear that
  takes the first command buffer and render pass. The later list's programs are precompiled until
  the main thread is about to join. The thread takes 17-27 ms at load 77-79, and the join waits
  0.02-0.2 ms for it. What the warm-up costs in memory: [MEMORY.md](MEMORY.md).
- **Font thread:** `FontPlugin`'s constructor resolves every generic family to San Francisco through
  `SystemUIFontProvider` and runs Skia's smoothing probe (~7 ms); making SF, the process's
  first CoreText font, costs ~6 ms cold. No font directory is read.

**Already in place** (don't redo): the Metal device is picked with `MTLCopyAllDevices`, not
`MTLCreateSystemDefaultDevice` and its WindowServer and TCC round trips (patch 0019, ~25 ms); Skia's
CoreText font manager lists families only when something enumerates them (patch 0020, ~12 ms); the
Lagom libraries are linked into libkarouka with only `kr_*` exported (~16 ms of pre-main);
system fonts are SF only (~25 ms CPU).

## Shader cache and the first flush

The cache file (`kr_system_desc.shader_cache_path`, `src/engine/ShaderCache.h`) holds each program's
MSL, which saves SkSL generation and compilation (~0.5 ms a program), plus a warm list (the programs
views' first frames used, at most 24, precompiled before `kr_system_create2` returns) and a later
list (frames 2-4's new programs, at most 32, precompiled while there is time).

What is left of the first flush is ~0.5 ms of the frame's own work (the IOSurface as a render target
for the first time, its draws) plus ~0.05 ms a program for fetching the pipelines the precompile
started; hence `showcase_page`, 18 programs, stays above 1 ms. Going lower needs pipeline states
built ahead, which Ganesh's `precompileShader` can't do without the draw's `GrProgramInfo`, or
`MTLBinaryArchive`, which Skia m148's Ganesh Metal backend doesn't support.

## Web-font glyphs and the second flush

A page's first frame with web-font text pays for rasterizing its glyphs in the flush:
`showcase_page`'s frame 2 is its first with text (its @font-face loads in frame 1). Next to the
shader cache, `<shader_cache_path>.glyphs` (`src/engine/WebFontGlyphs.h`) lists the glyphs views'
first 4 frames drew in web fonts, per page URL: per face (a hash of the font data, point size,
variation axes, shape features) the strike's SkFont parameters, paint color, glyph id and
quarter-pixel offset, up to 16K entries. It also lists, marked offscreen, the glyphs those frames'
display lists hold outside the damage (text below the fold or scrolled away in a scroller, up to 2048
a frame). That walk costs 0.1-0.6 ms a frame on a long page, so it is taken once per page and font:
on the first run that draws the font there.

Patch 0075 calls the host when LibWeb has made a web font's typeface, before the restyle it
triggers: in `FontLoader` (@font-face rules and `FontFace`s from URLs) and in `FontFace`'s own parse
of a BufferSource. The host then draws the list's onscreen glyphs for that font on one worker into a
16x16 raster canvas while the advance goes on. It gets each face from `Gfx::Typeface::font()`, whose
cache LibWeb's style then hits. That matters because a variable font's every `Font` gets its own
SkTypeface clone, which keys its own strikes; warming the loaded typeface itself, or a clone of our
own, fills strikes nobody draws from. The CPU text path makes the same images as Ganesh's direct
masks. The render stops the worker before its replay (the flush rasterizes whatever it didn't reach)
and starts it again after the flush: on the onscreen glyphs it hadn't reached, then on the font's
offscreen ones, until the next replay. `KR_WEBFONT_GLYPHS=0` turns it off. `KR_DEBUG`'s
`render replay … ms, flush … ms, glyph cache +N bytes` says how many bytes of glyph images a frame
rasterized itself.

Not warmed: text of 18 px and up (distance fields), transformed or vertical runs, the software
backend, and text a page gains offscreen after the run that walked it.

`showcase_page`, second launch, one binary, `KR_WEBFONT_GLYPHS=0` against on, 15 interleaved runs
each at load 7 (2026-10-09), p50 (min/max) ms:

| | off | on |
| --- | --- | --- |
| frame-2 flush | 3.25 (3.06/3.40) | 1.34 (1.27/1.70) |
| frame-2 replay + flush | 3.71 (3.50/3.84) | 1.64 (1.55/2.00) |
| `kr_system_create2` | 21.68 (19.78/23.09) | 21.49 (20.35/22.90) |

The worker warms the page's 302 glyphs in 2.3-2.9 ms (the other demo pages' 72-320 in 0.9-1.8
ms). In the headless viewer the typeface is made 62-80 ms before frame 2's render, so the worker
always finishes, and the render waits 0.01-0.07 ms for it. With less time in between, the flush
does what's left, and the worker finishes the rest after it. Recording a frame's glyphs costs
0.05-0.25 ms after its flush, and only on pages with a web font.

A page that makes Noto Sans with `new FontFace("…", bytes)` and draws 1908 glyphs of it at 11-17 px
(the font loads in frame 1, its text draws in frame 2; the worker reaches ~1700 glyphs before frame
1's render, and the rest after it). Second launch, 15 interleaved runs each at load 21-23
(2026-10-09), p50 (min/max):

| | no hook for BufferSource fonts | hook, worker dropped at the render | hook, worker resumed after it |
| --- | --- | --- | --- |
| frame-2 flush, ms | 5.60 (5.42/8.07) | 1.37 (1.02/1.64) | 0.96 (0.90/1.05) |
| frame-2 replay, ms | 0.72 (0.68/0.88) | 0.24 (0.16/0.29) | 0.15 (0.13/0.19) |
| frame-2 glyph images, KB | | 23.1 (0/30.5) | 0 |

Scrolling 60 px a frame for 30 frames, second launch, a build without offscreen glyphs and the
resumed worker against one with them, 11 interleaved runs each at load 16-19 (2026-10-09), p50
(min/max):

| page | | without | with |
| --- | --- | --- | --- |
| `trellis_page` | renders 3+: replay + flush, ms | 15.08 (13.95/15.55) | 11.86 (10.87/12.45) |
| | renders 3+: glyph images, KB | 118.4 | 42.3 |
| `sashimi_page` | renders 3+: replay + flush, ms | 15.32 (14.66/17.89) | 12.86 (12.26/15.08) |
| | renders 3+: glyph images, KB | 82.5 | 27.4 |

The glyph images left are the system font's and text of 18 px and up. `showcase_page` is
unchanged: frame-2 flush 1.39 against 1.41 ms, the same 5.7 KB of glyph images. The worker warms
trellis' 1115 offscreen glyphs and sashimi's 1349 in 6-8 ms between the first renders, which a page
that never scrolls pays for nothing: over 600 frames at load 13-15, process CPU 184 → 190 ms
(trellis, static) and 506 → 517 ms (sashimi, scrolling), max RSS +0.4 MB, and frame p50 within
noise (0.009 ms both; 0.449 against 0.491 ms).

## Budget

`tools/dev.sh check` runs the empty page once to write its own shader cache (`startup-shaders.bin`),
then times `kr_system_create2` (the `KR_DEBUG` line) over 11 one-frame runs (`KR_STARTUP_RUNS`),
and fails, at any load, when:

- **work:** the median instructions retired over the runs is over **160 M**
  (`KR_SYSTEM_CREATE_INSTRUCTIONS_BUDGET_M`). Clean main: p50 152.0-152.4 M at load 14-29, 151.3 M
  at load 62, steady while wall time varied 23-90 ms. About 4.5-5 M instructions per ms of CPU, so
  ~1.5 ms more CPU work fails it at any load;
- **waits:** the fastest run's main-thread off-CPU time (wall less the thread's own CPU time) is
  over **6 ms** (`KR_SYSTEM_CREATE_OFF_CPU_BUDGET_MS`). Clean: 3.4-5.5 ms at load 15-40, 3.95 ms at
  load 43, 4.71 at load 62; with a 3 ms `usleep` at the end of create2: 6.6-8.2 ms. Load only adds
  waits for a CPU, so it can't hide a sleep, but over load ~60 those waits alone reach 12-20 ms on
  healthy branches (12.5 ms at load 69, 9.2-12.2 at 107-108, 19.6 at 126; 4.1-5.5 at 88 on quieter
  stretches) and no run in 41 gets under 6. So when the load is over **60**
  (`KR_STARTUP_OFF_CPU_LOAD`) the budget widens to **1 ms per 4 of load** (17.3 ms at load 69, 31.5 at
  126, never under 6), and the summary line says `widened from 6 ms: load X is over 60`. Clean runs
  there sit at 0.11-0.18 ms per point of load, so the widened budget keeps a 1.4x margin and still
  fails a sleep or wait of ~10 ms or more; a 3-5 ms one is caught only by a check under load 60;
- **wall:** the fastest run is over **40 ms** (`KR_SYSTEM_CREATE_BUDGET_MS`) plus 1 ms per 5 of load
  over 40. A loose catch-all for what neither count sees. Clean fastest: 15.6-33 ms at load 15-40,
  26.2 at load 43, 33.7 at load 62: the main thread's own CPU time grows with load (22 to 29 ms),
  so the budget does too.

When either minimum misses its budget after the 11 runs, up to 30 more run (`KR_STARTUP_EXTRA_RUNS`),
stopping at the first that brings both in. Both budgets come from the 1-minute load as the runs
start; the verdict uses the higher of that and the load as they end. A healthy branch on a busy machine pays seconds, not a
FAIL; a real regression pays the 30 runs (~25 s) and fails.

The wall gate judges the fastest run, not the median: a median gate (40 ms, plus 1 ms per 10 of load
over 80) was pushed to 42.8 ms by load 45-50 from other apps on branches that hadn't regressed while
their instruction counts were fine. The median is still printed, not judged.
With `KR_DEBUG=1` the viewer prints the counters the gates read:
`kr_system_create2 runnable X ms, cpu X ms, main cpu X ms, off-cpu X ms, instructions X M, cycles X M`.
A `usleep` before `initialize_main_thread_vm` costs only ~1-2 ms of wall time (the main thread
otherwise waits that long on the GPU and font threads); at the end of create2 it costs the full
amount. Lower the instruction budget when create2 does less work (re-measure the p50 first: a macOS
update moves the Metal and CoreText share); raise a budget only with the reason here.

## Open candidates

- Static vcpkg libraries in libkarouka (static ports into the binary cache first, then the triplet
  switch): pre-main at most 7-8 ms faster, likely ~3 (see "Inside pre-main").
- Precompile the later list's programs in an idle pump when load leaves no time in `kr_system_create2`.
- Re-time process exit and the wall figures on a quiet machine.
- Per-page shader caches for check's page renders and `bench`, as `mem` and the startup gate have.

## Tried and rejected

- Precompiling every program in the cache: 13-20 ms more in `kr_system_create2` and a slower first flush.
- Warming showcase_page's frame-2 glyphs at render time, on workers or the main thread: CoreText's rasterization doesn't scale across threads, and the frame got slower.
- The order file for startup: warm launches 0-3 ms faster, pre-main unchanged; it stays for memory.
