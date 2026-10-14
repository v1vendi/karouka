# bench/engines

The same local page in karouka (headless and windowed), Ladybird, Electron, Tauri and TinyJS,
measured the same way from outside every process: startup, CPU, memory, and the page's own JS
and DOM timings. karouka's day-to-day numbers come from `tools/dev.sh bench`, `mem` and `startup`
against its own baselines; this is the occasional look at where it stands among other ways to
put HTML on screen.

```bash
bench/engines/setup.sh                                   # build every engine into bench/engines/.work
python3 -I bench/engines/perfcmp.py --runs 7 --max-load 5
```

Results land in `.work/results/` (`summary.md`, `results.json`). `--only ENGINE` (repeatable)
narrows the run, `--ladybird PATH` points at another Ladybird build, `KR_ENGINES_WORK` moves the
work dir. The windowed engines open a 1280x720 window for each run, about 20 s each.

A window that opens behind the app in use gets no frames: WebKit starves a covered window's
animation frames and timers, and the karouka viewer's display link stops with it. So Electron,
Tauri and TinyJS open their windows always on top (Electron and Tauri with background throttling
off too), and each windowed run waits for `--min-idle` seconds (default 30) without keyboard or
mouse input, since the karouka viewer has no always-on-top switch. Run it while you're away.

## The engines

| engine | how it runs | built by setup.sh as |
|---|---|---|
| karouka | `karouka_viewer --headless --fps 60 --real-time`, offscreen Metal | a snapshot of `tools/dev.sh build` |
| karouka-window | the same viewer in its window (CAMetalLayer, frames on its display link) | the same snapshot |
| ladybird | `Ladybird --headless=manual`, its own profile | not built: a release build at `~/ladybird` |
| electron | a BrowserWindow, on top, `backgroundThrottling: false` | `npm install electron@41.10.7` |
| tauri | a Tauri 2 window (WKWebView), on top, background throttling off; the page is served over a `bench://` scheme | `cargo build --release` of `apps/tauri` |
| tinyjs | a TinyJS window (WKWebView, txiki.js backend), on top; the bare binary from `tinyjs build` | the v0.50.1 release, checksum-verified |

## The page and what is measured

`page/bench.html` is a dashboard: 48 cards, a 24-row table, text, three CSS spinners. It prints
`BENCH ...` lines through whatever each host forwards: console.log (karouka with `--host-log
info`, Ladybird, Electron's `console-message`), a fetch to Tauri's scheme handler, or a TinyJS
backend call that appends to a file.

- **startup (ms):** from spawn to the page's `first_frame` line: load, then two animation frames.
  **startup CPU** is the process tree's CPU up to then, **memory at first frame** its summed
  footprint.
- **JS work / DOM work (ms):** a fixed synchronous workload timed by `performance.now()` in the
  page: object churn, sort and JSON; then 40 table rebuilds, each forcing style and layout.
- **steady:** 10 s of animation-frame callbacks that update the cards and a table cell, at most
  60 updates a second, so a 120 Hz display (Electron's rAF on a ProMotion screen) doesn't do twice
  the work. CPU % of one core and **CPU ms per update** over that window, the peak summed
  footprint and RSS, fps and the frame-interval p95 as the page saw them.

CPU and memory are summed over the launched process and all its descendants, plus, for the
WKWebView hosts, the `com.apple.WebKit.*` XPC processes that appear after launch (launchd starts
those, so they aren't descendants). Memory is `phys_footprint` per process (what Activity Monitor
shows); the RSS row double-counts pages processes share.

Not counted: WindowServer's compositing of the windowed engines' frames. karouka headless and
Ladybird headless don't present to a screen at all, so compare them with each other and the
windowed engines with each other.

Every run starts once the 1-minute load is at or below `--max-load` (default 5, waiting up to
`--load-wait` seconds in all), with one untimed warm-up per engine, the engines interleaved run by
run. Each figure is the median, with the per-run CV; check the CV, and rerun on a quiet machine,
before reading a difference.
