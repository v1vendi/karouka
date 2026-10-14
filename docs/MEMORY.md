# Memory

What karouka's memory is now, how to measure it, where the bytes go, and what is still open. Every
figure is from the dev Mac (M1 Pro, macOS 15.7, 16 KB pages) and carries the date it was measured.

## Status

`tools/dev.sh mem`, empty page, median of 5. The goal, under 70 MB RSS, is met.

| empty page | RSS MB | footprint MB | measured |
|---|---:|---:|---|
| `--frames 0` (loaded, never rendered) | 30.8 | 17.3 | 2026-10-11, load ~13 |
| `--frames 1` | 38.7 | 22.1 | the same, load ~9; four batches' medians 21.7-22.1, runs 21.6-22.3 |
| 600 frames | 39.2 | 22.1 | the same, load ~11 |

The footprint counts reused purged mimalloc pages (patch 0077) and pages freed in the last 1 ms
(patch 0079), § The allocator. At `--frames 1` that is ~0.9 MB of the footprint that RSS doesn't
show: 0077 ~0.5 MB, 0079 ~0.4 (0080 adds nothing). The code doesn't move it: with the allocator
held fixed, saved builds from a day of changes read within 0.15 MB of each other (interleaved
runs). A median of 5 lands anywhere in a ~0.4 MB band from one batch to the next. The bullets below
are `dev.sh mem` medians at 600 frames on a 2026-10-10 build unless they say otherwise.

- **More views:** 1 / 2 / 4 views of the empty page in one system: 22.1 / 25.6 / 32.9 MB footprint,
  42.4 and 45.0 MB RSS at 2 and 4 views: about 3.6 MB footprint per extra view, 2.3 MB of it the
  view's IOSurface (load 40-49).
- **Image churn:** `pages/tests/resource_churn.html` (a new 512x512 image every load): 74.8 / 119.8
  MB RSS / footprint (`dev.sh mem` median of 5, 2026-10-11, load 25-52),
  `decoded_images_peak` 16 MB; with `KR_IMAGE_GC=0` 32 MB (the peak is deterministic).
- **Animated churn:** `pages/tests/animated_churn.html` (~5 GIFs loaded a frame): 75.4 / 118.7 (the
  same, load 10-52), `decoded_images_peak` 16 MB; with `KR_IMAGE_GC=0` 44 MB.
