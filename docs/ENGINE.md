# Engine reference

How karouka drives LibWeb today, and the LibWeb behaviour that fails silently when you get it
wrong. Current behaviour only. Building, the build layout and the Ladybird patch workflow are in
`docs/BUILDING.md`; what `dev.sh check` verifies is in the comment at the top of `tools/dev.sh`.

## Engine map

| Where | What |
| --- | --- |
| `include/karouka/karouka.h` | The C API: system and view lifetime, host interface, fonts, load, input, focus, advance_time, render, IOSurface or host texture, capture, stats, data binding, the `engine` channel |
| `src/engine/Engine.cpp` `Karouka::PageClient` | The WebContent PageClient, locally: viewport, window focus (`kr_view_set_focused`: unfocused, selections paint in the palette's InactiveSelection and no caret or `outline: auto` ring draws, and a change fires blur or focus along the focus chain in a task, with the focused area left designated; the viewer follows its window's key state), `request_file` opens files, link navigation through `on_navigate` |
| `kr_system_create2` | Init order from `Services/WebContent/main.cpp`: event loop, resources, font and image plugins, VM, network-less ResourceLoader, Skia Metal context (none with `KR_BACKEND_SOFTWARE`). Metal device, shader cache and Skia context are made on a GPU thread alongside main-thread setup, then warmed up (`Karouka::set_up_gpu` in `HostMetal.mm`, `docs/STARTUP.md`); nothing on the main thread touches Skia's GPU context until it's joined. FontPlugin is built on a second thread |
| `src/engine/HostMetal.mm`, `ShaderCache.cpp` | The host's (or karouka's own) Metal device and queue as LibGfx's MetalContext, the GPU thread, and Skia's persistent shader cache (`kr_system_desc.shader_cache_path`) |
| `src/engine/HostInterface.cpp` | `kr_host_interface` inside the engine: the host clock for karouka's own timings, the log, and file loads routed to `kr_host_io` |
| `src/engine/SoftwareSurface.cpp` | Software backend: `PaintingSurface::wrap_bitmap` over the IOSurface's pixels, CPU rasterization (`--backend software`) |
| `src/engine/DisplayListCensus.cpp` | `KR_DEBUG_CENSUS=1`: what each display list asks of a player (`docs/COMMAND-LIST.md`; `tools/dev.sh census` tabulates it over the check pages). It counts every command in `ENUMERATE_DISPLAY_LIST_COMMANDS`, so a new upstream command appears without a change here (`pages/tests/canvas_2d.html` logs `FillRect=3 DrawCanvas=2`) |
| `src/engine/ShaderImage.cpp` | shader() images' pixels. `DrawEmbedderContent { dst_rect, content_id, is_live }` (patch 0101) is a display-list command whose pixels the embedder draws at replay: the player hands `content_id`, `dst_rect`, its canvas (set to the command's transform and clip) and the frame's host time (`set_caret_time_ns`) to its `EmbedderContentResolver`, here the system's `EmbedderContentRegistry`, which runs the painter registered under that id; no resolver or an unknown id paints nothing. `ShaderImages` compiles shader() SkSL with `SkRuntimeEffect::MakeForShader` (strict ES2), once per source text, and registers one painter family per shader whose content ids carry the raster scale's bits in their low 32 bits, so a changing scale adds no registry entries: LibWeb's `ShaderDecodedImageData` (patch 0102, `Libraries/LibWeb/Embedder/`) is vector content without a natural size, recorded as a one-command nested list whose content id comes from `Web::Embedder::set_shader_content_hook`, which the system points at its `ShaderImages`. The shader's coord is in CSS pixels from the destination's top-left; it gets `uSize` (CSS pixels), `uDevicePixelRatio` (the raster scale) and `uTime` only if it declares them. The recorder's destination rects are device pixels and its accumulated scale leaves out the device pixel ratio, so both background paths (`PaintRecorder::paint_vector_image` and the repeated-tile path in `paint/background.rs`) record a vector image without a viewBox, a shader() or an SVG, at the destination's CSS size and the ratio times that scale (patch 0111; `karouka_software_backend_test` checks both at scale 2). Its other uniforms are the author's, set by the image's arguments (below). A compile error, a child color filter or blender, a built-in uniform of another type or a uniform no argument can set (int, float3, a matrix, an array) paints nothing and logs one line (category `console`) per source. `uTime` is the frame's host time in seconds since the document's timeline origin (its `performance.now()`): the view sets the registry's time origin to the document's before each replay (`EmbedderContentRegistry::set_time_origin_ns`) and painters get the frame time less it. A shader that declares `uTime` is live: the hook (patch 0109) answers a `ShaderContent` whose `is_live` the recorded `DrawEmbedderContent` carries, so it draws at each frame's time with no style, layout or LibWeb paint, its bounds are damaged every frame, and the player never keeps a repeated tile holding it in its tile cache (`records_draw_live_embedder_content`; a background-size'd animated shader is a `DrawRepeatedTile` around the nested list). One without `uTime` is painted like a gradient and never rasterized again while it doesn't move (`pages/tests/shader_animation.html`, css-shader-image's M3 page, and `karouka_render_skip_test`). CSS `shader(<url> \| <string>)` (patch 0106) is an `<image>` wherever one is parsed (background-image, mask-image, list-style-image, border-image-source, content, image-set()): the Rust parser makes it a `StyleValueData::Image` whose `url_type` is 2 (`shader(url(...))`, the URL of an SkSL file) or 3 (`shader("...")`, the source text itself), and it serializes back as written (`getComputedStyle` gives the absolute URL). `ImageStyleValue` loads it through a `SharedResourceRequest` of kind `Shader`, from file: or data: only (the inline source goes as a base64 data: URL), keyed by the resolved URL with the fragment `#karouka-shader` so it never shares a request with an image of the same file; the fetched bytes become a `ShaderDecodedImageData`. With no natural size it fills its background positioning area or tile and a sized `content:` box, and takes the 300x150 default size as a list marker or as `::before` content, as a sizeless SVG does (`pages/tests/shader_image.html`). Uniform arguments `shader(<source>, --name <value>, ...)` (patch 0108) set `uniform name`: the parser takes a `<number>`, two space-separated numbers, a `<percentage>`, a `<length>` or a `<color>` per argument (after var() substitution; a name given twice or any other value makes the declaration invalid) and keeps them in the Image's `shader_arguments`, a comma-separated `ValueList` of dashed-ident and value pairs that serializes after the source and absolutizes as its values do (`0.0625em` computes to `1px`, colors to `rgb()`). `ImageStyleValue::Client::decoded_image_data` hands out the source's `ShaderDecodedImageData` bound to its arguments (`with_arguments`, one per client, with its own vector content identity, so a changed argument re-records only that image) as `Web::Embedder::ShaderArgument`s, which the hook passes to `ShaderImages`. It packs them by uniform name into `SkRuntimeEffect::uniforms()` offsets: a float or half takes a number, a percentage (divided by 100) or a length (CSS px), a float2 two numbers, a float4 a color (unpremultiplied RGBA in 0-1; `currentcolor` and `light-dark()` don't resolve there yet). A uniform with no argument or with one of another type paints nothing; an argument no uniform takes is ignored; each logs one line per source and set of arguments (`pages/tests/shader_uniforms.html`; `pages/tests/shader_plasma.html` is css-shader-image's M2 page on `plasma_still.sksl`, its plasma without `uTime`, where a var() argument changed by script damages only that element's box). A `uniform shader name` child is a canvas input, `--name element(#id)` (patch 0110): the parser keeps it as a `Function` named `element` around the id and serializes it back as written; `ImageStyleValue::Client::decoded_image_data` resolves it on every ask (so another context or a taint rebinds) to the `<canvas>`'s surface id in the canvas host's `CanvasSurfaceRegistry` (`ShaderArgument::Type::Canvas`), or refuses it (`RefusedCanvas`) when no element has the id, it isn't a canvas, it has no 2D context yet, it isn't origin-clean (as `getImageData()`), or it is inside the element the image paints for (each image observer of a layout node registers its element, `Embedder::set_image_client_element`). At replay the child samples the canvas's presented surface (`LocalCanvasHost::canvas_input`), one canvas pixel per CSS pixel of the shader's coord, transparent outside it. A refused, missing or mismatched input paints nothing and logs one line; so does a canvas whose 2D context draws a non-origin-clean image after binding (`Canvas2DContextBase::set_not_origin_clean` tells its transport, and the host refuses its pixels from then on). A shader with a canvas input is live, but unless it declares `uTime` its family doesn't depend on time: the registry's replay report (`EmbedderContentRegistry::Replay`) lists the canvases and content generations a frame sampled, and the view renders again only when one of them moves (`pages/tests/shader_canvas.html`, css-shader-image's M4 page, and `shader_canvas_still.html`). A page can't taint a canvas in karouka (a file: image is same-origin and nothing else loads), so the origin-clean refusal is exercised only by `karouka_embedder_content_test`. Each set of argument values is its own registry family, kept while the system lives, so an argument animated through var() adds a family per value it takes. `solid_color_test_content`, a color that changes each second, is the live test painter (`karouka_embedder_content_test` replays it and the shaders, `uTime` ones directly and as a repeated tile, on Metal and software). A nested display list holding the command is never cached as a raster |
| `src/engine/SystemUIFontProvider.h`, `HostFonts.cpp` | Font resolution and host-registered fonts (below) |
| `load()` → `Web::Embedder::load_html_in_place` (patch 0004) | Builds response and NavigationParams in place, `load_document`, activates the history entry, applies the history step |
| `kr_view_advance_time` | Steps the host clock to each timer deadline since the last advance, pumping the event loop at each (`step_host_clock_to`), then gives LibWeb one rendering opportunity. Marks the view dirty if LibWeb painted |
| `src/engine/HostEventLoop.cpp` | karouka's `Core::EventLoopManager`: the main loop runs only when `kr_view_advance_time` pumps it, never sleeps or polls; main-thread `Core::Timer`s fire on the host clock. Each pump first waits for awaitable thread-pool work (below) |
| `kr_view_render` | Records the display list and replays it with Skia into the IOSurface, or straight into a host texture (`kr_view_set_output2`, patch 0045; the view then has no IOSurface), then waits for the GPU unless the queue is the host's. Partial raster below |
| `src/engine/LocalImageCodecPlugin.cpp` | Synchronous in-process image decoding. Animated images stream: up to 8 frames decoded whole, longer ones keep a session and decode 4 frames per request. Once decoded pixels grew by max(8 MB, 3/4 of the last floor), collects, swept at once, and once more if that freed no pixels: before a decode, or at the frame boundary (after a render's submit, while the GPU draws, or before the next advance's tasks) when the frame's last decode took them past it (`KR_IMAGE_GC=0` turns it off, `KR_IMAGE_GC_STEP_MB=N` sets the 8 MB step, `KR_IMAGE_GC_CEILING=P` makes a decode wait for P% of the step and leave the rest to the boundary). Counts decoded pixels toward LibGC's own threshold only while that trigger is off. Counts `decoded_images` and its high-water mark `decoded_images_peak`. `KR_GC_TRACE=1` counts the main thread's collections by what started them, printed at exit as `kr_gc_sources` (`=2`: a line per collection) |
| `src/engine/WebFontGlyphs.cpp` | Warms the glyphs a page drew in a web font as soon as LibWeb makes that typeface, and its offscreen glyphs between renders (patch 0075; Fonts below) |
| `src/engine/Binding*.cpp`, `EngineChannel.cpp` | Data binding (`kr_binding_*`, `data-bind-*` attributes, applied by DOM mutation with no script) and the page/host `engine` message channel (`kr_view_engine_*`); `include/karouka/karouka.h` documents the contract |
| `src/engine/ScriptTypes.cpp` | Embedder `<script>` types (non-JavaScript ones, e.g. `<script type="text/x-example">`): each view's handlers by MIME essence (`kr_view_set_script_type_callback`, or `Karouka::set_script_type_handler` from C++). Patch 0099 runs such scripts on the classic-script path and calls `Engine.cpp`'s one `Web::Embedder::ScriptTypeHandler`, which finds the view by the document's page. `Karouka::set_active_document_handler` and `Karouka::active_document` let a C++ embedder linked from the engine's objects follow each view's top-level document (for example to tear down a per-document interpreter) |
| `src/engine/LegacyEntryPoints.cpp`, `StructSize.h` | Public structs are versioned by a leading `struct_size`; the unsuffixed entry points serve hosts built against older headers |
| `src/viewer/main.mm` | The viewer: test and bench flags, headless mode, Pages menu, `HudGame` (drives `hud_page.html`'s `data-bind-*` model from C) |

## Partial raster

A paint or visual-animation frame is diffed against the last rasterized one (`frame_damage`,
LibCompositing's `compute_display_list_damage`). Nothing changed in the viewport: the surface is
kept (`render skipped` in `KR_DEBUG`). Otherwise the frame replays into its damage alone, up to 8
rectangles (pieces whose union grows by at most 128×128 px are merged first), one replay each under
a plain rectangle clip. Don't clip to an `SkRegion`: Ganesh turns it into a path clip (~0.15 ms CPU
and ~0.12 ms GPU a `hud_page` frame). A damage over a quarter of the viewport goes through
`DamageSplitter`, which diffs halves of the display lists down to small pieces, unless a tree has a
filter or backdrop filter (they read neighbouring pixels) or a list is over 2 MB of commands.

- A nested scroller's offset change damages its content's old and new bounds. Canvases, video, a
  blinking caret and live embedder content (`DrawEmbedderContent` with `is_live`; patch 0101's
  damage diff never finds one unchanged) damage their own bounds every frame, and so does a nested
  display list (an SVG or shader() image) that holds one at any depth or has visual animations
  (`nested_display_list_is_live`, memoized per list id), as does a command whose records inside it
  hold one (an isolated group's content, a repeated tile: `command_is_live`). Any other nested list is damaged only when
  its `PaintNestedDisplayList` changes: lists are immutable under their id. A compositor
  background-color animation damages the fills naming its effect node (patch 0066 compares the sampled colors).
- What a live shader() costs a frame (one with `uTime`, or a canvas input whose canvas moved): its
  bounds replay whole every frame, so the frame pays to re-rasterize everything drawn in them, over
  and under the shader, plus the shader once per device pixel. Figures at 1280x720, scale 1, load
  10-45, from `pages/perf/shader_*.html` (`--stats`):
  - The shader itself. Metal runs it on the GPU: the main thread only records one draw (0.2-0.8 ms
    CPU a frame whatever the shader), and the GPU spends ~0.3-0.4 ms on a full-viewport constant or
    plasma shader, ~5 ms on a 512-iteration `sin` loop. The software backend runs it on the main
    thread in Skia's raster pipeline: 3-4 ms a frame for a constant, 20-24 ms for plasma, 2.6-2.8 s
    for the 512-iteration loop (~3 us a pixel).
  - What is drawn over it often costs more. Five paragraphs with a `text-shadow` over a live
    full-viewport constant shader: ~210 ms a software frame and ~4 ms GPU plus 2-3 ms CPU on Metal,
    because every line's shadow blur is redone each frame; plasma under it adds only its own shader
    time. Without the shadow the same text adds 0-2 ms (software) and nothing measurable (Metal).
  - A shader without `uTime` or a canvas input is rasterized once, like a gradient: the
    512-iteration loop over the viewport costs its first frame ~2.9-3.1 s on software and ~8 ms more
    GPU on Metal, and no frame after it renders.

  The SkSL compiler runs only when a shader() image is first recorded (`ShaderImages::compile`, once
  per source text). The empty page never constructs one, on either backend; on Metal, Skia's own
  blur and color-filter effects compile SkSL when a page draws a shadow or a filter.
- Loads, resizes, new targets and document scrolls raster whole. `KR_FULL_RASTER=1` turns partial
  raster off; `kr_view_stats.last_raster_pixels` says how much a frame rasterized.
- `kr_view_render` runs under its own autorelease pool (`Core::ScopedAutoreleasePool`): Skia's
  Metal backend autoreleases its command buffers and a C host's frame loop never drains a pool, so
  without one every frame's command buffer leaks. `kr_view_capture_png` (Skia's readback),
  `kr_view_resize` and `kr_view_destroy` (freeing the IOSurface's Metal texture autoreleases the
  device) and `kr_system_destroy` have one too, and so do `kr_system_add_font2`,
  `kr_system_add_font_file2` and `kr_system_set_default_font` (CoreText's font registry and a
  locale). `karouka_autorelease_test` counts what each public call leaves in the caller's pool and
  fails on any: the Metal, font, load and reload, binding, engine-channel and `kr_io_complete`
  calls, with and without a host io. A new entry point that drives Skia's GPU context, Metal or
  CoreText outside an event-loop pump needs a pool and a line there.

## Clocks and timers

- Everything on the main thread runs on the host clock: `Platform::Timer`s (patches 0025, 0043),
  `Core::Timer`s (`HostEventLoop.cpp`, LibGC's sweep and idle-GC timers included),
  `performance.now()`, and `Date`/`Temporal.Now` and LibWeb's wall clock (patch 0049: the Unix time
  at `install_host_clock` plus host time since), and LibWeb's other "now" readers through
  `Embedder::monotonic_now()`/`unix_now()` (patch 0076: main-thread smooth scrolls, the wheel
  latch, `File.lastModified`, cookie expiry, media/FileReader event throttles). The caret blinks on
  the host clock: its cycle starts at the shared clock's time, the player takes the frame's
  (`set_caret_time_ns`), and a view whose last frame drew a blinking caret renders again when it
  shows or hides (`caret-blink` render reason; LibWeb doesn't paint for a blink). Live embedder
  content (shader() images) draws at the same frame time, and a view whose last frame drew some
  in the viewport (`draws_live_embedder_content_in_viewport`, skipped while no content is
  registered: one below the fold or scrolled away keeps nothing rendering) renders again at each new
  host time (`shader` render reason); one whose last frame drew only canvas-sampling shaders without `uTime`
  renders again when a canvas they sampled presents new pixels instead. Media never plays
  (`LADYBIRD_MEDIA_STUB`). Still on real clocks: instrumentation timings, fetch/HTTP-cache times
  and EventSource reconnects (none reaches a capture). `kr_system_desc.real_time_clock`
  (`--real-time`) doesn't install the host clock.
  A timer you add on the wall clock fires at a frame that depends on machine load: a headless frame
  of a static page takes ~40 µs.
- The host clock fires each timer at most once per move (patch 0021), and an HTML timer whose
  firing is still queued drops the next one. So `kr_view_advance_time` steps to each deadline
  (`next_host_clock_deadline`, `event_loop_next_timer_deadline`), at most 1000 steps an advance; a
  longer jump fires deadlines within 1/1000 of it together. `kr_view_stats.event_loop_pumps` and
  KR_DEBUG's `pumps=` count the pumps; `karouka_host_clock_pumps_test` pins an idle 1 s advance.
- Within a task the host clock stands still, so each read a window's script makes of it takes a
  fixed 1 µs step (patch 0050, `Embedder::read_host_clock_for_script`): a 100 ms busy wait ends
  after ~100 000 reads on every run. LibWeb's own reads (event timestamps, rAF, timers) stay on the
  host's time and can lag `performance.now()` after a long wait.
- LibWeb runs one task per event-loop pump. `step_host_clock_to` pumps the tasks left from the last
  frame (up to 32) at its last step before the frame, not at the frame's own time (an idle period
  starting there would already be at its deadline), and a timer deadline's step pumps once per
  queued task (up to 32) before the 8 for the timers' own tasks. The budget is the system's, shared
  by its views: a test page that queues hundreds of tasks at once (140 image loads) holds back
  another view's task chains, and four views to a system its neighbour fails (data_url_image
  loaded 17 of 20). `pages/tests` pages spread such bursts over frames.
