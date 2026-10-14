# Command-list output

**Decision (2026-10-08): keep Skia (option a). Don't build a command-list player (option b) now.**
The revisit triggers are at the end; if the first one fires before a port, the cheap bridge
(option c) comes first.

## Question

A UI renderer for games can avoid touching the GPU itself: it emits a backend-neutral command list
(textures, vertex batches and a small fixed set of shaders: SOLID, SDF_BOX, GLYPH, TEXTURE, MASK,
BLUR, COLOR_MATRIX, BLIT, BLEND_COMPOSITE) that a game-side backend runs on whatever graphics API
the game uses. karouka rasterizes Ladybird's display list with Skia, so it can only reach the
graphics APIs Skia reaches, and it owns a GPU context to do so.

The options:

- **(a)** Keep Skia and offer one output per graphics API.
- **(b)** Write a `DisplayListPlayer` that translates Ladybird's display list into such a command
  list.
- **(c)** A bridge that emits a one-draw command list: the software raster as a texture.

## Where karouka's output stands

| Host | How it gets a frame |
| --- | --- |
| Metal | IOSurface, or a host MTLTexture it renders straight into (`kr_view_set_output2`) on the host's queue |
| No GPU / CI | Skia CPU raster into the IOSurface (`KR_BACKEND_SOFTWARE`) |
| OpenGL on macOS | Samples the IOSurface zero-copy (`CGLTexImageIOSurface2D`), with either backend |
| Vulkan via MoltenVK | Can import the IOSurface (`VK_EXT_metal_objects`); not documented or tested |
| D3D, console APIs, non-macOS | none: karouka is macOS-only (IOSurface and Metal types in `karouka.h`, CoreText fonts) |

On the only platform karouka runs on, every host API already gets a frame without a new raster
path. Backend independence pays off only on another OS, or for a host that wants to draw karouka's
UI through its own renderer: its own batching, shaders or render graph.

## Feasibility of (b): what the code allows

- **A non-Skia player needs no Ladybird patch.** `Compositing::DisplayListPlayer` is exported
  (`COMPOSITING_API`) and abstract (`LibCompositing/DisplayList/DisplayList.h:34-97`). It declares
  one pure-virtual `play_command` per command (36 in `ENUMERATE_DISPLAY_LIST_COMMANDS`, 8 of them
  compositor metadata that `execute_command_bytes` never plays), plus `set_matrix`/`canvas_matrix`,
  `push_clip`, `push_clip_path`, `push_transform`, `push_layer`, `push_mask`/`pop_mask`, `pop` and
  `push_device_space_plane_clip`. The visual-context-tree walk (Rust, `execute_impl`) turns clips,
  transforms, effects and masks into those calls. `src/engine/DisplayListCensus.cpp`
  subclasses it from karouka's own code, links, and replays every page below. A new upstream command
  becomes a compile error in such a subclass, not a silent gap.
- **`execute` requires a `PaintingSurface`** (`DisplayList.cpp:346`, `VERIFY(m_surface)`). A
  command-list player has to pass a placeholder; the census passes the view's surface. That's
  cosmetic.
- **Resources are reachable without the GPU, but partly Skia-typed.**
  `DisplayListResourceStorage::font(id)` returns a `Gfx::Font` and `image_frame(id)` returns a
  `DecodedImageFrame` with a bitmap: enough for glyph atlases and texture uploads. Text blobs,
  images and nested-list raster caches come out as `sk_sp<SkTextBlob>`/`sk_sp<SkImage>`
  (`DisplayListResourceStorage.h:147-154`). Fonts are `SkTypeface`-backed, so rasterizing glyphs
  for an atlas still goes through Skia, on the CPU.
- **Filters arrive as serialized bytes** that only `Gfx::to_skia_image_filter`
  (`LibGfx/SkiaUtils.h:144`) decodes. The format is LibGfx-internal. A command-list player needs its
  own decoder (blur, drop-shadow, color matrices; SVG filter chains don't map to a small fixed
  shader set) or a CPU fallback.