- On both churn pages the footprint includes Skia's GPU resource cache, full at its 64 MB budget
  (`--memory-stats`: `gpu_cache_mb` 63.2; mem's vmmap: IOAccelerator 68.7 MB, non-volatile), which RSS
  leaves out: the footprint runs ~40 MB above RSS there.
- **Long runs of animated_churn** (2026-10-10, with 0077 and before 0079): to 9600 frames
  `kmalloc_reusable_dirty_mb` stays 0.00, `kmalloc_mb` reads 21-24 MB from frame 2400 to 7200 and
  the footprint 118-122. The ~15 MB step seen before 0077 (the kernel reclaiming reused pages, so they
  counted again) can't happen any more; `kmalloc_mb` still rises 7.6-11.6 MB between frames 7200
  and 8400, which is working set.

## Measuring

```bash
tools/dev.sh mem                       # build, then 5 headless 600-frame runs of the empty page
tools/dev.sh mem page.html             # any page; demo pages by name (demo/trellis_page)
tools/dev.sh mem --frames 0            # load, never render
tools/dev.sh mem --no-render           # advance frames (style, layout, display list), never render
tools/dev.sh mem --runs 9 --frames 1   # KR_MEM_RUNS / KR_MEM_FRAMES set the defaults
tools/dev.sh mem --views 4             # 4 views in one system (viewer --second); KR_MEM_VIEWS
tools/dev.sh mem --all-demo            # every demo page, then a table of their medians
tools/dev.sh mem --attribute           # kmalloc bytes per call site and phase (below)
tools/dev.sh mem --hold                # also keep the held run's vmmap -v and footprint
tools/dev.sh mem --malloc-history      # held run under MallocStackLogging=lite, + heap, malloc_history
```

- Each run prints `maximum resident set size` and `peak memory footprint` from `/usr/bin/time -l`
  in MiB, then the median. Quote the median; footprint is the steadier of the two.
- One more run stops itself at the end (`karouka_viewer --hold`, SIGSTOP). `vmmap --summary` then
  counts its IOSurface regions and the GPU driver's IOAccelerator memory (dirty + swapped). The
  output stays in `Build/release/karouka/mem/vmmap.txt` under the Ladybird build dir.
- The last line, `karouka-mem page=... rss_mb=M footprint_mb=M ... ladybird_tree=ID
  series=match|differs owner=... karouka=COMMIT`, is for scripts. Two numbers are comparable when
  their `ladybird_tree` is the same or differs only by the change measured (`series=differs`:
  another checkout's tree was built).
- **Shader cache.** Every run uses the page's own cache,
  `Build/release/karouka/mem/shader-cache/<hash>.bin`, which an unmeasured seeding run remakes first.
  The viewer's default, `~/Library/Caches/karouka/skia-shaders.bin`, holds whatever page ran last on
  the machine, and `kr_system_create2` precompiles its lists: up to +2 MB footprint and +3.5 MB RSS
  that move with other checkouts' runs. Timing your own runs by hand, pass
  `--shader-cache <file>`. `dev.sh run` and `wpt` use per-page caches too, under
  `Build/release/karouka/run/<checkout>/shader-cache` and `.../wpt/<checkout>/shader-cache`, as do
  `dev.sh check` and `bench`: check sets
  `karouka_viewer`'s `KR_SHADER_CACHE_DIR` to a dir under its output, and bench remakes
  `<out>/shader-cache/<engine>/<page>.bin` with an untimed run before the page's first timed one and
  prints what the timed runs precompile (`shader cache:`, `shader_cache` in results.json).
- **Noise.** RSS moves with how much of the dyld shared cache and the font files is resident and
  with memory pressure. Compare back to back in one session, ideally interleaved from saved builds
  (`tools/dev.sh bench --save NAME`). `/usr/bin/time` is SIP-protected and strips `DYLD_*`.
- **Held-run detail.** `--hold` also saves `vmmap -v -wide` and `footprint` of the held run as
  `Build/release/karouka/mem/hold/<page>.vmmap.txt` and `.footprint.txt`, and runs it with
  `--memory-stats`: it prints that run's `malloc_zone_mb` and glyph cache strike count and adds
  `malloc_zone_mb=`, `font_cache_strikes=` and `msl=` to the `karouka-mem` line (the `karouka-memory` lines stay in `<page>.stats.txt`). `--malloc-history`
  also holds that run under `MallocStackLogging=lite` and saves `heap -s` (`<page>.heap.txt`: zone
  totals, block counts per class, e.g. `SkStrike`) and `malloc_history -allBySize`
  (`<page>.malloc_history.txt`: live bytes per allocation stack, VM regions included). MSL's
  bookkeeping is in that run's zone: its vmmap reads ~1.7 MB more MALLOC dirty on the churn pages,
  so quote vmmap and footprint from a plain `--hold`. Use `--runs 1` when only the hold is
  wanted.

### kmalloc attribution

`tools/dev.sh mem --attribute` runs the viewer once with `--mem-phases-heap` (default `--frames 1`)
and `libkarouka_miprof.dylib` (`src/tools/miprof.cpp`) inserted, which interposes libkarouka's
`mi_*` imports: no Ladybird patch. Each phase's snapshot (`mem/miprof/NN-phase.tsv`) holds live bytes
per call site, the main thread's heap pages and tag 240's dirty pages. `tools/miprof.py` diffs them
(`--from load --to render-0` by default) and sorts dirty pages into live, never held a block, and
freed (`never_held_mb`, `empty_mb`). `KR_MIPROF_ARGS` passes it arguments (`--sort alloc`, `--from
render-2 --to end`); `KR_MIPROF_COLLECT=<phase>` collects the main thread's heaps at that phase.
Canvas 2D surfaces are Metal textures with a GPU backend, which no call site sees: the report's
`canvas` line takes them from the phase lines' `canvas_mb` (`KR_MEM_TAG_CANVAS`, 2 x width x
height x 4 a canvas; 0.25 MB on `pages/tests/canvas_2d.html`). On `KR_BACKEND_SOFTWARE` they are
kmalloc'd bitmaps and show under `Gfx::Bitmap` too.

`--mem-phases-heap`'s heap walk (`kmalloc_mb`, `gc_heap_mb`, `walk_ms`) costs ~60 ms a phase: never
time with it. Its line also carries the glyph cache's `font_cache_strikes`. For long runs `KR_MEM_PHASE_EVERY=N` adds a `frame-F` phase every N frames.

## Where the bytes go

One held run per column, read with `vmmap --summary`, `vmmap -v -wide` and `footprint`
(`tools/dev.sh mem PAGE --frames N --hold` keeps all three), on 2026-10-11 (load 9-21). The
churn pages are `pages/tests/resource_churn.html` and `animated_churn.html`, both at 600 frames.
Dirty and swapped (vmmap's physical footprint at the hold), in MB:

| Region | empty, 600 frames | empty, `--frames 0` | resource_churn | animated_churn | What it is |
|---|---:|---:|---:|---:|---|
| Memory Tag 240 | 4.4 | 3.3 | 23.5 | 24.5 | mimalloc: everything AK, LibWeb and LibJS allocate, decoded pixels included (`Gfx::Bitmap::allocate_backing_store` kmallocs them). The empty page at 600 frames has 5.1 MB resident; the other 0.8 is reset pages `footprint` lists as reclaimable |
| MALLOC_* (system malloc) | 2.5 | 2.3 | 12.7 | 12.9 | Skia, CoreText/CoreGraphics, HarfBuzz, ObjC, Metal: 6.5 K allocations (1.5 MB live) on the empty page, 29 K (9.8 MB live) on the churn pages, most of it Skia's glyph cache for the label's 48 font sizes (below) |
| IOAccelerator | 4.0 | 3.8 | 68.7 | 68.7 | the AGX driver's memory: the first render pass's floor, and on the churn pages Skia's GPU resource cache, full at its 64 MB budget |
| Memory Tag 241 | 2.7 | 2.5 | 4.5 | 4.3 | LibGC heap blocks |
| image data (`__DATA*`, `__AUTH*`, `__OBJC_RW`) | 2.6 | 2.6 | 2.6 | 2.6 | mostly system frameworks; libkarouka `__DATA` 0.33 |
| IOSurface | 2.3 | 0 | 2.3 | 2.3 | the 960x640 render target |
| owned unmapped memory | 1.1 | 1.1 | 1.1 | 1.1 | the Metal driver's, from the first render pass; `footprint` counts 0.14 MB of it dirty and 1 MB reclaimable |
| page tables, stacks, dispatch, misc | 1.5 | 1.3 | 2.4 | 2.6 | page tables 0.6 (0.7-0.8 on the churn pages), thread stacks 0.17-0.34, dispatch continuations 0.1-0.2 (0.8-0.9) |
| total | 21.1 | 17.0 | 117.9 | 119.0 | `dev.sh mem`'s peak footprint is ~1 MB above the empty page's |

Clean and resident outside the dyld shared cache (whose clean pages aren't the process's):

| Image | empty, 600 frames | empty, `--frames 0` | resource_churn | animated_churn | Notes |
|---|---:|---:|---:|---:|---|
| libkarouka `__TEXT` | 7.1 | 3.3 | 14.2 | 14.1 | all of Lagom, laid out by the order file (below) |
| libskia | 1.6 | 1.5 | 2.6 | 2.6 | |
| AGX driver bundle | 1.5 | 1.5 | 1.9 | 1.9 | loaded with the Metal device |
| other vcpkg dylibs | 1.0 | 1.0 | 1.3 | 1.0 | a `__TEXT` and a `__LINKEDIT` page or two each |
| ICU (vcpkg 78.3 and the system's `icudt76l.dat`) | 0.9 | 0.9 | 1.1 | 1.1 | `icudt76l.dat` 0.36; `libicudata` 0.03 (0.08 on the churn pages) |
| libkarouka `__DATA_CONST`, `__LINKEDIT` | 0.5 | 0.4 | 0.8 | 0.8 | |
| Metal shader caches (mapped) | 0.5 | 0.5 | 0.7 | 0.7 | the driver's `ds.g13s`; the churn pages also map Metal's `functions.data` and `libraries.data` |
| system font files | 0.25 | 0.2 | 1.2 | 1.2 | `SFNS.ttf`, `SFNSItalic.ttf`: the only fonts mapped |
| libharfbuzz | 0.03 | 0.03 | 0.9 | 0.9 | first used by text shaping; the empty page shapes none |
| karouka_viewer | 0.2 | 0.2 | 0.2 | 0.2 | |
| total | 14.1 | 9.5 | 25.0 | 24.7 | |

**System malloc on the churn pages** is text, not images: both pages cycle their label through 48
font sizes (`12 + frame % 48` px). `MallocStackLogging=lite` and `malloc_history -allBySize` on a
held 600-frame run (`tools/dev.sh mem PAGE --malloc-history` records both) (2026-10-11, load 3-4) put the 10.5 MB live in the zone (28.4 K blocks,
the same on both pages; vmmap's other ~3 MB dirty is the zone's fragmentation, 24%) at:

| MB live | Owner |
|---:|---|
| 5.8 | Skia's glyph cache: 145 strikes, about three a size (`Gfx::Font`'s `SkFont::getMetrics`, `SkTextBlobBuilder::TightRunBounds` in `DisplayListResourceStorage::text_blob`, Ganesh's device-space direct-mask strike). Per strike: a CoreGraphics offscreen context (`SkScalerContext_Mac::Offscreen::getCG`, 1.9 MB in all), glyph images (`SkGlyph::allocImage`, 1.1), CoreGraphics glyph outlines (`TConcreteFontScaler::CopyGlyphPath`, 1.1), the scaler context and its CTFont (0.8), digests and metrics (0.6). Skia counts only the glyphs: `font_cache_mb` reads 0.85 (below) |
| 1.2 | Ganesh's text atlas: each plot's CPU copy of its pixels (`GrDrawOpAtlas`, `GrPlot::addSubImage`) |
| 1.0 | SkSL and Metal pipelines: the shader cache's precompile (`set_up_gpu`) and draw-time compiles |
| 0.6 | SkTypeface/CTFont clones per size (`SkTypeface_Mac::onMakeClone`, `TypefaceSkia::match_system_ui`) |
| 0.5 | HarfBuzz fonts and shape plans |
| 1.0 | Metal: Skia's command buffers and encoders 0.5, device and queue setup 0.3, textures 0.2 |
| 0.3 | the rest (viewer, LibWeb, other Skia) |

The same label with no image reads 11.9 MB dirty, 9.3 MB live (25 K blocks) at 600 frames; at a
fixed font size, 4.4 dirty and 3.1 live (13 K). The decoded images (in tag 240) and their uploads
add ~0.8 MB here. At 2400 frames the 48-size label reads 12.4 MB (`malloc_zone_mb`, `font_cache_mb`
1.37; load 10), more digits drawn at each size. A label cycling through 480 sizes reads 30.9 MB at
2400 frames and 36.8 at 4800 (`font_cache_mb` 1.77; load 8-11). It is bounded, by caches with their
own limits: Skia holds ~143 strikes under its 2 MB budget; CoreGraphics' own glyph bitmap cache
(`CGGlyphBitmapCreate` under `getCG`, 10-17 MB) fills toward its 16 MB limit
(`CGFontCacheGetMaxSize`, private API); `Gfx::Typeface` keeps at most 32 `Gfx::Font`s a typeface
(patch 0096; the demo pages use 3 to 19), each with its HarfBuzz font and shaping data and, on a
variable system font, a typeface clone for its optical size. When full it evicts a font nothing else
holds before one still in use. A label whose size changes by a fraction every frame (a font-size
transition) makes a new size each frame. Two limits keep it bounded: the document's font cascade memo forgets the
cascades no computed style holds once it doubles past 64 (patch 0091), and karouka caps Skia's glyph
cache at 256 strikes (`kr_system_create2`; a strike really holds 20-40 KB its budget doesn't count,
and the demo pages use 14 to 18). A cascade is also held by its computed `FontValues` group, which
outlives the records that used it until the style engine reclaims unreachable groups; that is due
after 1024 interned records, or once the live font groups double past 32 (patch 0095), so the memo
keeps about 7 cascades at each trim on a label stepping 0.1 px a frame. That label
(`pages/gates/font_size_growth.html`, `12 + (frame % 4800) * 0.1` px) reads 50.8-51.2 MB at 2400
frames and 52.6 at 4800 (`malloc_zone_mb`, `dev.sh mem PAGE --frames N --hold`, load 3-4), against
52.0-52.8 at 2400 with the typeface cap at 129, and 85.7 and 109.2 with neither the memo's limit nor
the strike cap. In one 9600-frame run
(`KR_MEM_PHASE_EVERY=2400 dev.sh run PAGE --headless --frames 9600 --mem-phases-heap`, load 4)
`malloc_mb` reads 51.0, 52.7, 54.5 and 55.3 at frames 2400, 4800, 7200 and 9600, with 249, 206, 200
and 221 strikes; with the strike cap lifted, 62.9 to 68.0 MB and 1804 to 1869 strikes. `dev.sh
check` gates on this page (`font_size_growth_check`: growth from frame 2400 and the strike count). `pages/tests/font_size_churn.html` checks that a size
resolved again after its cascade was forgotten measures the same.

**What `font_cache_mb` counts.** `KR_MEM_TAG_FONT_CACHE` is `SkGraphics::GetFontCacheUsed`: the
glyph images, paths and glyph records Skia charges to its strikes. Each strike also holds a scaler
context and its CTFont (`SkScalerContext_Mac`, 4.6 KB, plus CoreText's own copy) and a CoreGraphics
bitmap context that grows to the largest glyph it drew, and drawing glyphs through CoreGraphics fills
CG's glyph bitmap cache (`CGGlyphBitmapCreate`, up to its 16 MB limit) and outline cache
(`TConcreteFontScaler::CopyGlyphPath`). None of that is counted. Live bytes allocated under Skia's
strike code (`SkStrike`, `SkScalerContext` or `SkGlyph` in the stack; the text atlas left out), from
`malloc_history -allBySize` on held runs under `MallocStackLogging=lite`, label pages as above
(2026-10-11, load 9-11; the showcase at load 38):

| page, frames | strikes | `font_cache_mb` | live under strikes, MB | CG's glyph bitmap cache in it | ratio |
|---|---:|---:|---:|---:|---:|
| showcase demo, 600 | 17 | 0.06 | 0.72 | 0.07 | 12x |
| label at one size, 600 | 5 | 0.02 | 0.67 | 0.02 | 34x |
| label through 48 sizes, 600 | 145 | 0.85 | 5.96 | 0.98 | 7x |
| label through 480 sizes, 2400 | 143 | 1.77 | 20.5 | 9.5 | 12x |
| label at fractional sizes, 2400 | 249 | 0.48 | 39.0 | 15.8 | 81x |

Neither of Skia's public counters, the bytes or the strike count (`GetFontCacheCountUsed`, printed
as `font_cache_strikes` after `font_cache_mb` and in `kr_memory_stats.font_cache_strikes`), predicts
the rest: beyond what Skia counts, a strike costs 35-40 KB on the showcase and the 48-size label and
130-155 KB on the others. The first strikes pay ~0.5 MB of CoreText setup, large glyphs grow the CG
contexts and caches, and part of it likely outlives the strike that made it: the fractional page
keeps 11.9 MB of `CopyGlyphPath` outlines for its 249 strikes, against 1.1 MB for the 48-size
label's 145. So the tag stays Skia's count (`karouka.h` says so), and the rest shows only in
`malloc_zone_mb` and `malloc_total`.
For the glyph cache's real cost, compare `malloc_zone_mb` with the same page at one font size, or
run this profile.

**The first frame** (the empty page's 600 frames against `--frames 0` above) adds 3.9 MB of
libkarouka `__TEXT`, 1.8 MB of resident mimalloc pages (1.1 dirty, 0.8 reclaimable), the 2.3 MB
IOSurface and 0.2 MB each of LibGC blocks and system malloc. The mimalloc part is the UA stylesheet,
parsed on the first style update: a rule is compiled once an element it can match arrives, or an
attribute it requires (`[hidden]`, `[popover]`, `[dir]`) arrives or appears (patch 0072), a
predefined counter style once a page names it (patch 0044). Load to render-0 allocates 3.49 MB
(2026-10-09, `--attribute`); holding back the rules whose subjects aren't element types took load ->
destroyed under `--no-render` from 3.49 to 3.16 MB. The UA rules an empty page still
publishes are the html/body ones and those whose subject any element can match: `:root` and its
view-transition pseudo-elements, `:focus-visible`, `:fullscreen`, `::backdrop` and `::marker`.

**The GPU warm-up.** `kr_system_create2` warms the GPU up on its GPU thread (`Karouka::set_up_gpu`,
`src/engine/HostMetal.mm`; timing in [STARTUP.md](STARTUP.md)): a 16x16 clear takes the first
command buffer and render pass, and the shader cache's warm list is precompiled. The clear moves
the first render pass's ~5.3 MB (the IOAccelerator floor, the driver's unmapped memory, some
malloc) from the first frame to `--frames 0`; it adds nothing after the first frame. Each
precompiled program costs about 40 KB of malloc. IOAccelerator's 3.8 MB is a floor: a bare
Metal program with one render pass gets 3.86 MB, held per device while any queue exists;
a Metal host already pays it.

**Text that changes every frame.** Ganesh keeps a GPU text blob (glyph sub runs, ~1 KB of system
malloc for a short label) for each SkTextBlob it draws until that SkTextBlob dies.
LibCompositing's display list resources cache the SkTextBlobs they make
(`DisplayListResourceStorage::text_blob`, up to 16 MiB counted). On a miss, at most once every 60
frames, they drop every blob unused for 60 frames, even under that cap (patch 0089). A frame is one
`retain_only` or `apply_transaction` on the storage (karouka's `prune_resource_storage` calls
`retain_only` whenever the display list changes), not a span of wall-clock time, so a headless run
at a thousand frames a second keeps no more blobs than a 60 Hz host. Without that sweep a counter
or clock, which never asks for an old blob again, would keep growing until the cap. Skia's
text blob cache budget is 1 MiB instead of Skia's 4 MiB (`src/engine/TextBlobCache.h`;
`KR_DEBUG=1` logs its use at `kr_system_destroy`). On a headless page of three labels rewritten
every frame, `mem --frames 2400 --malloc-history` finds 180 Ganesh text blobs (`sktext::gpu::TextBlob`,
60 frames of three labels, 0.14 MB) and a 4.0 MB system malloc zone (load 20-43).

**System fonts.** `Karouka::SystemUIFontProvider` (`src/engine/SystemUIFontProvider.h`) knows San
Francisco (upright and italic, every weight and width through its axes) plus the faces a host
registers (`kr_system_add_font*`). No font directory is read, indexed or mapped.

**The allocator.** Ladybird's mimalloc is built without `secure` (patch 0029): free lists extend by
4 blocks instead of 32. The idle trim (`trim_allocator_when_idle`, `src/engine/Engine.cpp`, after
30 idle host frames) collects the main thread's heaps and has every other thread that allocates
collect its own: the StyleLayout and Paint threads through `Web::Embedder::collect_stage_thread_heaps`
(patch 0030), and the pool threads through `Threading::ThreadPool::collect_idle_threads` (patch 0078),
which otherwise collect a second after their last job.
A page that never goes idle (an animation) has the StyleLayout, Paint and pool threads collect every
120 host frames with a rendering update or paint instead (`busy_opportunities_before_collect`); the
main thread doesn't, as it allocates every frame and its collect costs 1.3-2 ms. A thread purges the
pages it freed only when it next allocates or frees a page in the same segment, so on animated_churn
(headless, 1200 frames, sampled every 500 ms) the Paint thread held 29.4-30.8 MB of expired purges
for the whole run and all threads 31-43 MB; with the collect the Paint thread holds none after its
first and all threads 0-11.6 MB, mostly the main thread's purges not yet due. Those pages were
mostly not resident: footprint at exit 125.4-126.0 MB against 124.1-126.9 (medians 125.6 and 126.0),
`kmalloc_mb` 29.1-29.2 against 27.2-29.6, peak 127.0-127.7 against 127.1-128.3, CPU per frame the
same (11.70-12.41 ms against 12.12-12.82; 5 interleaved runs each, load 4-6, 2026-10-10).
The collect costs no frame time: paced at 60 fps (`--headless --fps 60 --frames 1200 --stats`,
6 interleaved runs a side, load 7-18), animated_churn's frame p95 is 11.68-20.00 ms (median 14.15)
with it, 12.15-18.66 (median 14.16) without (`KR_BUSY_COLLECT_FRAMES=0`) and 12.95-53.45 (median
13.73; one run caught a load spike) collecting every 10 frames; frame p50 10.56 / 10.14 / 10.40.
Collected every 10 frames, the frame that posts a collect and the next one (update + record + raster)
take a median 9.72 ms, mean 11.20 and p95 14.84 against 9.68, 11.07 and 14.99 for frames 4-9 after
it: a collect queues on the Paint thread ahead of the next frame's paint job and costs that frame
under 0.1 ms. Patch 0080's wait (a forced purge spins until another thread's purge ends) is on the
collecting thread, never the main thread, whose purges are unforced and skip. `KR_BUSY_COLLECT_FRAMES=N`
sets the interval, 0 turns the busy collect off.
The other threads that own mimalloc segments (karouka's GPU set-up thread, and on animated_churn one
more `Threading::Thread`) held no pending purges at any sample.
mimalloc purges on macOS with `MADV_FREE_REUSABLE`. Upstream 2.2.7 then reports the range as still
committed and writes to it again without `MADV_FREE_REUSE`, so the pages stay flagged reusable and
neither the footprint nor `kmalloc_mb` counts them (up to 17.8 MB on animated_churn) until the kernel
reclaims them. Patch 0077 overlays vcpkg's mimalloc port
(`Meta/CMake/vcpkg/overlay-ports/mimalloc`): on macOS a purged range needs a recommit, and the
recommit (`mprotect`) is followed by `MADV_FREE_REUSE`. That is two syscalls per reuse (~30 a frame
on animated_churn with `purge_delay` 0: 35.4 K commits in 1200 frames, against 40 K purges) and no
extra page faults: a page the kernel reclaimed refaults with or without it. System CPU 6.13 vs 6.06 s, user 13.47 vs
13.62 s over those 1200 frames. The empty page's footprint reads ~0.5 MB more for it at
`--frames 1` and ~0.4 at 600 frames, at the same RSS. With one fixed libkarouka and `purge_delay` 0, the vcpkg
mimalloc from before 0077 reads 21.06-21.08 MB at `--frames 1`, 0077's 21.60 and 0077 plus 0080's
21.55-21.56 (medians of 9 interleaved); at 600 frames 21.24 against 21.66 with 0077 and 0080
(medians of 5; load 9-12). The churn pages read ~18 MB more at 600 frames.
A huge block (over 16 MiB, a segment of its own) freed by a thread other than the one that allocated
it is reset with `MADV_FREE` instead (`_mi_segment_huge_page_reset`, untouched by 0077; so is the
unused prefix of an over-aligned huge allocation). That hides nothing from the footprint: macOS
keeps charging the pages until the owning thread frees the segment and the arena purges it with
`MADV_FREE_REUSABLE`, and a write before then needs no `MADV_FREE_REUSE`. They leave `kmalloc_mb`
at once (they are no longer dirty), so meanwhile `kmalloc_mb` reads the block's size under the
footprint. A standalone probe on the overlay's libmimalloc with karouka's options, 48 MiB: footprint
49.0 MB and `kmalloc_mb` 48.1 after the write, 49.0 and 0.1 after the free on another thread, 0.9 and
0.0 once the owner collects, and no dirty reusable pages at any step. No karouka page takes that
path: `MIMALLOC_SHOW_STATS=1` counts 0 resets on `pages/mem/huge_image_churn.html` (a new 22 MiB
decoded image each load, ~5 loads a frame; Metal and software), animated_churn, resource_churn,
canvas_2d, showcase and sashimi (200-300 frames, load 7-11), so each huge block is freed by the
thread that allocated it and its segment goes straight back to the arena (2.3-3.5 K purges in 200-300
frames). Footprint minus `kmalloc_mb`, sampled every 10 frames for 300 on the software backend, is a
median 13.4 MB (12.6-20.8) on huge_image_churn and 13.5 (12.7-18.5) on its control
`pages/mem/large_image_churn.html`, whose 15.3 MiB images stay in ordinary segments; on Metal
huge_image_churn reads 99.5-133.1 (median 101.6), the GPU cache's 75 MB included (load 5-8,
2026-10-11). Making the reset `MADV_FREE_REUSABLE` would bring back the hidden reusable pages:
a freed segment returns to its arena still marked committed, so a reuse before the arena purge
would write the pages without `MADV_FREE_REUSE`.
Patch 0079 sets `purge_delay` to 1 ms (mimalloc's default is 10; `MIMALLOC_PURGE_DELAY=0` purges at
once). A freed span is purged when its thread next allocates, frees or collects after the deadline, so
a busy page takes most freed pages back before they are purged. On animated_churn (headless, 1200
frames, 4 interleaved runs each, load 25-40) system CPU drops from 5.5-7.8 s to 2.6-3.0 s and CPU per
frame from 15.3-20.9 ms (15.3-16.7 without a run caught in a load spike) to 12.2-13.5 ms, for a peak footprint of 128-132 MB against 126 MB and
`kmalloc_mb` 29.3-33.4 against 27.0-27.2. Paced at 60 fps the saving is the same and it is all
on-CPU: `--headless --fps 60 --frames 1200 --stats`, 6 interleaved runs a side, load 4.2-8.3
(2026-10-11), delay 1 against delay 0 takes process CPU per frame from 12.61 ms (median;
12.25-13.88) to 11.05 (10.94-12.14) and system CPU from 4.50 s to 2.62 s, and retires 104.2 G
instructions against 110.6 G. The main thread does the saving: its own CPU per frame goes from
8.59 ms (8.40-9.39) to 7.10 (7.01-7.64), frame p50 from 10.32 to 8.79 ms and p95 from 11.60 to
9.74. Its off-CPU time per frame (frame wall less its own CPU) stays 1.93 ms (1.76-3.81) against
1.99 (1.79-3.86), p50 1.78 against 1.74: a purge and its recommit are syscalls on the thread that
frees and reuses the page, not waits. Purges and commits drop from 33.5 K each to 0.16-0.42 K and
0.27-0.80 K; peak footprint is 123.6 MB against 120.8 and `kmalloc_mb` at exit 25.1 against 19.9.
A thread that goes idle keeps the pages it freed until it
collects, so the idle trim reaches every thread: on `showcase_page.html` (600 frames, 13 interleaved
runs each, load 27-29) delay 1 ends at a mean 92.75 MB footprint against 92.81 MB at delay 0.
The delay costs the empty page ~0.4 MB footprint: with `MIMALLOC_PURGE_DELAY=0` it reads 21.7 MB at
`--frames 1` and 21.8 at 600 frames, against 22.2 and 22.2 back to back (load 98-121); resource_churn
reads 120.3 against 120.8 (medians of 3, load 23-39), inside its run-to-run spread.
Interleaved at load 9-12 (medians of 9) it is the same: 21.55 against 21.97 MB on the older
libkarouka above, 21.58-21.60 against 21.92-22.00 on main's.
A segment freed whole goes back to its arena, which purges the range 10 ms later (`purge_delay` times
`arena_purge_mult`) when any thread next frees a segment or collects. Upstream 2.2.7 inverts that
deadline check in `mi_arenas_try_purge` (`arenas_expire < now`), which left arena ranges to a forced
collect; patch 0080 fixes it in the overlay and has a forced purge wait for one running on another
thread instead of skipping it. On animated_churn (1200 frames) the arenas now purge 599-669 times
(12.7-14.3 GiB of ranges, mostly pages the segment purge already released) against 49-72 times
(60-88 MiB), at the same CPU and footprint: CPU per frame 11.29-13.56 ms against 11.21-13.13, peak
footprint 127.0-128.1 MB against 127.2-131.4 (5 interleaved runs each, load 5-7). The empty page,
`showcase_page.html` and resource_churn read the same on both sides too (2026-10-10).