- Off-thread work is awaited (patch 0051): an external script's compile, a stylesheet's parse and
  a web font's preparation are submitted as awaitable thread-pool work, and every main-thread pump
  waits for it first, so what it posts back lands on the same frame every run
  (`karouka_script_frame_test`). `--real-time` doesn't wait. Other pool work (a module's remaining
  functions, the bytecode cache, media) is not awaited.

## Fonts

One system font: San Francisco, upright and italic, all weights and widths through its axes.
Every generic family and every family a page names without @font-face resolves to SF;
`system-ui`/`ui-*`/`-apple-system` too (patch 0031). There is no system glyph fallback: a code point
the cascade doesn't cover renders as SF's .notdef, so CJK, Arabic and emoji need a page font. Only
SF's files are mapped; FontPlugin is built on a thread during `kr_system_create2`.

Hosts add fonts per system, not per view (`kr_system_add_font2`, `kr_system_add_font_file2`), as
glyph fallback (`KR_FONT_FALLBACK`), or as the default family (`kr_system_set_default_font`). A face
answers to its family name ahead of SF and to `local()` by full or PostScript name. All of it
reaches live documents (`FontComputer::did_load_font`, and patch 0037's `did_change_system_fonts`
for the default family), except a `local()` that failed before the face existed. Viewer flags:
`--font PATH[=FAMILY] --fallback-font PATH --default-font FAMILY`; `karouka_font_registration_test`.