- **The interface churns.** In the six months to the pinned commit (2026-04-06 → 10-06), 103 commits
  touched the player interface and command headers (`LibWeb/Painting/DisplayList{,Command}.h` and
  their `LibCompositing/DisplayList/` successors after the 2026-09 move; the commands are now
  generated from Rust). `DisplayListPlayerSkia.cpp` changed on 48 distinct days. Every Ladybird
  bump would need a karouka-owned player kept in step, and nothing upstream would test it.

## Command coverage (measured)

`KR_DEBUG=1 KR_DEBUG_CENSUS=1 karouka_viewer PAGE --headless` logs, before each rasterized frame,
what the display list asks of a player: commands by type, plus the replay calls and features a
command list would have to express. `tools/dev.sh census` (`tools/census.py`) runs it over every
page `dev.sh check` renders and prints the karouka column below, the drawing commands never seen,
the busiest frames and the S3+S4 coverage; `--input` adds each page's scripted input. Two corpora:

- **karouka's pages**, measured 2026-10-11 with `tools/dev.sh census`: the 56 pages `dev.sh check`
  renders (8 demo, 48 test), 60 frames each, without the scripted input some of them declare
  (with it, FillRoundedRectRing gains one page, click_active_style). A frame that changed nothing
  isn't rasterized, so a static page logs one or two censuses. `pages/tests/border_image_vector.html` (measured alone
  2026-10-12) is counted only in the row of the three commands no other page records. The census
  also covered one more demo page that is no longer in the tree, so a few per-command counts below
  may be one higher than a fresh run gives.
- **The vendored 692-document WPT reftest subset** (`third_party/wpt/`), measured 2026-10-08: 10
  frames, software backend, 800x600.

| Command / feature | karouka pages using it (max per frame) | WPT documents | Command-list mapping | Difficulty |
| --- | --- | --- | --- | --- |
| FillRect | 56 (75) | 692 | SOLID quad; non-normal blend → BLEND_COMPOSITE + BLIT | easy |
| DrawGlyphRun | 34 (499 runs, 7193 glyphs) | 616 | GLYPH over an R8 atlas rasterized by Skia CPU from the `Gfx::Font` | medium |
| FillRectWithRoundedCorners | 14 (102) | 3 | SDF_BOX | easy |
| FillRoundedRectRing (borders) | 14 (100) | 94 | SDF_BOX; dashed, dotted and per-side styles → paths | medium |
| PaintLinearGradient | 3 (36) | 11 | TEXTURE with a 256×1 LUT, `p0` = t | easy |
| PaintRadialGradient, PaintConicGradient | 1 (1), 0 | 0 | per-pixel t that TEXTURE can't interpolate: CPU-baked texture | medium |
| PaintOuter/InnerBoxShadow | 4 (24), 1 (6) | 6 | SDF_BOX shadow, or offscreen + 2× BLUR | medium |
| PaintTextShadow | 1 (28) | 11 | glyphs to offscreen, 2× BLUR, TEXTURE | medium |
| FillPath, StrokePath (dashes 1 page) | 3 (8), 1 (1) | 5, 7 | tessellate to SOLID with an AA fringe, or Skia-CPU coverage → MASK | hard (tessellate) / easy (coverage) |
| DrawLine | 5 (20) | 12 | SOLID quad; dotted/dashed → paths | easy |
| DrawScaledDecodedImageFrame | 6 (3) | 0 | TEXTURE, texture lifetimes via resource ops | easy |
| PaintScrollBar | 3 (5) | 5 | SOLID / SDF_BOX | easy |
| DrawCanvas | 3 (2): canvas_2d (2 canvases), offscreen_placeholder (2), fetch_file_url (1) | 0 | TEXTURE from the canvas's own Skia surface (`CanvasSurfaceRegistry`, by `canvas_id`); the canvas's drawing stays Skia's, so the texture is read back or shared each time the canvas changes | medium |
| PaintCaret | 1 (1): caret_blink_clock | 0 | SOLID quad, shown or hidden by the blink time | easy |
| DrawEmbedderContent (patch 0101) | 1 (7): `pages/tests/shader_image.html`, measured alone 2026-10-12; only a shader() image's nested list (patch 0102) records it. The same page is the only one to record DeclareMaskContent, 1 (1), for its shader() mask-image | 0 | pixels the embedder draws at replay (shader() images): the player hands `content_id`, `dst_rect`, its canvas and the frame time to an `EmbedderContentResolver` (`src/engine/ShaderImage.cpp`); a command-list player would need the content as its own draw (an SkSL program becomes a fragment shader) or as a TEXTURE drawn each frame by Skia, since `is_live` content changes with the time while the command doesn't | hard |
| DrawTiledDecodedImageFrame, DrawRepeatedTile, PaintNestedDisplayList | 1 (9), 1 (74), 1 (51): border_image_vector (border-image from a PNG, from SVGs and from gradients) | 0 | per-tile quads (TEXTURE samples clamp-to-edge); an offscreen tile repeated as a TEXTURE; recursion into the nested list | medium |
| never seen: DrawRepeatedDecodedImageFrame, DrawCompositedContext (no iframes), DrawEllipse, DrawRect, DrawIsolatedGroup, BackdropFilterRegion, DrawVideoFrame | 0 | 0 | per-tile quads (TEXTURE samples clamp-to-edge); recursion; offscreen groups; external textures | easy to hard |
| set_matrix (spatial nodes) | 56 (74) | 692 | CPU vertex transform, or `mvp` uniform; projective in 0 | easy (affine) |
| push_clip rect / rounded / difference | 11 (74) / 6 (37) / 0 | 48 / 1 / 1 | SET_SCISSOR under scale-translate; otherwise MASK over an R8 coverage target | medium |
| push_clip_path, plane clips | 0, 0 | 7, 0 | MASK | hard |
| push_layer (all opacity) | 7 (72) | 2 | offscreen target + TEXTURE × opacity, or fold into vertex alpha | medium |
| layer blend / filter / backdrop, masks | 0 | 0 | BLEND_COMPOSITE, BLUR/COLOR_MATRIX, BLIT + BLUR, MASK | hard |