**Long runs.** `prune_resource_storage` (Engine.cpp) keeps only what the display list still uses.
Decoded pixels count as live LibGC external memory (the image data cells report them),
which sets LibGC's next threshold. A document's image caches (its shared
resource requests and its list of available images) mark only the entries their prune would keep
if every image in use went away in that collection: the most recently used ones within 8 MB and 96
entries (patch 0081). Data in use is kept alive by its clients, so a collection that finalizes
replaced `<img>` elements frees their pixels in that same collection. `pages/tests/gc_image_reload.html`
holds this in `dev.sh check`: after a collection, exactly the newest 8 MB of 12 unused images still
complete synchronously when their URLs are requested again. Data that survives a collection
without clients is within the prune's limits, so nothing prunes after a collection: the prune runs
when an image finishes loading. LibGC's threshold is 1.75x a live set that includes the caches and
sweeps on a timer, so on its own it lets decoded pixels climb within a frame.
`LocalImageCodecPlugin` therefore also collects, swept, before a decode once decoded pixels have
grown by max(8 MB, 3/4 of the last floor), and once more if that freed no pixels. It then zeroes LibGC's allocated-since-last-collection count
(an oversized `did_free_external_memory`), which `collect_garbage()` leaves alone, so LibGC's own
threshold collections count from the trigger's. While the trigger is on, newly
decoded pixels don't count toward that threshold (`did_allocate_external_memory`): only the GC
cells allocated do. Counted, they reached it between triggers on every other batch of
animated_churn, 598 more collections per 600 frames at the same peak. With the trigger off
`LocalImageCodecPlugin` counts them as they decode, so LibGC's threshold doesn't run away.
Per 600 frames this costs 1198 collections on
animated_churn and 375 on resource_churn, both at a 16 MB peak (`KR_IMAGE_GC=0` turns the trigger
off: 150 collections and a 33 MB peak on resource_churn, 600 and 34 MB in 2400 frames; on
animated_churn 839 and 44 MB at load 4-6 but 762-1128 and 64-80 MB at load ~50; every count
deterministic). On animated_churn
every trigger collects once and leaves 5 MB: the shown 4 MB image and a 1 MB frame. Batches
alternate between 2 and 3 images (13 and 16 MB at the trigger). The 8 MB step is the low end of a
trade-off: a larger step cuts collections in proportion and raises the peak by about as much
(600 frames, `LIBGC_LOG_LEVEL=1` `Time spent` lines, every count deterministic, load 5-21).
`KR_IMAGE_GC_STEP_MB=N` sets the step to N MB (unset, empty or 0 keeps 8), so a sweep
needs no rebuild: `LIBGC_LOG_LEVEL=1 KR_IMAGE_GC_STEP_MB=12 tools/dev.sh run
pages/tests/animated_churn.html --headless --frames 600 --memory-stats`, counting `Time spent`
lines.