Glyphs rasterize ~1px heavier than their outlines (CoreText font smoothing); `--font-hinting none`
(`KR_FONT_HINTING=none`, patch 0057) turns it off, and `tools/wpt.py` passes it, as reftests compare
glyph edges.

With a shader cache and the GPU backend, the glyphs a view's first frames drew in web fonts, and the
ones their display lists held offscreen, are kept in `<shader_cache_path>.glyphs`. When LibWeb next
makes that typeface (an @font-face rule's or a `FontFace`'s, patch 0075), a worker warms the drawn
ones before the next render and the offscreen ones between later renders (`WebFontGlyphs.cpp`;
`KR_WEBFONT_GLYPHS=0` turns it off). What is and isn't warmed: `docs/STARTUP.md`.

## LibWeb pitfalls (each fails silently)

- Set the page's system visibility to `Visible` **before** creating the traversable, or the
  document is hidden: no rAF, no CSS animations.
- LibWeb marks the whole document for repaint on any layout commit or text/child change; only the
  recorded display list tells whether a paint is visible.
- Without a compositor, the paint step only clears `needs_repaint`. The event loop's
  `rendering_scheduler_counters().paints` is the "frame changed" signal.
- Pass `document->scroll_state_snapshot()` to `DisplayListPlayerSkia::execute`, or pages render
  unscrolled.
