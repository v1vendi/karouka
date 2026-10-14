# Pages

Test and demo pages: what `karouka_viewer` opens, `tools/dev.sh check` renders, and `bench/compare.py`,
`tools/dev.sh mem` and `orderfile` measure.

| Path | What |
| --- | --- |
| `index.html` | karouka_viewer's start page (opened when no page is given); its entries are real links |
| `demo/*.html`, `demo/*/index.html` | Demo pages (a page in its own directory, `demo/NAME/index.html`, is named for the directory) |
| `demo/demo_index.html` | A fixed-geometry start page whose rows are not links |
| `demo/frameworks/*.js` | Unmodified React and Svelte bundles for `demo/showcase_page.html` (licenses in `demo/frameworks/licenses/`) |
| `tests/*.html`, `tests/swatch.png` | The pages check smoke-renders |
| `fonts/NotoSans*.ttf` | The Noto faces the pages load through `@font-face` |

`demo/trellis_page.html` talks to its host through the page's `engine` channel (`kr_view_engine_*`);
karouka_viewer's stand-in host answers it.

`tests/busy_wait.html` is karouka's own: scripts that busy-wait on `performance.now()` and
`Date.now()`. On the default host clock each script read takes a fixed 1 us step, so
the waits end after the same number of reads on every run, which its title check pins.

`gates/` holds karouka's own pages for single `dev.sh check` gates, outside `tests/` so check's
page jobs don't render them: `gates/malloc_growth.html` is the system malloc growth gate's page
(`malloc_growth_check` in `tools/dev.sh`).

`mem/` holds karouka's own measurement pages, also outside `tests/`: `mem/huge_image_churn.html`
decodes a 2400x2400 image (one 22 MiB kmalloc, a mimalloc huge segment) on every load and
`mem/large_image_churn.html`, its control, a 2000x2000 one (15.3 MiB, an ordinary segment)
(`docs/MEMORY.md` § The allocator).

`perf/` holds karouka's own per-frame cost pages, outside `tests/` too: full-viewport shader()
backgrounds with text over them (`perf/shader_*.html`: none, a constant live shader, plasma, and
css-shader-image's 512-iteration case 8 once and live), the figures in `docs/ENGINE.md` § Partial
raster. Run one with `tools/dev.sh run pages/perf/NAME.html --headless --frames N --size 1280x720
--scale 1 --stats [--backend software]`.