**What starts each collection.** `KR_GC_TRACE=1` prints `kr_gc_sources` at exit: the main thread's
collections by caller, read from the stack of a post-GC task that runs inside each one (the decode
trigger and its retry, LibGC's threshold from a cell or from external memory, its idle timer, a GC
deferral ending, other). `KR_GC_TRACE=2` adds a line per collection with
the decoded pixels left and those decoded and released since the last one. Per 600 frames (load
3.2-18, every count deterministic and equal to the `Time spent` lines):

| page | total | trigger | trigger retry | LibGC threshold | idle |
|---|---|---|---|---|---|
| resource_churn | 375 | 374 | 1 | 0 | 0 |
| animated_churn | 1198 | 1198 | 0 | 0 | 0 |
| resource_churn, `KR_IMAGE_GC=0` | 150 | 0 | 0 | 149 (external), 1 (cell) | 0 |
| animated_churn, `KR_IMAGE_GC=0` | 839 | 0 | 0 | 839 (external) | 0 |

On resource_churn each trigger fires at 16 MB, frees 8 MB of replaced images and leaves the 8 MB
the caches keep; the one retry is the first trigger, at 8 MB, when the caches held everything.
The showcase, animations and trellis demo pages run one collection each in 600 frames, from the
idle timer.
`kr_gc_sources` counts the trigger's collections at the frame boundary (after a render's submit,
or before the next advance's tasks) as `frame_boundary`: on resource_churn 75 of the 375, the
trigger 299.