- The parser doesn't start until the document is "ready to run scripts", set by
  `update_for_history_step_application`, which needs the navigation API entries.
- Wheel input scrolls the document synchronously when there's no compositor context. A wheel
  gesture latches its first target; patch 0052 latches the nearest element with a layout node, not
  a Text node, and clears the latch when dispatch drops the event.
- `page_did_create_new_document` fires for every Document (top-level, DOMParser) before its
  Window has its Document: define properties on the Window, not through `globalThis`
  (`EngineChannel::install`).
- No frames: `kr_system_create2` turns child navigables off (patch 0100,
  `Embedder/ChildNavigables`), so a view has one document and one Window. An iframe, frame or
  object element stays in the DOM, but `NavigableContainer::create_new_child_navigable` does
  nothing: it loads no document (no load event for one, a srcdoc's script never runs),
  `contentDocument` and `contentWindow` are null, `window.length` is 0, and it paints as an empty
  box. An object whose resource is a document shows its fallback content, though its `data` is
  still fetched to learn the type. `PageClient` brokers no child navigation and answers no history
  operation (`pages/tests/iframe_inert.html`).
- A pointer event's hit test reads compositor-driven animations at the compositor's samples
  (patch 0071), so a mouse move over a running animation doesn't restyle its targets or lay out.
- file: URLs have a tuple origin `("file", "", null)` (Ladybird's `--tuple-file-origins` setting,
  turned on in `kr_system_create2`), so module scripts load from file: pages; `self.origin` is
  `"file://"`. Storage throws QuotaExceededError on file: pages.
- Scheme fetch serves file: URLs only to a client with a file: origin, and upstream only to
  requests with a destination (subresource loads), never to `fetch()`. Patch 0092
  (`Embedder/FileFetch`) adds `Web::Embedder::set_fetch_reads_file_urls`, which
  `kr_system_create2` turns on, so a file: page's `fetch()` reads local files
  (`pages/tests/fetch_file_url.html`).
- "Prepare the script element" ignores a type that isn't JavaScript, `module` or `importmap`.
  Patch 0099 (`Embedder/ScriptTypes`) asks the embedder's `ScriptTypeHandler` about any other
  type's MIME essence for the document; an accepted one becomes a "classic" script whose result is
  an `EmbedderScript` (UTF-8 text, URL, line) instead of a `ClassicScript`, so parser blocking,
  `defer`/`async` ordering, `currentScript` and `load`/`error` are upstream's. Its `src=` is fetched
  as a no-cors script request and decoded as UTF-8. `execute_script` runs the handler between
  "prepare to run script" and "clean up after running script"; false fires `error` instead of
  `load`. `HTMLScriptElement.h` is untouched (it's widely included).
- Canvas 2D gets its backing store from a `CompositorHost`, which karouka doesn't have: without
  one, drawing is dropped and `getImageData` reads zeros. Patch 0090 (`Embedder/LocalCanvas`) lets
  `Karouka::LocalCanvasHost` (`src/engine/LocalCanvas.cpp`, set by `kr_system_create2`) hand out
  the transport instead. It replays the shared command stream on the main thread with the system's
  Skia context (the CPU on the software backend) when LibWeb flushes it: at a readback, when
  pending commands pass LibWeb's limit, and at each rendering update's present markers, which copy
  a canvas's draw surface to its presented surface in the host's `CanvasSurfaceRegistry`.
  `kr_view_render` resolves `DrawCanvas` against that registry. A canvas costs
  two surfaces of its size (draw and presented), GPU memory with the Metal backend, counted as
  `canvas` (`KR_MEM_TAG_CANVAS`, `kr_view_stats.canvas_bytes`, `dev.sh mem --attribute`). LibWeb
  passes the host the page each canvas belongs to (patch 0098), and `kr_view_destroy` drops that
  page's canvases at once instead of waiting for a collection to finalize their contexts, including
  surfaces made with no script running (an `OffscreenCanvas`'s at its placeholder commit, a
  `contextlost` restore). The host also keeps `transferControlToOffscreen()` placeholders
  (patch 0094): each rendering update that follows a draw into the `OffscreenCanvas` commits a copy
  of its presented surface under the placeholder's id (a third surface, counted as `canvas`), and
  the canvas element, told at once, moves its content generation so that update's paint redraws
  it, and takes the frame's size in a task. A page's placeholders go with `kr_view_destroy`
  too. Only a window's `OffscreenCanvas` commits (workers are pruned). Not
  hosted: WebGL (pruned). A canvas without backing storage serializes as transparent pixels of its
  size in `toDataURL()` (patch 0035). `pages/tests/canvas_2d.html`, `data_url_image.html`,
  `offscreen_placeholder.html`.
- `Page::enable_primary_paste` defaults to on (an X11 selection clipboard; Ladybird's macOS build
  turns it off). `kr_view_create2` turns it off: left on, every selectionchange (each click) lays
  the document out to read the selected text. Mouse entry points that find only style pending
  update style first and lay out only if that left layout unclean (patch 0074), so a click on a
  static page runs no layout pass (`pages/tests/click_active_style.html`).
- The page palette (`PageClient` in `Engine.cpp`) sets only the window and
  base colors, `Selection` and `InactiveSelection` (Ladybird's `Default.ini` values). A role left
  at 0 is transparent: without `Selection`, selections in a page's normal color scheme don't paint.
  `PageClient` has focus unless `kr_view_set_focused` took it, so the page paints `Selection`
  focused and `InactiveSelection` unfocused. `pages/tests/script_selection.html` and
  `window_focus.html` pin both colours' paint.
- `kr_view_set_focused` fires its blur or focus events along the spec focus chain
  (`Web::HTML::focus_chain`): losing focus, blur and focusout at the focused field, then blur at
  the window; gaining focus, the same in reverse, focus and focusin in place of blur and focusout.
  `tests/view_focus_test.c` pins the order.
- Every event dispatched at a Window has the Window's document as its `target` (and
  `srcElement`): `HTML::Window::dispatch_event` always passes the legacy target override flag to
  `EventDispatcher::dispatch`, which the spec sets only for `load`, `unload`, `pageshow` and
  `pagehide`. So `e.target === window` is false for `window.dispatchEvent(...)`, `resize`,
  `message`, focus and blur at the window, and every other window event; `e.target ===
  document` is true. `currentTarget` and `composedPath()` give the WindowProxy (`=== window`).
  Listen on the window and test `currentTarget`, or compare `target` with `document`. The
  bindings aren't at fault: the `[DirectGetter]` fast path bails out on global objects and the
  generated getter maps a Window to its WindowProxy.
- `LocalImageCodecPlugin::decode` hands LibWeb the decoder's `color_space()` (the cICP chunk, else
  the ICC profile). LibWeb tags every frame with it and Skia converts to the sRGB surface; left
  default, tagged images draw unconverted. A profile the decoder rejects draws as sRGB.

## Ladybird's image tests

`tools/dev.sh libweb` (`tools/libweb_tests.py`) runs the 272 Text
and 91 Ref tests in Ladybird's `Tests/LibWeb` that touch images. Text: 181 pass, 86 need internals
karouka lacks, 1 never reports, 4 fail. Ref: 84 pass, 1 within tolerance, 5 need internals, 1
fails. Every failure is accepted, and listed with its status in `tests/libweb/known_failures.txt`, the
run's ratchet; by cause:

- `createImageBitmap-invalid-args`: the video sources never load (media is a no-playback stub,
  patch 0007) and the Blob source
  comes from `XMLHttpRequest`, which is pruned.
- `pixel-length-attributes`: all 546 subtests pass. Ladybird's expectation lists 588: its imported
  copy dropped the 42 `<body rightmargin>`/`<body bottommargin>` subtests and the expectation
  wasn't regenerated.
- `elementFromPoint`: differs from Ladybird's expectation in its iframe subtest.
- `naturalWidth-naturalHeight-width-height.tentative`: 51 of 228 pass, the expectation has 56,
  and 25 subtests differ in both directions. The pin's unpatched code (`HTMLImageElement::
  natural_width`, `SVGDecodedImageData::natural_size`) reports 0 for an SVG with a negative width
  or height and a viewBox, which the expectation passes as 300x100.
- Ref `contain-size-013` renders right, but its reference is `.xht`. Every top-level file loads as
  HTML (`Web::Embedder::load_html_in_place`), so the reference's CDATA-wrapped style is dropped
  (as in WPT's `large-scroll-margin-001`).
- Ref pages that set state through `internals` (no stand-in there): `force-dark-inverts-images-like-fills`
  (`setForceDarkEnabled`), `object-fit-with-zoom-*` (`setBrowserZoom`) and
  `svg/preferred-color-scheme-normal` (`setPreferredColorScheme`).
- `cors/image-tainting-in-cross-origin-iframe.sub` never reports: there is no `.sub` substitution.