What the corpora say:

- **Coverage.** 16 of the 29 drawing commands occur at all. FillRect, glyphs, rounded rects and
  rings make up nearly every command on the game-UI pages (restyle 734 commands at most in a
  frame, sashimi 529, trellis 387).
- **Cost of a useful subset.** Rects, rounded rects, rings, lines, glyphs, linear gradients,
  images, carets, opacity layers and scissor clips (S3 and S4 below) cover 47 of the 56 karouka
  pages completely. That includes only 4 of the 8 demo pages: animations, demo, hud and
  demo_index. The other four demo pages:
  - trellis needs rounded clips;
  - restyle needs paths, dashes and rounded clips;
  - sashimi needs a shadow, paths and rounded clips;
  - showcase needs a radial gradient, shadows and rounded clips.

  The five test pages left over: hover_rows needs shadows and rounded clips, ua_rules_late_elements
  a path, canvas_2d, offscreen_placeholder and fetch_file_url DrawCanvas. So every game-UI demo page needs S5 or S6.
- **Untested features.** Neither corpus has a blend mode, filter, backdrop filter, mask, 3D
  transform or isolated group, so a command-list player's hardest stages would have no local test
  pages. The pages are far from a budget of under 150 draws for a complex menu, so the player would
  need a batcher.

## Cost of (b)

**Basis.** A command-list layer from paint entries to a batched command list (tessellation,
effects, a glyph cache and atlas, a batcher, the list builder, shapes and paths, validation and
serialization) is on the order of 6,000 lines. Box-decoration geometry stays on Ladybird's side of
the line. karouka would translate Ladybird's commands into that machinery, and would also own a
filter-bytes decoder and the Skia-CPU fallback.