| step | animated_churn collections / peak | resource_churn collections / peak |
|---|---|---|
| 8 MB | 1198 / 16 MB | 375 / 16 MB |
| 9 MB | 997 / 17 MB | 332 / 17 MB |
| 10 MB | 997 / 17 MB | 299 / 18 MB |
| 11 MB | 997 / 17 MB | 272 / 19 MB |
| 12 MB | 798 / 20 MB | 249 / 20 MB |
| 14 MB | 748 / 21 MB | 213 / 22 MB |
| 16 MB | 599 / 24 MB | 187 / 24 MB |
| 20 MB | 597 / 28 MB | 149 / 28 MB |
| 24 MB | 448 / 32 MB | 124 / 32 MB |
| 32 MB | 342 / 40 MB | 93 / 40 MB |

resource_churn's peak is the step plus 8 MB (1 MB images); animated_churn's moves on its 4 MB GIFs,
so 9-11 MB give the same 997 / 17 MB. GC time falls with the count (animated_churn 539 ms at 8 MB,
369 at 12, 197 at 32). Footprint follows the peak only loosely (one run each): 118-124 MB up to
14 MB, 120-131 at 16-20 and 135-152 at 24-32.
`decoded_images_peak`
(`--mem-phases-heap`, `--memory-stats`) is the high-water mark; phase samples alone land anyagainst
on that sawtooth.

