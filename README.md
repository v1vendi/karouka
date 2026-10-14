# karouka

A UI renderer for apps and games that turns an HTML/CSS/JS page into a GPU texture, built from
[Ladybird](https://ladybird.org)'s engine instead of written from scratch. karouka reuses a full
browser engine (LibWeb, LibJS, LibGfx/Skia) and strips away what a browser needs and a UI layer
doesn't: networking, process isolation, session history, storage and media. It runs on macOS on
Apple silicon.

## What it is

- **One process, one thread, no IPC.** The work Ladybird's WebContent process normally gets from
  other processes is done locally: navigation (`src/engine/Engine.cpp` `load()`), image decoding
  (`LocalImageCodecPlugin`) and compositing (`kr_view_render` replays the display list with Skia).
- **No networking.** `ResourceLoader` runs without a RequestServer (patch 0002). `file:`, `data:`
  and `about:` load; `http(s)`, WebSockets and DNS prefetch fail.
- **Output is an IOSurface** (BGRA8, premultiplied) that the host wraps as an `MTLTexture`, or binds
  as a GL rectangle texture with `CGLTexImageIOSurface2D` (see `kr_view_iosurface`), or reads on
  the CPU as BGRA bytes and a row stride (`kr_view_lock_pixels` / `kr_view_unlock_pixels`). A host
  that passes its own `MTLDevice` and command queue (`kr_system_desc.mtl_device`/`mtl_queue`) can
  instead have a view draw straight into one of its textures (`kr_view_set_output2`), and
  `kr_view_render` then doesn't wait for the GPU.
- **Host interface** (`kr_host_interface`): optional callbacks for file IO (pages from pak files or
  a virtual file system), karouka's own timing clock and the log, which carries the pages'
  `console.*` output.
- **C API** in `include/karouka/karouka.h`. Its frame loop: inject input, advance time, render.
- **Embedder script types** (`kr_view_set_script_type_callback`): the host runs `<script>` types
  other than JavaScript itself, on HTML's classic-script path, so pages can carry scripts in
  another language.

## Layout

| Path | What |
| --- | --- |
| `third_party/ladybird/` | Ladybird, a git submodule pinned at `1a9bd18fc4` |
| `patches/ladybird/` | The patch series applied to it (`tools/apply_patches.sh`) |
| `include/karouka/karouka.h` | The public C API |
| `src/engine/` | The embedder: page client, loading, frame loop, rendering |
| `src/viewer/main.mm` | `karouka_viewer`, the macOS demo viewer |
| `src/viewer/EventInput.h` | NSEvent to `kr_input_event`, for the viewer and other AppKit hosts |
| `pages/` | Demo and test pages (`pages/README.md`) |
| `tests/` | The test executables `tools/dev.sh check` runs; `tests/wpt/` holds the WPT corpus pin and ratchet lists |
| `bench/` | `compare.py`, the timing harness behind `tools/dev.sh bench` (karouka alone, or two builds A/B) |
| `bench/engines/` | The same page in karouka, Ladybird, Electron, Tauri and TinyJS: startup, CPU, memory (`perfcmp.py`, `setup.sh`) |
| `docs/` | `BUILDING.md` (build layout, Ladybird patch workflow), `ENGINE.md`, `MEMORY.md`, `STARTUP.md`, `COMMAND-LIST.md` |

## Quickstart

Requirements: macOS on Apple silicon with Xcode or the Command Line Tools, plus the Homebrew
packages `tools/dev.sh bootstrap` checks for: `autoconf autoconf-archive automake ccache libtool
nasm ninja pkgconf llvm` (the build compiles with Homebrew's clang). Qt isn't needed: karouka's
build leaves out Ladybird's `UI/` (the Qt browser). Only a build with `LIBWEB_PRUNE_WEB_APIS=OFF`,
which builds the browser too, needs Homebrew's `qt`.

From a clone of this repository:

```bash
git submodule update --init third_party/ladybird
tools/dev.sh bootstrap
tools/dev.sh build
tools/dev.sh run         # the start page (pages/index.html)
```

## Build

The first build compiles Ladybird's libraries and their vcpkg dependencies, which takes a while
even at 4 jobs; afterwards `third_party/ladybird/Build/` holds about 5 GB. Every command:

```bash
tools/dev.sh bootstrap   # CMake 3.30+, Ladybird's pinned Rust and sccache into .toolchain/ (leaves Homebrew's alone)
tools/dev.sh ladybird    # patch, configure and compile only the Ladybird libraries karouka links
tools/dev.sh build       # patch, configure, build the Ladybird libraries, karouka, the viewer and tests
tools/dev.sh run [page]  # build, then open the page, or the demo picker (pages/index.html)
tools/dev.sh check       # build, then unit tests, a WPT subset, every test and demo page, startup gate
tools/dev.sh startup     # build, then only check's kr_system_create2 startup gate
tools/dev.sh mem [page]  # build, then peak RSS + footprint, 5 headless 600-frame runs (default: empty)
tools/dev.sh mem --all-demo   # the same for every demo page, as a table (mem --list names them)
tools/dev.sh bench       # time karouka on the demo pages (bench/compare.py)
tools/dev.sh bench --save before; ...; tools/dev.sh bench --ab before current   # A/B two karouka builds
tools/dev.sh wpt         # build, then the vendored WPT reftests and testharness.js tests, ratcheted
tools/dev.sh libweb      # build, then Ladybird's own Tests/LibWeb image tests, ratcheted (tools/libweb_tests.py)
tools/dev.sh census      # build, then docs/COMMAND-LIST.md's display-list census over the check pages
tools/dev.sh orderfile   # build, then re-record libkarouka's link order file (src/libkarouka.order)
tools/dev.sh package [DIR]   # build, then the stripped dylib, its dSYM and the headers a host ships
tools/dev.sh patches [--reset]   # apply this checkout's patches/ladybird/ series to the shared tree
tools/dev.sh own         # take the shared Ladybird tree before editing it (docs/BUILDING.md)
tools/dev.sh release     # give the tree back once its patches are saved
```

The comment at the top of `tools/dev.sh` describes each command and its options. Builds run at
`nice 10` with 4 jobs. Set `KR_JOBS` to change that. `check` runs its test executables and
renders 3 at a time (`KR_CHECK_JOBS`, at most `KR_JOBS`). `tools/readme_sync.py` (run by `check`)
checks that this README lists every patch, `dev.sh` command and viewer flag in the tree, and nothing
else.

### How the build is wired

karouka doesn't add Ladybird to its own CMake project. Patch 0003 adds a hook to Ladybird's
top-level `CMakeLists.txt` that builds karouka's `src/` (`-DKAROUKA_SOURCE_DIR`) from inside the
Ladybird tree, so the engine compiles with exactly Ladybird's toolchain, flags and library targets.
The outputs are in `third_party/ladybird/Build/release/karouka/{bin,lib}`. Git worktrees of this
repository share the main checkout's Ladybird tree and build directory (`docs/BUILDING.md`, Build
layout), which also describes how to change Ladybird through the patch series.

### Patches

| Patch | Why |
| --- | --- |
| `0001` | `VM_MEMORY_APPLICATION_SPECIFIC_2` fallback for SDKs older than macOS 26 |
| `0002` | `ResourceLoader::initialize_without_network`: no RequestServer, so `http(s)` loads fail at once |
| `0003` | The CMake hook that builds karouka's `src/` inside Ladybird's tree |
| `0004` | `Web::Embedder::load_html_in_place`: loads a page into a traversable without a navigation. It lives in LibWeb because the types it builds (`NavigationParams`, `PolicyContainer`, `load_document`) aren't exported from the library |
| `0005` | Drops LibTLS/libssl and LibDatabase/sqlite (the disk cache) from LibWeb's link |
| `0006` | `HTMLImageElement`'s batching timer is 0 ms, so batched `<img>` loads run at the next pump instead of after a 1 ms wall-clock wait |
| `0007` | LibMedia/LibMediaClient as a no-playback stub without ffmpeg |
| `0008` | Build option and bindings-generator support for leaving Web API families out of LibWeb |
| `0009` | Leaves out IndexedDB and WebSockets |
| `0010` | Leaves out WebDriver |
| `0011` | Leaves out Web Speech and the Cookie Store API |
| `0013` | Leaves out the Navigator extensions |
| `0014` | Leaves out Notifications |
| `0015` | Halts the thread pool and LibWeb's stage threads so `kr_system_destroy` leaves no threads behind |
| `0016` | The bindings generator drops union alternatives whose interface was left out |
| `0017` | Leaves out WebGL, Geolocation, EME, XMLHttpRequest and StorageManager |
| `0018` | A pruned LibWeb build leaves out the browser UI, WebContent and WebWorker, which need the pruned families |
| `0019` | Picks the Metal device with `MTLCopyAllDevices`, without a WindowServer handshake |
| `0020` | Builds Skia's CoreText font family list only when something enumerates families |
| `0021` | `Web::Embedder` host clock: `performance.now()`, animations and HTML timers follow the time the host passes |
| `0022` | Folds an opacity layer over a single fill into the fill |
| `0023` | LibRequests' 256 KiB `thread_local` read buffer is heap-allocated on first use |
| `0024` | Compositor-run transform/opacity animations sample the shared (host) clock |
| `0025` | `Platform::Timer` runs on the host clock |
| `0026` | Bounds an opacity layer that can't be folded to its ink rect |
| `0027` | Leaves out Service Workers |
| `0028` | Leaves out Media Source Extensions and Media Capture |
| `0029` | vcpkg builds mimalloc without the `secure` feature |
| `0030` | `Web::Embedder::collect_stage_thread_heaps`: the style/layout and paint threads collect their mimalloc heaps when the host is idle |
| `0031` | `system-ui` and the `ui-*` families resolve through the embedder's font provider, not straight to CoreText |
| `0032` | Cuts the CSS parser's allocation churn: reserved vectors, smaller tokens, one top-level rule at a time |
| `0033` | Right-to-left text keeps its order without wrapping, and numbers in it stay left to right |
| `0034` | Skips the root isolation layer when nothing reads the destination |
| `0035` | A canvas without a compositor host (no backing storage) serializes as transparent black instead of reporting no pixels |
| `0036` | Lays out at event-loop step 19 only when something invalidated layout |
| `0037` | `FontComputer::did_change_system_fonts`: a host default font set after load reaches live documents |
| `0038` | Leaves `PathFontProvider` out when the embedder provides fonts |
| `0039` | Leaves the MediaServer IPC out of builds without a media server |
| `0040` | Reorders line fragments across elements and fonts (line-level bidi) |
| `0041` | The thread pool starts threads as work arrives, not all four at once |
| `0043` | `Document`, `LocalNavigable` and `font-display` timers run on the host clock |
| `0044` | Parses the 170 rarely used predefined counter styles on first use instead of in every document's UA sheet |
| `0045` | `PaintingSurface::create_from_metal_texture`: draws straight into the host's texture |
| `0046` | A rendering update lays out only when something invalidated layout |
| `0047` | vcpkg leaves ffmpeg out of media-stub builds |
| `0048` | Pruned builds leave the browser's vcpkg dependencies out |
| `0049` | `Date` reads follow the host clock (`JS::Temporal::set_host_wall_clock`) |
| `0050` | Each script read of the host clock takes a fixed 1 us step, so busy-waits end |
| `0051` | `ThreadPool::submit_awaitable`: the host can wait for off-thread compiles before a pump, so script timing doesn't depend on machine load |
| `0052` | A wheel gesture that starts over text latches to its element, not the Text node |
| `0053` | Containment on `<html>` or `<body>` keeps the body's background off the canvas, and the surface's clear color agrees |
| `0054` | A grid container's absolutely positioned children take their static position and `justify-self`/`align-self` from its content box |
| `0055` | `clip-path: <basic-shape> <geometry-box>` clips in the box given, border-box by default |
| `0057` | The hinting override (`KR_FONT_HINTING`, `--font-hinting`) applies to Skia fonts on every platform, so `none` turns off CoreGraphics' glyph dilation on macOS |
| `0058` | Idle thread-pool threads exit; `submit()` starts another when work comes, and `halt()` joins the retired ones |
| `0059` | Pruned builds leave libpsl (with libidn2, libunistring) out: `PublicSuffixData` answers from the `*` rule alone |
| `0060` | Pruned builds leave out WebCrypto's SubtleCrypto and CryptoKey: `crypto.subtle` is undefined; `getRandomValues`/`randomUUID` stay |
| `0061` | `LIBCRYPTO_COMMONCRYPTO`: LibCrypto keeps big integers, ASN.1 and SHA-1/SHA-2 (over CommonCrypto), and OpenSSL leaves the link and vcpkg |
| `0062` | Pruned builds leave the content blocker's Rust engine (adblock, with psl, regex, aho-corasick) out of the link: `ContentBlocker` filters nothing and setting rules fails |
| `0063` | Pruned builds leave out WebAssembly and link LibWeb without LibWasm: `typeof WebAssembly` is "undefined" and an `application/wasm` module script fails to import |
| `0064` | ICU's data keeps root and English plus the locale-independent data (33.4 MB to 5.7 MB); other locales fall back to en-US |
| `0065` | A wheel step or viewport scroll lays out only when something invalidated layout |
| `0066` | The damage diff compares the colors compositor background-color animations were sampled at, so a moving one repaints |
| `0067` | Pruned builds leave Chromium's HSTS preload list (3.7 MB) out: `HSTSPreloadData` knows no host |
| `0068` | Mouse, key and scroll entry points, and script reads of scroll state, lay out only when something invalidated layout |
| `0069` | Pruned builds leave cpptrace, libdwarf and zstd out: assertion backtraces come from `backtrace(3)` |
| `0070` | Pruned macOS builds install Skia without fontconfig and HarfBuzz without FreeType: libfreetype, libfontconfig and libbz2 leave the link, and glyphs rasterize through CoreText only |
| `0071` | A pointer event hit-tests compositor-run animations at the compositor's sample time, so its layout update needn't sample them on the main thread |
| `0072` | A user-agent style rule whose every selector needs an element type is compiled only once such an element arrives |
| `0073` | CSS parser tokens shrink from 112 to 88 bytes, and the token vector is reserved at two fifths of the source length, so it doesn't double |
| `0074` | The mouse down/move/up and activation entry points settle style first, and skip the layout pass when that style left layout as it was |
| `0075` | `Web::Embedder::set_web_font_typeface_created_callback`: LibWeb tells the embedder when it makes a web font's typeface (an @font-face rule's, or a `FontFace`'s from URLs or a BufferSource), so karouka can rasterize the font's glyphs ahead of the render |
| `0076` | LibWeb's remaining readers of the monotonic and Unix clocks go through `Web::Embedder::monotonic_now()`/`unix_now()`, the host clock once installed: a caret's blink cycle, main-thread smooth scroll steps, the wheel-gesture latch, media and FileReader event throttles, `File.lastModified`, `document.lastModified`, cookie expiry. `DisplayListPlayerSkia::set_caret_time_ns` lets the embedder say when a frame's caret shows |
| `0077` | vcpkg's mimalloc port is overlaid: on macOS a purged range is recommitted before reuse, with `MADV_FREE_REUSE`, so the footprint counts the pages written again |
| `0078` | `Threading::ThreadPool::collect_idle_threads()`: idle pool threads collect their kmalloc heaps on request, not a second after their last job; karouka's idle trim asks |
| `0079` | AK's mimalloc purges freed pages 1 ms after they are freed on macOS, not 10 |
| `0080` | The mimalloc overlay purges arena ranges once their deadline passes (2.2.7's check is inverted), and a forced purge waits for a concurrent one |
| `0081` | A document's image caches (shared resource requests, list of available images) mark only the entries their prune would keep if every image in use went away, so a collection that finalizes a replaced `<img>` frees its decoded pixels too |
| `0083` | A pending `@import` blocks scripts, as it blocks rendering, and the parser resumes when the last one loads. `Web::FileRequest` carries the URL's query, so the host sees a `file:` URL's `?...` |
| `0085` | LibJS's Rust crate builds without its `debug-dump` feature in karouka: no native disassembler (iced-x86), AST dump or bytecode dumper, and the LibJS dump flags print nothing |
| `0086` | karouka's LibCore compiles the unimplemented geolocation provider and links neither CoreLocation nor CoreServices |
| `0088` | Rust crates build without an extra `--emit=dep-info`, which made sccache skip each build's top crate |
| `0089` | LibCompositing's text blob cache drops blobs unused for 60 frames (on a miss, at most once every 60 frames) even under its 16 MiB cap, so text that changes every frame doesn't grow it to the cap. Ages count frames (each `retain_only`/`apply_transaction`), not wall-clock time, so a headless run keeps as few blobs as a 60 Hz host |
| `0090` | `Web::Embedder::LocalCanvas2DHost`: an embedder without a compositor hosts canvas 2D; karouka replays the command stream in-process, so canvases paint and `getImageData`/`toDataURL` read what was drawn |
| `0091` | The font computer forgets the font cascades no computed style holds once its memo doubles past what it kept last time (and more than 64), so a page that animates `font-size` doesn't keep a cascade, with its typeface and HarfBuzz objects, for every size it passed |
| `0092` | `Web::Embedder::set_fetch_reads_file_urls`: requests without a destination (`fetch()`) may read `file:` URLs, still only from a `file:` client; karouka turns it on |
| `0094` | `LocalCanvas2DHost` also keeps `transferControlToOffscreen()` placeholder canvases: each rendering update commits the `OffscreenCanvas`'s frame to the host, and the canvas element paints it, reads it back and takes its size |
| `0095` | A style group reclamation is also due once the live computed font groups reach twice what the last one left (at least 32), so the groups holding unused cascades go and patch 0091's trim can forget them |
| `0096` | A typeface keeps at most 32 sized fonts (was 129), and when full it evicts one only the cache holds before falling back to any |
| `0098` | `LocalCanvas2DHost::create_canvas_2d_transport` and `allocate_placeholder_canvas` take the page the canvas belongs to, so the host can drop a page's canvases even when their backing storage was made with no script running |
| `0099` | `Web::Embedder::set_script_type_handler`: `<script>` types the embedder accepts per document (`text/x-example`, say) run on the classic-script path (parser-blocking, `defer`/`async` order, `src=` fetched, `currentScript`, `load`/`error`) through the embedder's handler; karouka's `kr_view_set_script_type_callback` |
| `0100` | `Web::Embedder::set_child_navigables_enabled`: with child navigables off, an iframe, frame or object never gets a content navigable, so it loads no document, `contentDocument` and `contentWindow` are null and it paints as an empty box; an object whose resource is a document shows its fallback content. karouka turns them off: a view has one document |
| `0101` | `DrawEmbedderContent { dst_rect, content_id, is_live }`: a display-list command whose pixels the embedder draws at replay through `DisplayListPlayerSkia::set_embedder_content_resolver` (content id, rect, canvas, frame time); live content never diffs as unchanged and keeps a nested display list from being cached as a raster; `DisplayListResourceStorage::draws_live_embedder_content` finds it at any depth (for shader() images) |
| `0102` | `DecodedImageData` answers vector content itself (`is_vector_content`, `vector_content_identity`, `has_active_view_box`, `record_display_list_at_scale`; the SVG image overrides them, and paint facts and the Rust bridge no longer cast to it); `Web::Embedder::ShaderDecodedImageData`, a shader() image recorded as one `DrawEmbedderContent` whose content id the embedder's `set_shader_content_hook` gives |
| `0103` | `border-image-source` paints SVG images, other vector content (shader() images) and gradients, not only raster frames: the source is recorded once at its natural size, or the border image area when it has none, and each of the nine slices draws that one recording clipped to its part and scaled onto its tiles, under stretch, repeat, round and space |
| `0106` | CSS `shader(<url> \| <string>)`: parsed as an `<image>` (a `StyleValueData::Image` with `url_type` 2 or 3), serialized back as written, and loaded through a `SharedResourceRequest` of kind `Shader` (file: and data: only, kept apart from image requests for the same URL) into a `ShaderDecodedImageData` |
| `0108` | shader() uniform arguments: `shader(<source>, --name <value>, ...)` parsed, serialized, var()-substituted and absolutized in the Image's `shader_arguments`, bound to the image's `ShaderDecodedImageData` and passed through the shader content hook |
| `0109` | Animated shader() images: the shader content hook answers whether the content is live (`ShaderContent`), recorded as `DrawEmbedderContent::is_live`, and the player never keeps a repeated tile that draws live embedder content in its tile cache |
| `0110` | shader() canvas inputs: `--name element(#id)` parsed (a `Function` named `element` around the id) and serialized back; `ImageStyleValue`'s client resolves it on each ask to the `<canvas>`'s surface id (`ShaderArgument::Type::Canvas`) or a refusal (no element, not a canvas, no context, not origin-clean, inside the element the image paints, which `Layout::Node`'s image observers name); a 2D context that loses origin-clean tells its transport (`RemoteCanvas2DTransport::did_become_not_origin_clean`) |
| `0111` | Vector images without a viewBox in CSS pixels: the background recorder (`PaintRecorder::paint_vector_image` and the repeated-tile path) divides the device-pixel destination by the device pixel ratio and multiplies the ratio into the raster scale, so a shader()'s coord and `uSize` and an SVG's layout are CSS pixels at any backing scale, and a canvas input samples one canvas pixel per CSS pixel |
| `0112` | A build that prunes Web APIs (`LIBWEB_PRUNE_WEB_APIS`) compiles LibWeb's generated bindings, exposed-interface and StructuredSerialize sources with `-Os`: libkarouka's `__text` 2.06 MB smaller |
| `0114` | libxml2 overlay port with only the push parser, tree building, entities and XPath (no HTML, C14N, catalog, debug, modules, output, pattern, reader, regexps, SAX1, schemas, validation, writer, XInclude, XPointer, iconv or zlib): LibXML feeds it UTF-8 from memory. libxml2 1.22 MB to 0.48 MB, linking only libSystem |
| `0115` | `text-transform: full-width`, `String::to_fullwidth` and `Utf16String::to_fullwidth` map through a table in LibUnicode (`FullwidthMapping.cpp`: 224 code units and 28 katakana + sound-mark compositions, what ICU's Halfwidth-Fullwidth transliterator does), so libicudata keeps no transliterator data (5.68 MB to 4.56 MB) |

## Viewer

```bash
karouka_viewer [page.html] [--size WxH] [--scale N] [--frames N] [--headless] [--fps N]
               [--capture out.png] [--stats] [--scroll DX,DY[@F|@A..B]]
               [--poke X,Y@F] [--move X0,Y0:X1,Y1@F[xSTEPS]] [--key VK@F[..L]]
               [--blur F]... [--focus F]... [--hold]
               [--second page2.html]... [--input-view N] [--close-second F]
               [--mem-phases] [--mem-phases-heap] [--memory-stats] [--no-render]
               [--host-io sync|async] [--host-log trace|debug|info|warn|error] [--host-clock]
               [--real-time] [--doc-root DIR] [--verbose] [--check-title]
               [--max-layouts-per-frame N[@F]] [--engine-gpu] [--output-texture]
               [--backend metal|software] [--shader-cache PATH | --no-shader-cache]
               [--capture-again N:out.png] [--check-full-raster]
               [--print-meta NAME] [--no-reload] [--live-reload] [--testharness]
               [--font PATH[=FAMILY]]... [--fallback-font PATH]... [--default-font FAMILY]
               [--font-hinting none|slight|normal|full]
```

`karouka_viewer --help` prints the flags, and the comment at the top of `src/viewer/main.mm`
explains each. The ones that show what a host can set:

| Flag | Does |
| --- | --- |
| `--host-io sync\|async` | Routes file loads through the viewer's `kr_host_io` callbacks, completed inside the request (sync) or at the start of the next frame (async) |
| `--host-log LEVEL` | Routes the log (page console output and karouka's diagnostics) through `kr_host_log`, from LEVEL up |
| `--host-clock` | Gives karouka the viewer's monotonic clock through `kr_host_clock`, for its own timings (`kr_view_stats`); the page's clock stays the time the viewer passes to `kr_view_advance_time` |
| `--verbose` | Without `--host-log`, prints the pages' console output to stderr (`kr_system_desc.verbose`) |
| `--real-time` | The page's clock is the system's monotonic clock (`kr_system_desc.real_time_clock`), so busy-waits on `performance.now()` end |
| `--engine-gpu` | karouka makes its own Metal device and queue and waits for the GPU in `kr_view_render`, instead of using the viewer's |
| `--output-texture` | Headless: draws each view into a viewer texture and checks it against a reference view's IOSurface |
| `--backend software` | Skia's CPU rasterizer; no Metal device headless |
| `--shader-cache PATH` | Keeps the GPU programs Skia builds in PATH between runs (`kr_system_desc.shader_cache_path`); the default is `~/Library/Caches/karouka/skia-shaders.bin`, and `--no-shader-cache` compiles every program each run |
| `--font-hinting MODE` | Sets `KR_FONT_HINTING` before the engine starts: every glyph rasterizes with that Skia hinting (`none` for reftests, which compare glyph edges) |

For tests and measurement, `--headless` needs `--frames N`, which steps the page's clock 16.67 ms
a frame (so a run depends on N only); `--fps N` paces a headless run to N frames a second of real
time, `--key VK@F` presses macOS virtual key VK in frame F, and `--testharness` runs a WPT
testharness.js document headless and prints its report (`tools/wpt.py`). `--capture`, `--stats`,
`--verbose` and the scripted input flags are the debugging tools.

With no page given, the viewer opens `pages/index.html`, and links on it work. In a window it
reloads a page when one of its files changes (`--no-reload` turns that off). The **Pages** menu
switches pages from anywhere:

| Keys | Does |
| --- | --- |
| Cmd+0 | Start page |
| Cmd+1, Cmd+2, … | The demo pages the start page links to, in its order (seven: Cmd+1 to Cmd+7) |
| Cmd+Shift+] / Cmd+Shift+[ | Next / previous page: start page, those demo pages, then the test pages (wraps) |
| Esc or Cmd+[ | Back |
| Cmd+R | Reload, keeping the scroll position |

Test pages are listed under Pages → Test Pages. With several views (`--second`), the menu acts on
the view clicked last.

## Status

Every demo and test page renders headless and in the viewer, and `tools/dev.sh check` passes.
Data binding, the `engine` message channel, and the Metal, software and OpenGL outputs are done.

`tools/dev.sh wpt` on the vendored subset, 2026-10-09:

| Suite | Pass |
| --- | --- |
| Reftests | 620 of 692 (89.6%) |
| testharness.js subtests | 3424 of 3599 (95.1%), in 320 documents (re-run 2026-10-11) |

Memory, startup and on-disk size, with how to measure each and where the bytes and milliseconds
go: `docs/MEMORY.md` and `docs/STARTUP.md`. Work still open: feature parity, memory and speed,
removing unused code from the link, engine follow-ups, host integration (an Unreal Engine plugin, a
Skia GL backend, routing Ladybird's own and worker console output to the host log), tooling and the
viewer.

## License

BSD-2-Clause, see `LICENSE`. Ladybird (`third_party/ladybird`, with karouka's patches in
`patches/ladybird/`) is BSD-2-Clause. The vendored WPT subset in `third_party/wpt/` is under its own
license (`third_party/wpt/LICENSE.md`).