| Stage | Content | Est. lines | Patch |
| --- | --- | --- | --- |
| S0 | Census player (`DisplayListCensus.cpp`) and the coverage numbers above | 250 | no; **done** |
| S1 | A command-list header; `CommandListPlayer` skeleton; vertex/index/uniform arenas; resource ops (texture lifetimes keyed by resource id); a C API to fetch a view's list; a test that runs it through a software backend and compares with the Skia capture within `CHECK_SOFTWARE_TOLERANCE` | 1,200 | no |
| S2 | **Fallback first:** any command or subtree S3–S7 don't cover is rasterized by Skia CPU into a texture and drawn with TEXTURE, so every later stage ships pixel-correct | 300 | no |
| S3 | Rects, SDF rounded rects and rings, lines, scrollbars, carets, affine transforms on the CPU, scissor clips, opacity layers, images, linear-gradient LUTs, batching | 1,500 | no |
| S4 | Glyph atlas (Skia CPU masks from `Gfx::Font`, shelf packer, R8 updates, eviction) and GLYPH draws | 900 | no |
| S5 | Shadows (SDF and BLUR), text shadow, radial and conic gradients baked to textures | 800 | no |
| S6 | Paths: fill, stroke, dash, rounded and path clips as MASK (Skia-CPU coverage first, tessellation later if the upload cost shows) | 600–1,500 | no |
| S7 | Effects: blend modes (BLIT + BLEND_COMPOSITE), filter-bytes decoder → BLUR/COLOR_MATRIX, backdrop filters, masks, isolated groups, nested lists, repeated/tiled images, canvas and composited-context surfaces as textures, 3D transforms through `mvp` | 1,500 | no; the filter decoder may want an upstream accessor |

**Total.** About 6,000–7,000 karouka-owned lines in 10–14 reviewable tasks. Add a standing
maintenance cost: the 103 interface commits in six months have to be tracked on every Ladybird
bump.

**Runtime.** The display list would be rebuilt into vertices every rendered frame, on the CPU, where
Skia's GPU path now batches on its own. Glyphs, paths and any fallback would still be rasterized by
Skia on the CPU, and uploaded. **Memory.** The only certain saving is the GPU context: the empty
page's RSS was 41.1 MB on Metal and 37.7 MB on the software backend. Skia itself stays
linked.

## (a) per-API Skia contexts

LibGfx already has Vulkan (`USE_VULKAN`), Direct3D 12 (`USE_DIRECTX`) and Metal contexts
(`SkiaBackendContext.h:40-50`), with wrap factories for VkImage (dma-buf) and D3D shared textures
(`PaintingSurface.h:65-71`). They are all behind non-macOS defines.

- **On macOS, (a) is complete:** Metal, software and GL-through-IOSurface.
- **Vulkan and D3D12** come with a port, as part of it: IOSurface would be replaced by dma-buf or a
  D3D shared handle, and CoreText by a font provider. The output side of such a port is mostly
  upstream code.
- **Skia GL** is not built on macOS and isn't needed there.

## (c) a one-draw command-list bridge

For a host that has a command-list backend and wants to point it at karouka, emit, per frame:

- a CREATE_TEXTURE (RGBA8, once);
- an UPDATE_TEXTURE with the software raster;
- one TEXTURE draw.

It's patch-free, about 200–300 lines plus an ABI addition, and it costs one upload a frame (1.9 MB
at 800x600, plus a BGRA→RGBA swizzle unless the backend's format list has BGRA8). It gives no
batching or shader control: it only plugs karouka into the backend contract. Build it only when such
a host exists; it's also stage S2's degenerate case.

## Recommendation

**Keep Skia (a).** On macOS every host API already gets a frame. The only reason to take on (b) is
a host that must own the draw calls; (b) costs ~6–7k lines plus permanent upstream tracking, and
half its stages have no test content.

Revisit when any of these happen:

1. A real host asks to consume karouka through a command-list backend, or through its own render graph.
   Build (c) first, then (b) S1–S4, which cover 47 of 56 pages (4 of 8 demo pages), with S2's
   fallback for the rest; S5–S6 for the demo pages.
2. A Windows, Linux or console port is scheduled. Do (a) with LibGfx's Vulkan/D3D12 contexts as
   part of the port. (b) only if a target has no Skia backend (a console API).
3. Upstream Ladybird grows a non-Skia player or a stable command-list export. Then reuse it.

The census (`KR_DEBUG_CENSUS`) stays as the coverage probe for any of these.