## libkarouka's order file

`src/libkarouka.order` is the link's `-order_file` (`src/CMakeLists.txt`): the functions the empty
page runs first, in first-run order, then what each demo page adds, then the named data they read.
Each demo page replays scripted input: its own `karouka-check-input` meta when it declares one, else
`tools/orderfile.py`'s `DEMO_INPUT` (a wheel scroll, a mouse move across the page, a click and
down-arrow presses, as check's layout gates replay), so the input paths are recorded. Its window also
resigns key halfway through its frames and becomes key again in the next
(`karouka_viewer --blur/--focus`), so `kr_view_set_focused` and the unfocused paint it brings are
recorded. Each `# page:` line names the input that page replayed.
Literals are in `src/libkarouka_literals.c`, first on the link line. The empty page runs ~6805
functions, 4.99 MB of code. The committed file was recorded on 2026-10-11 and puts them
on 359 `__text` pages, against ~1060 without an order file. The ordering saves ~11 MB RSS on the
empty page and nothing in footprint: the pages it saves are clean.

`tools/dev.sh check` ends with `ok   order file (empty page on N __text pages, limit 400)`, or
warns (never fails) `WARN order file is stale` over `$KR_ORDERFILE_WARN_PAGES`. `tools/dev.sh
orderfile --stats [--data]` prints each page's code and data pages without writing; it takes pages
as arguments (a `pages/tests` page replays its own `karouka-check-input`), `--input FLAGS` in place
of `DEMO_INPUT`, `--fresh`, and `--tests`, which adds the `pages/tests` pages that declare a
`karouka-check-input` after the demo pages. The committed file traces the demo pages only. A stale file
costs pages, not correctness. To regenerate, on a checkout whose Ladybird tree is its own series:

1. `tools/dev.sh orderfile` builds, traces the empty page and the demo pages
   (`src/tools/ordertrace.cpp`, `tools/orderfile.py`) and rewrites both files: ~10 min at load ~100.
2. `tools/dev.sh check` relinks with it and should print `ok   order file` well under the limit.
3. Commit both files with the change that staled them, or as their own task after a patch wave.

**`__TEXT,__const` isn't ordered.** `orderfile --stats --data --unplaced` shows, per touched page,
whether its atoms are listed: in libkarouka's link the listed `__DATA_CONST,__const` atoms sit on
its first 24 pages, but the listed `__TEXT,__const` ones lie in object order over pages 1-63, so ld
applies none of the order file there (the empty page reads 34 of its 67 pages). A reduced link with
`-dead_strip` does order that section, `leaf.o:ltmpN` atoms included (without `-dead_strip` ld
ignores the order file for data). orderfile.py names an unnamed `ltmpN` atom by its object leaf
when the leaf is unique, and the committed file lists 47 of them; libkarouka's link
ignores them: the same file without them puts the empty page on the same `__text` and data pages.
A trace sees almost none of the reads of literals the literals file already packs together, so a
regeneration keeps the previous files' data and literals after the ones it traced, every
`__literalN` section included. Read `libkarouka.map` only under the build lock or from a snapshot of the
build (`dev.sh orderfile` reads its snapshot's): another checkout's link rewrites it.

## On disk

`python3 tools/bundle_size.py` reports sizes from the last build without building (`--section`,
`--rust` and `--dylib` for detail). On 2026-10-13:

- **libkarouka.dylib 53.47 MB:** `__TEXT` 33.11 (`__text` 30.86), `__LINKEDIT` 18.66, nearly all of
  it the symbol table. `strip -x` of it is 35.3 MB; `tools/dev.sh package` ships it that way, with
  a dSYM. Stripping changes neither RSS nor footprint.
- **`__text` by library:** LibWeb 14.84 MB (6.55 of it generated bindings, compiled `-Os` by patch
  0112), web_rust 8.32, LibJS 2.72, imagedecoders_rust 1.04, js_rust 0.81, everything else under
  0.35 each.
- **25 vcpkg dylibs, 23.16 MB:** ICU 10.4 (data 4.56 after trimming to root and English and
  leaving out the transliterators), libskia 5.51, harfbuzz 1.30, the image decoders'
  libraries, Brotli, libxml2 0.48 (push parser, tree and XPath only, patch 0114), and small ones.

Bytes on disk that an empty page never touches don't move its RSS or footprint. The prunes of
libcrypto, the content blocker, WebAssembly, ICU data, the HSTS list, cpptrace and
fontconfig/FreeType each left the empty page within ~0.4 MB of where it was.

## Open candidates

| What | Expected |
|---|---|
| the UA stylesheet as build-time read-only data: parsed blob, static atoms, static selector programs, precompiled dispatch | the style step's parse and compile |
| order file: the 35 `__TEXT,__const` pages ld doesn't order, the `*2` host-API entry points, a stale file failing check | clean RSS |
| ICU data: tr/az/lt/el casing (~70 KB) | disk |
| libexpat (0.18 MB) out of Skia | disk |
| the stripped package in `dev.sh check`, with its dylibs | |

Kept by decision, so not candidates: image formats and their decoders (AVIF, JPEG XL and the rest)
and font backends; the Brotli encoder; WebAudio and `window.internals`.

## Tried and rejected

- Deferring the warm-up's clear past `kr_system_create2`: it only moves bytes and costs the first flush ~1 ms.
- Fewer or smaller Metal queues, smaller targets, unretained command buffers for IOAccelerator: no change.
- Collecting the main thread's heaps right after the first advance: ~0.8 MB, not worth it.
- Exact-size CSS parser vectors: more size classes, more dirty pages; power-of-two reservations kept.
- Reporting decoded pixels to LibGC without the follow-up collection, or crediting pruned bytes in LibGC: no peak change.
- A collection every 16 MB of decoded pixels in the prune a finalized `<img>` queued, after the decode: no peak change on resource_churn. The trigger that works runs before the decode, at 8 MB (above).
- A forced `mi_collect(true)` every 600 frames on animated_churn: freed nothing.
- Collecting the shared partitions (layout, JS object storage, ArrayBuffer) on the thread that created
  them in the idle trim: they hold about 0.25 MB on `showcase_page.html`.
- Leaving the decode trigger's collection to the frame boundary up to twice the step
  (`KR_IMAGE_GC_CEILING=200`): resource_churn 299 collections, all at the boundary, at an 18 MB peak
  instead of 375 at 16; animated_churn decodes ~20 MB a frame, so 599 collections still land in the
  decodes, at a 24 MB peak instead of 1198 at 16, the 16 MB step's trade-off.
- `purge_delay` 10 or 50 ms instead of 1: the same or more peak memory on animated_churn.
