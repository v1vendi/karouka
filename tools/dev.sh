#!/usr/bin/env bash
# karouka developer entry point.
#   tools/dev.sh bootstrap   install pinned cmake, rust and sccache into .toolchain/
#   tools/dev.sh ladybird    patch + configure + compile the Ladybird libraries karouka links
#                            (their objects; libkarouka links those, not the Lagom dylibs)
#   tools/dev.sh build       configure + build karouka (engine + viewer)
#   tools/dev.sh check       build (a failed build fails check), snapshot the build into
#                            its check dir and give back the build lock (everything below
#                            runs from the snapshot), check that
#                            README.md lists every patch, command and viewer flag and nothing else
#                            (tools/readme_sync.py), verify the vendored WPT corpus
#                            against its pin
#                            (tools/wpt_vendor.sh --check: committed third_party/wpt is the pinned
#                            tree and the working tree matches it), render the WPT reftests
#                            tests/wpt/check_filters.txt names (tools/wpt.py --filter, same ratchet as
#                            dev.sh wpt), run the tests/
#                            executables, then headless smoke-render every
#                            page in pages/tests at 30 frames and, in the same run, at 60
#                            (--capture-again: the same pixels, or different ones
#                            for a page marked karouka-check-animated),
#                            then again four views to a system (--second) and
#                            with the second view closed halfway (--close-second); each surviving
#                            view must capture the same pixels as its page alone (tools/pngdiff.py)
#                            and report the same nonzero rendering update count (updates_run).
#                            Every render runs with --check-title: a page that declares
#                            <meta name="karouka-check-title" content="REGEX"> fails unless its
#                            final document.title matches; attributes in any order and
#                            quoting, and a page that declares one must have been checked.
#                            A page's <meta name="karouka-check-input" content="FLAGS"> (same
#                            attribute rules) gives its render scripted input.
#                            A page's <meta name="karouka-check-pixels" content="X,Y=#RRGGBB[~D] ...">
#                            holds its captures' pixels to those colours (tools/pngdiff.py
#                            --pixels): what only paint shows, such as a selection. Alone,
#                            on the software backend, with host io and in every multi-view run
#                            that renders the page with its own input.
#                            Every pages/demo/*.html and pages/demo/*/index.html (named for its
#                            directory) renders the same way, alone, so a demo page's
#                            title meta is enforced too (trellis_page.html).
#                            pages/demo/animations_page.html and the static demo pages (restyle,
#                            sashimi, showcase, demo_index, trellis) must run no layout update
#                            from frame 10 on (--max-layouts-per-frame), nor
#                            trellis scrolled a wheel step a frame from frame 10 on, nor
#                            trellis, showcase and sashimi under a mouse move a frame or
#                            trellis under a down-arrow press a frame, nor
#                            trellis and sashimi clicked (--poke), animations_page under a
#                            mouse move a frame at most 1 in all, and
#                            hud_page.html at most 1 a frame. animations_page.html and scroll_input.html
#                            drawn straight into a viewer texture (--output-texture) must match a
#                            reference view's IOSurface pixel for pixel
#                            sashimi_page.html at 1280x1200 renders at least 590 of 600 frames,
#                            at 1280x720 at most 3: the off-screen animation cull
#                            Every page that passed alone renders again on the software backend
#                            (--backend software, no GPU) and must match its Metal capture within
#                            CHECK_SOFTWARE_TOLERANCE (tools/pngdiff.py --tolerance)
#                            and again with its loads routed through the host (--host-io async:
#                            kr_host_io, each read completed a frame later through kr_io_complete),
#                            which must capture its Metal pixels exactly and serve at least the page
#                            itself, with every borrowed buffer released; the same run
#                            rasterizes its last frame whole (--check-full-raster), which must match
#                            its partially rasterized pixels exactly (on a host io
#                            difference a KR_FULL_RASTER=1 run decides the full raster line)
#                            Then it measures kr_system_create2 over $KR_STARTUP_RUNS (default 11)
#                            one-frame runs of the empty page with KR_DEBUG=1 and fails when the
#                            median instructions retired are over
#                            $KR_SYSTEM_CREATE_INSTRUCTIONS_BUDGET_M (default 160 M), when no run,
#                            $KR_STARTUP_EXTRA_RUNS (default 30) more included, has main-thread
#                            off-CPU time at $KR_SYSTEM_CREATE_OFF_CPU_BUDGET_MS (default 6; over load
#                            $KR_STARTUP_OFF_CPU_LOAD, default 60, 1 ms per 4 of load) or under,
#                            or when no run's wall time is at $KR_SYSTEM_CREATE_BUDGET_MS (default
#                            40, more over load 40) or under. Mins and a count, not medians of
#                            time: machine load only raises them
#                            (docs/STARTUP.md)
#                            It also renders pages/gates/malloc_growth.html 900 frames (a job
#                            beside all the others, its line printed last) and fails when the
#                            system malloc zone grew more than $KR_CHECK_MALLOC_GROWTH_KB (default
#                            0.75) KB a frame from frame 300 to 900: kr_view_render's autorelease
#                            pool
#                            And pages/gates/font_size_growth.html 9600 frames (a label 0.1 px
#                            larger every frame, two laps of 4800 sizes; another such job) and
#                            fails when the system malloc zone's highest reading from frame 2400
#                            to 9600 is more than $KR_CHECK_FONT_SIZE_GROWTH_MB (default 8) MB
#                            over frame 2400's, or Skia's glyph cache holds more than
#                            $KR_CHECK_FONT_SIZE_STRIKES (default 256, kr_system_create2's cap)
#                            strikes at any of those frames: the font cascade memo's limit and the
#                            strike cap
#                            Last, it warns (without failing) when the empty page's code spans more
#                            than $KR_ORDERFILE_WARN_PAGES (default 400) __text pages: the order
#                            file is stale, regenerate it with orderfile
#                            Logs and captures go to this checkout's own directory under
#                            Build/release/karouka/check/ (printed at the end), and
#                            each page's shader cache to its shader-cache/
#                            The WPT filters, test executables and renders run $KR_CHECK_JOBS at a
#                            time (default 3, at most $KR_JOBS; 1 runs them one by one), their lines
#                            printed in the same order at any count; the startup gate runs alone.
#                            The end prints check's wall time after the build, by phase,
#                            and its slowest jobs ("time" lines)
#   tools/dev.sh run [page]  build, then launch the viewer from a snapshot of the build, without the
#                            build lock
#   tools/dev.sh python [TEST.py...]
#                            build, then (from a snapshot of the build, without the build lock) run
#                            tests/python/*.py, or the given ones, against the built _karouka module
#                            (src/python/module.cpp): the interpreter the module was built for
#                            (lib/_karouka.python), the snapshot's lib on PYTHONPATH and KR_SOURCE_DIR
#                            set to this checkout. Logs: $KR_BUILD/python/<checkout>/. check runs
#                            every tests/python/*.py the same way, as jobs beside the test executables.
#                            The module is built for $KR_PYTHON (default /opt/homebrew/bin/python3,
#                            any CPython 3.14 with the GIL; set on every configure)
#   tools/dev.sh startup     build, then only check's kr_system_create2 budget, logged to
#                            Build/release/karouka/startup/<checkout>/startup.log, from a snapshot of
#                            the build, holding the measure lock, not the build lock
#   tools/dev.sh bench ...   build, then run bench/compare.py (karouka alone on its bench pages), from
#                            a snapshot of the build, holding the measure lock instead of the build
#                            lock
#   tools/dev.sh bench --save NAME
#                            build, then keep this build's karouka_viewer, libkarouka.dylib and the
#                            vcpkg and Skia dylibs it loads (libmimalloc...) as NAME (in
#                            $KR_BENCH_BUILDS) for an A/B run, each side loading its own
#   tools/dev.sh bench --ab A B [...]
#                            build, then time two karouka builds against each other: saved NAMEs,
#                            directories, or `current` (this build), e.g. --ab before current.
#                            Warns when A and B were built from different Ladybird trees;
#                            --same-ladybird refuses to run instead (exit 1)
#   tools/dev.sh wpt [--suite all|reftest|dom] [--filter SUBSTRING]... [--write-known] [--verbose]
#                            build, then (from a snapshot of the build, without the build lock)
#                            render the vendored WPT reftest subset (third_party/wpt,
#                            pinned by tests/wpt/corpus.pin; or $KR_WPT_ROOT) on
#                            the software backend at 800x600, one viewer per document, and print the
#                            pass rate (tools/wpt.py). Fails on a test outside
#                            tests/wpt/known_failures.txt that fails, or one in it that passes.
#                            Then (--suite all, the default; reftest|dom for one) runs the vendored
#                            testharness.js subset (dom/nodes/, css-scroll-snap, cssom-view, innerText,
#                            html/semantics/scripting-1, transform-hit-testing) through karouka_viewer --testharness and
#                            prints karouka's subtest count (tools/wpt_dom.py); its ratchet is
#                            tests/wpt/known_failures_dom.txt, per subtest. Output:
#                            $KR_BUILD/wpt/<checkout>; a run first deletes those of checkouts that are gone.
#                            Not part of check (minutes; check runs wpt_vendor.sh --check and only the
#                            tests/wpt/check_filters.txt subset).
#                            Re-vendor: tools/wpt_vendor.sh --from DIR
#   tools/dev.sh libweb [--kind text|ref|both] [--gc-stress] [--only REL]... [--save NAME] [--write-known]
#                       [--list] [--compare A B]
#                            build, then (from a snapshot, without the build lock, as wpt) run
#                            Ladybird's own Tests/LibWeb Text and Ref tests that touch images in
#                            karouka_viewer (tools/libweb_tests.py; its other flags pass through).
#                            Results: $KR_BUILD/libweb/<checkout>/results-<kind>[-gc].json, replaced
#                            each run; --save NAME also keeps them as $KR_BUILD/libweb/saved/NAME.json
#                            (shared by every checkout; an existing NAME, or a bad flag, is refused
#                            before the build). A run deletes saved runs older than 14 days
#                            (--keep-saved-days N) and the output directories of checkouts that are
#                            gone. --compare diffs two results files or saved NAMEs and --list
#                            prints the picked tests, neither building. Exits 1 when a run differs
#                            from its ratchet, tests/libweb/known_failures.txt (--gc-stress too): an
#                            unlisted test that doesn't pass, a listed one that passes or ends with
#                            another status (--write-known rewrites it from the run). Not part of check.
#   tools/dev.sh census [--input] [--frames N] [--jobs N] [--json FILE] [page...]
#                            build, then (from a snapshot of the build, without the build lock) run
#                            every page check renders (or the given ones: a path or NAME under pages/,
#                            tests/canvas_2d) headless 60 frames with KR_DEBUG_CENSUS and print
#                            docs/COMMAND-LIST.md's karouka column: per display-list command and
#                            feature, the pages using it and the most in one frame, the drawing
#                            commands never seen, the busiest frames and the pages stages S3+S4
#                            cover (tools/census.py). --input gives each page its
#                            karouka-check-input. Logs: $KR_BUILD/census/<checkout>/logs; jobs
#                            $KR_CHECK_JOBS (default 3). Exits 1 when a page fails or logs no census
#   tools/dev.sh mem [page] [--frames N] [--runs N] [--views N] [--attribute] [--no-render]
#                    [--hold] [--malloc-history]
#                            build, then print peak RSS + footprint of 5 headless 600-frame runs
#                            (from a snapshot of the build, holding the measure lock, not the build
#                            lock)
#                            and their median, plus vmmap's IOSurface region count (default page:
#                            empty; or a demo page by name, demo/trellis_page).
#                            --frames 0 loads without rendering; --no-render advances frames without
#                            rendering. Same numbers docs/MEMORY.md uses. A --frames below
#                            0 or --runs/--views below 1 exits 2 before the build lock.
#                            --views N renders N views of the page in one system (--second);
#                            the difference from --views 1 is the cost of the extra views
#                            --attribute instead runs once with karouka_miprof inserted and prints
#                            the kmalloc (mimalloc) bytes per call site each phase adds (tools/miprof.py),
#                            plus canvas 2D surface bytes (canvas_mb, KR_MEM_TAG_CANVAS)
#                            Its build line and karouka-mem line name the Ladybird tree it measured
#                            (ladybird_tree=, series=match|differs, owner=; build_info)
#                            --hold also keeps vmmap -v -wide and footprint of the held run in
#                            $KR_BUILD/mem/hold/<page>.*.txt and prints its malloc_zone_mb and
#                            font_cache_strikes (--memory-stats). --malloc-history (implies --hold)
#                            holds that run under
#                            MallocStackLogging=lite and adds heap -s and malloc_history -allBySize
#   tools/dev.sh mem --all-demo [--frames N] [--runs N] [--views N] [--no-render]
#                            build once, then mem of every demo page (mem --list) with those flags,
#                            and a table of each page's median RSS, footprint, IOSurface regions and
#                            IOAccelerator MB. A failing page is a FAILED row; exit 1
#   tools/dev.sh orderfile [--stats [--data [--unplaced]]] [--input FLAGS] [--fresh] [--tests]
#                          [page...]
#                            build, then (from a snapshot of the build, without the build lock)
#                            record which of libkarouka's functions the empty page (600
#                            frames) and then the given pages, by default pages/demo/*.html and
#                            pages/demo/*/index.html (60 frames, each with its
#                            karouka-check-input or else orderfile.py's DEMO_INPUT and a focus
#                            toggle) run, in first-run order, into src/libkarouka.order,
#                            the link's -order_file (tools/orderfile.py),
#                            headed by the build_info of the tree it ran.
#                            --input FLAGS replaces DEMO_INPUT for pages without a meta ('' for
#                            none); --fresh drops the data and literals the previous files listed;
#                            --tests also traces, after those pages, every pages/tests page that
#                            declares a karouka-check-input (not in the committed file)
#                            --stats only prints how many __text pages each page's code spans;
#                            --unplaced lists the data ld can't place and each touched data page's
#                            atoms (o listed, n named unlisted, l literal, u unplaced)
#   tools/dev.sh package [DIR]
#                            build, then write what a host ships into DIR (default: this checkout's
#                            Build/release/karouka/package/<checkout>/, replaced): lib/libkarouka.dylib
#                            without its local symbols and debug map (strip -x, ~18 MB less __LINKEDIT),
#                            lib/libkarouka.dylib.dSYM made from the build's unstripped dylib
#                            (dsymutil; same UUID, so atos, lldb and crash reports symbolize through it),
#                            include/karouka/ and build.txt. Fails unless the dSYM read every object,
#                            the exports are unchanged and the viewer renders the empty page with the
#                            packaged dylib. The build's own dylib keeps its symbols: miprof's atos,
#                            ordertrace's dladdr and assertion backtraces read them. The vcpkg dylibs
#                            it loads are not packaged
#   tools/dev.sh wheel [DIR]
#                            build, then the karouka wheel into DIR (default: this checkout's
#                            Build/release/karouka/wheel/<checkout>/, replaced; tools/wheel.py):
#                            _karouka*.so stripped (strip -x), the karouka package, Ladybird's
#                            Base/res as karouka/res and the dylibs the module loads in
#                            karouka/.dylibs, all on @loader_path rpaths, tagged
#                            cp3XX-macosx_*_arm64 for the interpreter the module was built for
#                            (KR_PYTHON). Fails unless that interpreter's fresh venv, with the wheel
#                            pip-installed and the checkout and Ladybird tree unreadable
#                            (sandbox-exec), runs python -m karouka on demo_page.html with the same
#                            pixels as the build's module, and on a page whose text/python runs
#   tools/dev.sh mem --list | orderfile --list
#                            print the demo pages (demo/NAME and path) without building: orderfile's
#                            default pages, and the names mem and orderfile take in place of a path
#   tools/dev.sh patches [--reset]
#                            apply this checkout's patch series to the shared Ladybird tree. The
#                            owner keeps its hand edits there; --reset discards them too
#   tools/dev.sh own
#                            take ownership of the shared Ladybird tree before editing it (patch
#                            series work), and apply this checkout's series
#   tools/dev.sh release [--force]
#                            give it back once the patches are saved. Refuses while the tree differs
#                            from this checkout's series (unsaved edits), or when another checkout
#                            owns it; --force overrides both.
# check and mem first kill stopped viewers left held by hand (--hold, KR_MEM_HOLD).
# check, run, python, bench, mem, wpt, libweb, orderfile, census and startup hold the build lock only to build and snapshot
# the build (tools/snapshot_build.py), then run from the snapshot without it, so other checkouts
# build meanwhile. check prints "build lock: waited X s, held Y s"; a second check of the
# same checkout waits for the first, and a second wpt the first's renders. bench, mem and startup
# then take the measure lock, which only they take: no two measurements overlap, whichever
# checkouts they come from; check's startup gate takes it too. bench --save, package (dsymutil reads the build's
# object files, which the next build replaces) and every other command but bootstrap hold the build
# lock until they exit. Every lock file names its holder, and a waiting dev.sh leaves a record in
# $KR_WAITS_DIR.
# Once their build is done, the snapshot commands pass INT, TERM and HUP on to the viewer and every
# other process they started, then remove the snapshot; during the build, a signal waits
# for it. check passes them on to everything it started, the renders included; a signal
# during its build waits for the build.
# Everything runs at nice 10 with $KR_JOBS (default 4) parallel jobs; check's tests and renders
# with $KR_CHECK_JOBS (default 3, at most $KR_JOBS).
#
# While another checkout owns the Ladybird tree (own/release, see env.sh), builds here use the tree
# as the owner left it. The owner's builds keep its unsaved edits (see apply_patches.sh). With
# KR_SERIES_STRICT=1 a checkout instead waits for the release, polling every $KR_OWNER_POLL s
# (default 30) for up to $KR_OWNER_WAIT s (default 2400) without holding the build lock, then fails.
set -euo pipefail
source "$(dirname "$0")/env.sh"

# Saved karouka builds for bench --ab: NAME/{karouka_viewer,libkarouka.dylib,build.txt}.
KR_BENCH_BUILDS="${KR_BENCH_BUILDS:-$KR_LADYBIRD_BUILD/karouka-bench-builds}"

# bench and mem measure holding this lock, not the build lock (from_snapshot).
KR_MEASURE_LOCK="$KR_LADYBIRD/Build/karouka-measure.lock"

# The build's dylibs and libkarouka's link map. use_snapshot repoints these, with KR_BIN, at a
# snapshot of the build (check, run, bench, mem).
KR_LIB="$KR_BUILD/lib"
KR_MAP="$KR_BUILD/libkarouka.map"

# Test executables (tests/), built by build and run by check before the page smoke renders.
KAROUKA_TESTS=(karouka_binding_model_test karouka_binding_c_test karouka_binding_expression_test karouka_binding_dom_test karouka_engine_channel_test karouka_font_registration_test karouka_render_skip_test karouka_partial_raster_test karouka_memory_usage_test karouka_title_reset_test karouka_view_focus_test karouka_reload_test karouka_system_lifecycle_test karouka_view_stats_test karouka_host_clock_pumps_test karouka_pool_threads_test karouka_script_frame_test karouka_script_type_test karouka_struct_size_test karouka_software_backend_test karouka_gl_interop_test karouka_output_texture_test karouka_autorelease_test karouka_shader_cache_test karouka_embedder_content_test)

# Runs "$@" holding KR_LOCK. Every checkout (the main one and its git worktrees) builds in the same
# Ladybird build dir, so builds and everything that runs their output (check, run, bench, mem) take
# turns. The lock fd is inherited by "$@" and its children ($^F), so it stays held until they exit.
with_lock() {
    with_lock_at "$KR_LOCK" "the build lock (another checkout is building or running the viewer)" "$@"
}

# Runs "$@" holding an exclusive flock on FILE, saying "waiting for WHAT" while it waits. With
# $KR_LOCK_REPORT set it prints how long it waited and held the lock (check's build phase).
# FILE holds its holder (pid, root, since, what: the command; stale once
# that pid is gone; ended once the command is), and a wait leaves a record in $KR_WAITS_DIR until the
# lock is taken.
#   with_lock_at FILE WHAT COMMAND...
with_lock_at() {
    mkdir -p "$(dirname "$1")" "$KR_WAITS_DIR"
    KR_ROOT="$KR_ROOT" KR_WAITS_DIR="$KR_WAITS_DIR" KR_CHECKOUT_KEY="$(checkout_key)" \
    perl -MFcntl=:flock -MTime::HiRes=time -MPOSIX=strftime -MIO::Handle -e '
        $^F = 255; my $file = shift; my $what = shift; open(my $lock, ">>", $file) or die "lock: $!";
        sub stamp { strftime("%Y-%m-%dT%H:%M:%SZ", gmtime) }
        my $asked = time;
        if (!flock($lock, LOCK_EX | LOCK_NB)) {
            print STDERR "dev.sh: waiting for $what\n";
            my $wait = "$ENV{KR_WAITS_DIR}/$ENV{KR_CHECKOUT_KEY}.$$";
            if (open(my $w, ">", $wait)) { print $w "pid=$$\nroot=$ENV{KR_ROOT}\nsince=" . stamp() . "\nwhat=lock\non=$file\n"; close $w }
            flock($lock, LOCK_EX);
            unlink $wait;
        }
        truncate($lock, 0); print $lock "pid=$$\nroot=$ENV{KR_ROOT}\nsince=" . stamp() . "\nwhat=@ARGV[1..$#ARGV]\n"; $lock->flush;
        my $got = time;
        my $code = system(@ARGV);
        print $lock "ended=" . stamp() . "\n"; $lock->flush;
        printf "%s: waited %.1f s, held %.1f s\n", $ENV{KR_LOCK_REPORT}, $got - $asked, time - $got if $ENV{KR_LOCK_REPORT};
        $code == 0 or exit(($? >> 8) || 1);' "$1" "$2" "${@:3}"
}

# Runs with_lock; in a strict checkout, retries while another checkout owns the Ladybird tree, with
# a wait record in $KR_WAITS_DIR (what=owner) meanwhile.
locked() {
    local waited=0 code poll="${KR_OWNER_POLL:-30}" limit="${KR_OWNER_WAIT:-2400}" owner since=""
    local wait_file
    wait_file="$KR_WAITS_DIR/$(checkout_key).$$"
    while :; do
        code=0
        with_lock "$0" "$@" || code=$?
        owner="$(kr_tree_owner)"
        if ((code != KR_OWNED_EXIT || !KR_SERIES_STRICT)) || [[ -z "$owner" || "$owner" == "$KR_ROOT" ]]; then
            rm -f "$wait_file"
            return "$code"
        fi
        if ((waited >= limit)); then
            rm -f "$wait_file"
            echo "dev.sh: $owner still owns the Ladybird tree after ${waited}s; giving up." \
                "It releases it with tools/dev.sh release (or remove $KR_OWNER_FILE if it is abandoned)." >&2
            return "$code"
        fi
        [[ -n "$since" ]] || since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        mkdir -p "$KR_WAITS_DIR"
        printf 'pid=%s\nroot=%s\nsince=%s\nwhat=owner\non=%s\n' "$$" "$KR_ROOT" "$since" "$owner" >"$wait_file"
        echo "dev.sh: waiting for $owner to release the Ladybird tree (${waited}s of ${limit}s)" >&2
        sleep "$poll"
        waited=$((waited + poll))
    done
}

own() {
    local owner
    owner="$(kr_tree_owner)"
    if [[ -n "$owner" && "$owner" != "$KR_ROOT" ]]; then
        echo "dev.sh own: $owner already owns the Ladybird tree" >&2
        return 1
    fi
    mkdir -p "$(dirname "$KR_OWNER_FILE")"
    printf 'root=%s\nsince=%s\n' "$KR_ROOT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$KR_OWNER_FILE"
    # Taking a tree nobody owned: make it exactly this series (edits made there without owning it
    # are discarded, and listed). Already the owner: keep the hand edits, as a build would.
    if [[ -z "$owner" ]]; then
        "$KR_ROOT/tools/apply_patches.sh" --reset
    else
        "$KR_ROOT/tools/apply_patches.sh"
    fi
    echo "dev.sh own: $KR_ROOT owns the Ladybird tree; other checkouts build against it until tools/dev.sh release"
}

release() {
    local force=0 owner
    [[ "${1:-}" == --force ]] && force=1
    owner="$(kr_tree_owner)"
    if [[ -z "$owner" ]]; then
        echo "dev.sh release: nobody owns the Ladybird tree"
        return 0
    fi
    if [[ "$owner" != "$KR_ROOT" ]] && ((!force)); then
        echo "dev.sh release: $owner owns the Ladybird tree, not this checkout (--force to take it away)" >&2
        return 1
    fi
    if [[ "$owner" == "$KR_ROOT" ]] && ((!force)) && ! "$KR_ROOT/tools/apply_patches.sh" --check; then
        echo "dev.sh release: the tree has changes patches/ladybird/ doesn't (listed above). Regenerate" \
            "the patches, or --force to release and let the next build discard them." >&2
        return 1
    fi
    rm -f "$KR_OWNER_FILE"
    echo "dev.sh release: the Ladybird tree is shared again (was owned by $owner)"
}

# What the vcpkg overlay ports (Ladybird's Meta/CMake/vcpkg/overlay-ports) held at the last configure:
# ICU's karouka-data-keep.txt and portfile, mimalloc's patches, ...
KR_OVERLAY_STAMP="$KR_LADYBIRD/Build/karouka.overlay-ports"
overlay_ports_hash() {
    (cd "$KR_LADYBIRD/Meta/CMake/vcpkg/overlay-ports" && find . -type f | LC_ALL=C sort | xargs shasum | shasum | cut -d' ' -f1)
}

# Runs sccache with none of this process's inherited descriptors, stdin from /dev/null and stderr
# dropped, printing its stdout. The server it may start outlives the build (10 min idle), and the
# build lock is a flock on a descriptor every child inherits: a server that kept it would hold the
# lock after the build. Python closes descriptors above 2. Never fails.
sccache_clean() {
    python3 -c 'import subprocess, sys; subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL)' \
        "$KR_SCCACHE" "$@" 2>/dev/null || true
}

# Starts the sccache server, and sets KR_SCCACHE to the sccache the build uses (empty when bootstrap
# hasn't installed one). A server already running on another SCCACHE_DIR (a stray one, or one from
# a tool run by hand) is replaced: the build's compiles would go to its cache, not ours.
KR_SCCACHE=""
start_sccache() {
    [[ -x "$KR_SCCACHE_BIN/sccache" ]] || return 0
    KR_SCCACHE="$KR_SCCACHE_BIN/sccache"
    mkdir -p "$SCCACHE_DIR"
    sccache_clean --start-server >/dev/null
    if ! sccache_clean --show-stats | grep -qF "\"$SCCACHE_DIR\""; then
        sccache_clean --stop-server >/dev/null
        sccache_clean --start-server >/dev/null
    fi
}

configure() {
    "$KR_ROOT/tools/apply_patches.sh"
    start_sccache
    cd "$KR_LADYBIRD"
    # Bootstraps the vcpkg tool into Build/vcpkg-release; ports restore from the binary cache.
    nice -n 10 python3 Meta/ladybird.py vcpkg -j "$KR_JOBS"
    export VCPKG_ROOT="$KR_LADYBIRD/Build/vcpkg-release"
    export PATH="$VCPKG_ROOT:$PATH"
    link_source
    local overlay_hash had_ninja=0 python
    overlay_hash="$(overlay_ports_hash)"
    python="$(karouka_python)" || return
    [[ -f "$KR_LADYBIRD_BUILD/build.ninja" ]] && had_ninja=1
    if [[ ! -f "$KR_LADYBIRD_BUILD/build.ninja" ]]; then
        nice -n 10 cmake --preset Release -S "$KR_LADYBIRD" -B "$KR_LADYBIRD_BUILD" \
            ${KR_SCCACHE:+-DRUSTC_WRAPPER="$KR_SCCACHE"} \
            -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" \
            -DBUILD_TESTING=OFF -DENABLE_CRANELIFT_JIT=OFF \
            -DRUST_CARGO="$KR_RUST_BIN/cargo" -DRUST_RUSTC="$KR_RUST_BIN/rustc" \
            -DKAROUKA_SOURCE_DIR="$KR_SRC_LINK" -DKAROUKA_PYTHON="$python"
    elif [[ "$(sed -n 's/^KAROUKA_SOURCE_DIR:[A-Z]*=//p' "$KR_LADYBIRD_BUILD/CMakeCache.txt")" != "$KR_SRC_LINK" ]]; then
        # The checkout built last used older tools, which configured its own path, not the link.
        nice -n 10 cmake -S "$KR_LADYBIRD" -B "$KR_LADYBIRD_BUILD" -DKAROUKA_SOURCE_DIR="$KR_SRC_LINK" >/dev/null
    fi
    # sccache caches the Rust crates' compiles: Ladybird's rust_crate.cmake hands
    # RUSTC_WRAPPER to cargo.
    if [[ -n "$KR_SCCACHE" ]] && ((had_ninja)) &&
        [[ "$(sed -n 's/^RUSTC_WRAPPER:[A-Z]*=//p' "$KR_LADYBIRD_BUILD/CMakeCache.txt")" != "$KR_SCCACHE" ]]; then
        echo "dev.sh: building the Rust crates through sccache"
        nice -n 10 cmake -S "$KR_LADYBIRD" -B "$KR_LADYBIRD_BUILD" -DRUSTC_WRAPPER="$KR_SCCACHE" >/dev/null
    fi
    # The build dir is shared, so the interpreter is set on every configure: a build with KR_PYTHON
    # doesn't leave the next checkout's build on it.
    if ((had_ninja)) &&
        [[ "$(sed -n 's/^KAROUKA_PYTHON:[A-Z]*=//p' "$KR_LADYBIRD_BUILD/CMakeCache.txt")" != "$python" ]]; then
        echo "dev.sh: building the _karouka module for $python"
        nice -n 10 cmake -S "$KR_LADYBIRD" -B "$KR_LADYBIRD_BUILD" -DKAROUKA_PYTHON="$python" >/dev/null
    fi
    # vcpkg installs the manifest while CMake configures, and CMake doesn't know the overlay ports'
    # files: rerun it when one changed since the last configure (vcpkg then rebuilds just that port).
    if ((had_ninja)) && [[ "$(cat "$KR_OVERLAY_STAMP" 2>/dev/null)" != "$overlay_hash" ]]; then
        echo "dev.sh: an overlay port changed; reconfiguring so vcpkg rebuilds it"
        nice -n 10 cmake -S "$KR_LADYBIRD" -B "$KR_LADYBIRD_BUILD" >/dev/null
    fi
    echo "$overlay_hash" >"$KR_OVERLAY_STAMP"
    # Regenerates build.ninja now if src/CMakeLists.txt changed, then records what it was made from.
    nice -n 10 ninja -C "$KR_LADYBIRD_BUILD" build.ninja >/dev/null
    cp "$KR_ROOT/src/CMakeLists.txt" "$KR_SRC_LINK.cmakelists"
}

# The CPython 3.14 interpreter the _karouka module is built for: $KR_PYTHON (a path, or a command
# on PATH), default Homebrew's python3, printed as an absolute path for KAROUKA_PYTHON.
karouka_python() {
    local python="${KR_PYTHON:-/opt/homebrew/bin/python3}" path
    if ! path="$(command -v "$python")" || [[ "$path" != /* ]]; then
        echo "dev.sh: KR_PYTHON=$python is not an interpreter" >&2
        return 1
    fi
    echo "$path"
}

# Points KR_SRC_LINK at this checkout. The compile commands don't change with the checkout, so
# ninja can't tell its sources from the last checkout's (and they may be older than the objects):
# karouka's objects are dropped, and ccache brings back the ones whose sources are unchanged.
# Ninja reruns CMake (seconds, over the whole Ladybird tree) when src/CMakeLists.txt is newer than
# build.ninja, so its date is set by content: a fresh checkout's copy of what build.ninja was made
# from is dated back, and a different one (even an old file) forward.
link_source() {
    local lists="$KR_ROOT/src/CMakeLists.txt" ninja_file="$KR_LADYBIRD_BUILD/build.ninja"
    if [[ "$(readlink "$KR_SRC_LINK" 2>/dev/null)" != "$KR_ROOT" ]]; then
        echo "dev.sh: building karouka from $KR_ROOT"
        ln -sfn "$KR_ROOT" "$KR_SRC_LINK"
        [[ -d "$KR_BUILD/CMakeFiles" ]] && find "$KR_BUILD/CMakeFiles" -name '*.o' -delete
    fi
    [[ -f "$ninja_file" ]] || return 0
    if cmp -s "$lists" "$KR_SRC_LINK.cmakelists"; then
        [[ "$lists" -nt "$ninja_file" ]] && touch -r "$ninja_file" "$lists"
    elif [[ ! "$lists" -nt "$ninja_file" ]]; then
        touch "$lists"
    fi
    return 0
}

# Only the libraries karouka links. ENABLE_GUI_TARGETS stays on: it also gates LibWeb itself. The
# browser UI and services are not configured: they can't build against the pruned LibWeb (patch 0018).
# libkarouka links their object files (src/CMakeLists.txt writes the list), so build those and leave
# the Lagom dylibs unlinked. Regenerate first: the list is written at generate time.
ladybird() {
    configure
    nice -n 10 ninja -C "$KR_LADYBIRD_BUILD" build.ninja
    sed "s|^$KR_LADYBIRD_BUILD/||" "$KR_BUILD/lagom-objects.txt" |
        xargs nice -n 10 ninja -C "$KR_LADYBIRD_BUILD" -j "$KR_JOBS" ${KR_NINJA_ARGS:-}
}

# karouka's targets live inside the Ladybird build tree (patch 0003), under karouka/. Its compiles
# return their failure; configure's steps stop it only through set -e, which is off inside a function
# called left of || or &&, where a failed step would go on and leave the last good binaries for
# check or run. So every caller runs it as its own process, "$0" _build, and tests its status.
build() {
    configure
    # LibCompositing's and LibWeb's WebGL sources include this generated header without an ordering
    # dependency on its generator, so a clean build can compile them before it exists. Make it first.
    nice -n 10 ninja -C "$KR_LADYBIRD_BUILD" Libraries/LibCompositing/WebGL/GLFunctions.h || return
    nice -n 10 ninja -C "$KR_LADYBIRD_BUILD" -j "$KR_JOBS" ${KR_NINJA_ARGS:-} karouka _karouka karouka_viewer karouka_miprof karouka_ordertrace "${KAROUKA_TESTS[@]}" || return
}

# Frames per check render; the multi-view runs close the second view halfway through.
CHECK_FRAMES=30
# Each pages/tests page renders alone a second time to this many frames. A page has to be
# done changing by CHECK_FRAMES, so both captures must match. Content that arrives on a wall-clock
# timer (docs/ENGINE.md, Clocks and timers) or late on the host clock lands at a frame that depends on
# machine speed or past the capture, and shows as a difference here. A page built to keep moving
# says so with <meta name="karouka-check-animated" content="why"> and is held to the opposite: its
# two captures must differ, so the mark can't outlive the motion and hide a page that stopped.
CHECK_SETTLE_FRAMES=60
# How far the software backend's captures may stray from the Metal ones (tools/pngdiff.py
# --tolerance DELTA:PERCENT): at most PERCENT of the pixels may have a channel more than DELTA off.
# Skia's CPU rasterizer and its Metal backend anti-alias edges, paths and gradients slightly
# differently: on the 2026-10-08 pages at most 0.098% of the pixels were more than 16 off
# (animations_page, 800x600). A blank page, or a shifted or missing element, is more.
CHECK_SOFTWARE_TOLERANCE=16:0.2

# The empty page mem and orderfile measure, written to DIR/empty.html (default $KR_BUILD/mem); prints
# its path. check's runs pass their own DIR: they run without the build lock, beside another
# checkout's mem rewriting the shared one.
#   empty_page [DIR]
empty_page() {
    local dir="${1:-$KR_BUILD/mem}" html='<!doctype html><html><body></body></html>'
    mkdir -p "$dir"
    # Rewritten only when it differs, and then whole (mv), never truncated under a running viewer:
    # mem, orderfile and package can run at once.
    if [[ "$(cat "$dir/empty.html" 2>/dev/null)" != "$html" ]]; then
        printf '%s\n' "$html" >"$dir/empty.html.$$"
        mv -f "$dir/empty.html.$$" "$dir/empty.html"
    fi
    echo "$dir/empty.html"
}

# The demo pages check, mem and orderfile run: pages/demo/*.html, then each page in its own
# directory, pages/demo/*/index.html. One path a line.
demo_pages() {
    local page
    for page in "$KR_ROOT"/pages/demo/*.html "$KR_ROOT"/pages/demo/*/index.html; do
        [[ -e "$page" ]] && echo "$page" # skips an unmatched glob
    done
    return 0
}

# A page's name: its file name without .html, or for an index.html its directory's
# (pages/demo/NAME/index.html is NAME).
page_name() {
    local name
    name="$(basename "$1" .html)"
    [[ "$name" == index ]] && name="$(basename "$(dirname "$1")")"
    echo "$name"
}

# Prints the demo pages as demo/NAME, the names mem takes in place of a path.
list_demo_pages() {
    local page
    while IFS= read -r page; do
        echo "demo/$(page_name "$page")  ${page#"$KR_ROOT"/}"
    done < <(demo_pages)
}

# A page argument for mem/orderfile: demo/NAME is pages/demo/NAME.html or
# pages/demo/NAME/index.html, a directory is its index.html, anything else is a path as given.
resolve_page() {
    local page="$1"
    if [[ "$page" == demo/* && ! -e "$page" ]]; then
        if [[ -e "$KR_ROOT/pages/$page.html" ]]; then page="$KR_ROOT/pages/$page.html"
        elif [[ -e "$KR_ROOT/pages/$page/index.html" ]]; then page="$KR_ROOT/pages/$page/index.html"
        fi
    fi
    [[ -d "$page" && -e "$page/index.html" ]] && page="${page%/}/index.html"
    echo "$page"
}

# What the measurement ran, as key=value fields for mem, orderfile and bench --save:
#   ladybird_tree=<id> series=match|differs|? owner=none|<checkout> karouka=<commit>[+src]
# ladybird_tree is the shared Ladybird working tree as a git tree id (12 hex), the tree the build that
# just ran under this lock compiled; its objects go into the Ladybird repo, so
# `git -C third_party/ladybird diff <id> <other>` shows what two measurements differ by.
# series=match when that is exactly this checkout's series (pinned commit + patches/ladybird/);
# differs when it isn't: another checkout owns the tree (owner=, its basename) and builds here use
# its tree, or the owner's own unsaved edits. karouka is this checkout's commit, +src with
# uncommitted src/ changes. Never fails: a field it can't compute is ?.
# bench --save's build.txt and bench's current-build file carry it as a `build` line, and compare.py
# --ab warns when A's and B's ladybird_tree differ: libkarouka.dylib links Ladybird in, so
# two builds from different trees differ by those patches too (patch 0032 alone once read as ~3 MB RSS).
# Keep this the only definition: a second one would silently shadow it.
build_info() (
    index="$(mktemp -t kr-build-info)" || { echo "ladybird_tree=? series=? owner=? karouka=?"; exit 0; }
    trap 'rm -f "$index" "$index.lock"' EXIT
    # Only the Ladybird commands use the scratch index; the karouka commit below reads the real one.
    lb=(env GIT_INDEX_FILE="$index" git -C "$KR_LADYBIRD")
    tree="?" series="?"
    # A copy of the real index keeps its stat data, so only files that changed are hashed (~0.2 s).
    if cp "$(git -C "$KR_LADYBIRD" rev-parse --absolute-git-dir 2>/dev/null)/index" "$index" 2>/dev/null &&
        "${lb[@]}" add -A >/dev/null 2>&1; then
        tree="$("${lb[@]}" write-tree 2>/dev/null)" || tree="?"
    fi
    # This checkout's series, as apply_patches.sh builds it.
    if [[ "$tree" != "?" ]] && rm -f "$index" && "${lb[@]}" read-tree HEAD 2>/dev/null; then
        applied=1
        for patch in "$KR_ROOT"/patches/ladybird/*.patch; do
            [[ -f "$patch" ]] || continue
            "${lb[@]}" apply --cached "$patch" 2>/dev/null || { applied=0; break; }
        done
        if ((applied)) && target="$("${lb[@]}" write-tree 2>/dev/null)"; then
            [[ "$target" == "$tree" ]] && series=match || series=differs
        fi
    fi
    [[ "$tree" != "?" ]] && tree="${tree:0:12}"
    owner="$(kr_tree_owner 2>/dev/null)" || owner="?"
    owner="${owner:+$(basename "$owner")}"
    if karouka="$(git -C "$KR_ROOT" rev-parse --short HEAD 2>/dev/null)"; then
        git -C "$KR_ROOT" diff --quiet HEAD -- src 2>/dev/null || karouka+="+src"
    else
        karouka="?"
    fi
    echo "ladybird_tree=$tree series=$series owner=${owner:-none} karouka=$karouka"
)

# src/libkarouka.order goes stale as Rust/C++ functions move (renamed objects, new code), and
# a stale one costs pages, not correctness, so nothing else notices. With a fresh one the empty
# page's code spans ~360 __text pages (docs/MEMORY.md), without one ~1060. The limit, 400, is
# ~10% over a fresh file: one stale file spanned 424. Warns, never fails.
orderfile_check() {
    local log="$1/orderfile.log" limit="${KR_ORDERFILE_WARN_PAGES:-400}" code=0 spans
    python3 "$KR_ROOT/tools/orderfile.py" --viewer "$KR_BIN/karouka_viewer" \
        --tracer "$KR_LIB/libkarouka_ordertrace.dylib" --map "$KR_MAP" \
        --empty "$(empty_page "$1")" --stats --warn-pages "$limit" >"$log" 2>&1 || code=$?
    spans="$(sed -n '/pages of __text/{s/.* on *\([0-9]*\) pages of __text.*/\1/p;q;}' "$log")"
    case "$code" in
        0) echo "ok   order file (empty page on $spans __text pages, limit $limit)" ;;
        3) echo "WARN order file is stale: the empty page's code spans $spans __text pages, over $limit." \
                "Regenerate src/libkarouka.order with tools/dev.sh orderfile and commit it (see $log)" ;;
        *) echo "WARN order file: couldn't measure the empty page's __text pages (see $log)" ;;
    esac
}

# kr_system_create2's cost on the empty page run headless for one frame with KR_DEBUG=1:
# one warm-up run that writes DIR's own shader cache, then $KR_STARTUP_RUNS (default 11) runs that
# read it. Three gates, all must pass, at any load (docs/STARTUP.md § Budget):
# - work: the median of the instructions create2's threads retired, from the viewer's
#   "kr_system_create2 runnable ..." line, is at most $KR_SYSTEM_CREATE_INSTRUCTIONS_BUDGET_M million.
#   A count of work, not time, so load, core type and clock barely move it (~1.5% run to run at load
#   14-62): ~1.5 ms more main-thread CPU work fails it at any load.
# - waits: the fastest run's main-thread off-CPU time (wall less its own CPU:
#   sleeps, waits on other threads, waits for a CPU) is at most $KR_SYSTEM_CREATE_OFF_CPU_BUDGET_MS.
#   When none of the first runs makes it, up to $KR_STARTUP_EXTRA_RUNS (default 30) more run,
#   stopping at the first that does (and makes the wall gate). Load only adds waits for a CPU, so a
#   busy machine can cost extra runs but can't hide a sleep: a 5 ms usleep in create2 fails it at
#   any load. Over load $KR_STARTUP_OFF_CPU_LOAD (default 60) the waits for a CPU alone
#   reach 12-20 ms on healthy branches (12.5 at load 69, 19.6 at 126), and runs quiet
#   enough for 6 ms stop coming, so there the budget widens to 1 ms per 4 of load (17 ms at 69,
#   31.5 at 126; never under 6), and the summary says so with the load. It still fails a sleep or
#   wait of ~10 ms or more there, and still judges 6 ms whenever the load is under the threshold.
# - wall: the fastest run's "kr_system_create2 X ms" line (Engine.cpp), extra
#   runs included, is at most $KR_SYSTEM_CREATE_BUDGET_MS plus 1 ms per 5 of load over 40. Loose: a
#   catch-all for regressions over ~10-15 ms that neither count sees. It judges the fastest
#   run, not the median: load 45-50 pushed the median over 40 ms on branches that hadn't regressed.
# The median wall time is printed too, but not judged.
# A run that fails or logs no such lines fails the check. Logs to DIR/startup.log.
#   startup_check DIR
KR_SYSTEM_CREATE_BUDGET_MS="${KR_SYSTEM_CREATE_BUDGET_MS:-40}"
KR_SYSTEM_CREATE_INSTRUCTIONS_BUDGET_M="${KR_SYSTEM_CREATE_INSTRUCTIONS_BUDGET_M:-160}"
KR_SYSTEM_CREATE_OFF_CPU_BUDGET_MS="${KR_SYSTEM_CREATE_OFF_CPU_BUDGET_MS:-6}"
KR_STARTUP_OFF_CPU_LOAD="${KR_STARTUP_OFF_CPU_LOAD:-60}"
startup_check() {
    local dir="$1" runs="${KR_STARTUP_RUNS:-11}" extra="${KR_STARTUP_EXTRA_RUNS:-30}" page cache log
    local ms off instr times=() instrs=() i p50 min max total load load_after budget ipm offmin failed=0
    local offbudget offnote=""
    page="$(empty_page "$dir")" cache="$1/startup-shaders.bin" log="$1/startup.log"
    [[ "$runs" =~ ^[1-9][0-9]{0,2}$ ]] || { echo "FAIL kr_system_create2 budget: KR_STARTUP_RUNS must be 1-999 (got '$runs')"; return 1; }
    [[ "$extra" =~ ^(0|[1-9][0-9]{0,2})$ ]] || { echo "FAIL kr_system_create2 budget: KR_STARTUP_EXTRA_RUNS must be 0-999 (got '$extra')"; return 1; }
    [[ "$KR_STARTUP_OFF_CPU_LOAD" =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo "FAIL kr_system_create2 budget: KR_STARTUP_OFF_CPU_LOAD must be a load (got '$KR_STARTUP_OFF_CPU_LOAD')"; return 1; }
    mkdir -p "$dir"
    rm -f "$cache"
    : >"$log"
    # Run I (0 is the warm-up); sets ms, off and instr, or prints the FAIL line and returns 1.
    startup_run() {
        echo "-- run $1" >>"$log"
        if ! KR_DEBUG=1 "$KR_BIN/karouka_viewer" --headless --frames 1 --shader-cache "$cache" "$page" >>"$log" 2>&1; then
            echo "FAIL kr_system_create2 budget: run $1 of the empty page failed (see $log)"
            return 1
        fi
        ms="$(sed -n '/^-- run '"$1"'$/,$s/.*kr_system_create2 \([0-9.]*\) ms$/\1/p' "$log" | tail -1)"
        off="$(sed -n '/^-- run '"$1"'$/,$s/.*kr_system_create2 runnable .* off-cpu \(-*[0-9.]*\) ms, instructions \([0-9.]*\) M.*/\1/p' "$log" | tail -1)"
        instr="$(sed -n '/^-- run '"$1"'$/,$s/.*kr_system_create2 runnable .* off-cpu \(-*[0-9.]*\) ms, instructions \([0-9.]*\) M.*/\2/p' "$log" | tail -1)"
        if [[ -z "$ms" || -z "$off" || -z "$instr" ]]; then
            echo "FAIL kr_system_create2 budget: run $1 logged no 'kr_system_create2 X ms' or 'kr_system_create2 runnable' line (see $log)"
            return 1
        fi
    }
    loadavg() { sysctl -n vm.loadavg 2>/dev/null | awk '{ print $2 }'; }
    under() { awk -v t="$1" -v b="$2" 'BEGIN { exit !(t <= b) }'; }
    wall_budget() { awk -v b="$KR_SYSTEM_CREATE_BUDGET_MS" -v l="${1:-0}" 'BEGIN { printf "%.1f", b + (l > 40 ? (l - 40) / 5 : 0) }'; }
    # The off-CPU budget, widened to 1 ms per 4 of load over the threshold.
    off_budget() {
        awk -v b="$KR_SYSTEM_CREATE_OFF_CPU_BUDGET_MS" -v t="$KR_STARTUP_OFF_CPU_LOAD" -v l="${1:-0}" \
            'BEGIN { w = l / 4; if (l > t && w > b) printf "%.1f", w; else print b }'
    }
    load="$(loadavg)"
    budget="$(wall_budget "$load")"
    offbudget="$(off_budget "$load")"
    for ((i = 0; i <= runs; i++)); do
        startup_run "$i" || return 1
        if ((i > 0)); then
            times+=("$ms") instrs+=("$instr")
            if ((i == 1)) || ! under "$offmin" "$off"; then offmin="$off"; fi
            if ((i == 1)) || ! under "$min" "$ms"; then min="$ms"; fi
        fi
    done
    # Extra runs until both minimums are in budget: on a busy machine a quiet enough run is rarer.
    total=$runs
    for ((i = runs + 1; i <= runs + extra; i++)); do
        under "$offmin" "$offbudget" && under "$min" "$budget" && break
        startup_run "$i" || return 1
        total=$i
        under "$offmin" "$off" || offmin="$off"
        under "$min" "$ms" || min="$ms"
    done
    load_after="$(loadavg)"
    load="$(awk -v a="${load:-0}" -v b="${load_after:-0}" 'BEGIN { print (a > b ? a : b) }')"
    budget="$(wall_budget "$load")"
    offbudget="$(off_budget "$load")"
    if [[ "$offbudget" != "$KR_SYSTEM_CREATE_OFF_CPU_BUDGET_MS" ]]; then
        offnote=" (widened from $KR_SYSTEM_CREATE_OFF_CPU_BUDGET_MS ms: load $load is over $KR_STARTUP_OFF_CPU_LOAD)"
    fi
    p50="$(median "${times[@]}")"
    ipm="$(median "${instrs[@]}")"
    max="$(printf '%s\n' "${times[@]}" | sort -n | tail -1)"
    local summary="wall min $min ms over $total runs, budget $budget ms (p50 $p50, max $max over $runs); instructions p50 $ipm M, budget $KR_SYSTEM_CREATE_INSTRUCTIONS_BUDGET_M M; main-thread off-CPU min $offmin ms, budget $offbudget ms$offnote; load $load"
    echo "kr_system_create2 $summary" >>"$log"
    under "$min" "$budget" || failed=1
    under "$ipm" "$KR_SYSTEM_CREATE_INSTRUCTIONS_BUDGET_M" || failed=1
    under "$offmin" "$offbudget" || failed=1
    if ((failed)); then
        echo "FAIL kr_system_create2 $summary: over budget (see $log, docs/STARTUP.md)"
        return 1
    fi
    echo "ok   kr_system_create2 $summary"
}

# The system malloc zone (mstats().bytes_used, --mem-phases' malloc_mb) may grow at most
# $KR_CHECK_MALLOC_GROWTH_KB KB a frame from frame 300 to frame 900 of pages/gates/malloc_growth.html
# (a box repainted every frame beside a small looping GIF). Skia autoreleases the Metal command
# buffer each frame's render draws through; without kr_view_render's own autorelease pool a host
# that drains none in its frame loop (the headless viewer) keeps every one, ~1.8 KB a frame.
# The page changes no text and loads no images, so with the pool the zone stays flat from frame 100
# on: 0.00 KB a frame from 300 to 900, 1.71 without the pool (load ~50). malloc_mb has
# 0.1 MB steps, ~0.17 KB a frame over 600 frames, so the budget sits ~2x above the worst healthy
# reading and ~2x below the broken one. The run takes a few seconds; check queues it first beside
# the other jobs: it counts bytes on host-clock frames and times nothing, so their load doesn't
# change what it measures. Logs to DIR/malloc_growth.log.
#   malloc_growth_check DIR
KR_CHECK_MALLOC_GROWTH_KB="${KR_CHECK_MALLOC_GROWTH_KB:-0.75}"
malloc_growth_check() {
    local log="$1/malloc_growth.log" code=0 from to kb
    KR_MEM_PHASE_EVERY=300 "$KR_BIN/karouka_viewer" --headless --size 800x600 --frames 900 --mem-phases \
        "$KR_ROOT/pages/gates/malloc_growth.html" >"$log" 2>&1 || code=$?
    from="$(sed -n 's/^karouka-mem-phase frame-300 .* malloc_mb=\([0-9.]*\) .*/\1/p' "$log")"
    to="$(sed -n 's/^karouka-mem-phase frame-900 .* malloc_mb=\([0-9.]*\) .*/\1/p' "$log")"
    if ((code)) || [[ -z "$from" || -z "$to" ]]; then
        echo "FAIL gates/malloc_growth system malloc growth: the run failed or logged no frame-300/frame-900 malloc_mb (see $log)"
        return 1
    fi
    kb="$(awk -v a="$from" -v b="$to" 'BEGIN { printf "%.2f", (b - a) * 1024 / 600 }')"
    local summary="gates/malloc_growth system malloc growth $kb KB a frame from frame 300 to 900 ($from -> $to MB), budget $KR_CHECK_MALLOC_GROWTH_KB KB"
    if awk -v k="$kb" -v b="$KR_CHECK_MALLOC_GROWTH_KB" 'BEGIN { exit !(k <= b) }'; then
        echo "ok   $summary"
    else
        echo "FAIL $summary (see $log; an autorelease pool missing?)"
        return 1
    fi
}

# A label whose font size changes by 0.1 px every frame (pages/gates/font_size_growth.html,
# a font-size transition) resolves a new size each frame. Two limits keep that bounded: the
# document's font cascade memo forgets the cascades no computed style holds (patches 0091, 0095) and
# kr_system_create2 caps Skia's glyph cache at 256 strikes. A 9600-frame run, two laps of the
# page's 4800 sizes, with a phase every 1200 frames (--mem-phases-heap prints the strike count; its
# walk adds ~45 ms a phase). Healthy (load 4.5-5): malloc_mb 52.2, 54.2, 55.9, 56.9 at frames 2400,
# 4800, 7200 and 9600, 4.7 MB over frame 2400, and 252, 209, 233, 253 strikes. The malloc gate takes
# the highest reading from 2400 on, not the last: before patch 0095 the zone peaked at the end of
# the first lap (55.0 at 2400, 69.2 at 4800) and fell back in the second (59.9 at 9600), and without
# patch 0091 it rose 23.5 MB from 2400 to 4800. So the 8 MB budget sits ~1.7x above the healthy
# reading and below both regressions. The strike count is judged as a count, not a growth: without
# the cap Skia's own budget fills by frame 2400 (1804 strikes there, 1869 at 9600, and the zone grows
# only 5.1 MB from 2400 to 9600). Counts bytes on host-clock frames, timing nothing, so check runs
# it beside the other jobs; ~20 s at load 5. Logs to DIR/font_size_growth.log.
#   font_size_growth_check DIR
KR_CHECK_FONT_SIZE_GROWTH_MB="${KR_CHECK_FONT_SIZE_GROWTH_MB:-8}"
KR_CHECK_FONT_SIZE_STRIKES="${KR_CHECK_FONT_SIZE_STRIKES:-256}"
font_size_growth_check() {
    local log="$1/font_size_growth.log" code=0 frame from="" peak="" peak_frame="" strikes=0 strikes_frame="" mb count
    KR_MEM_PHASE_EVERY=1200 "$KR_BIN/karouka_viewer" --headless --size 800x600 --frames 9600 --mem-phases-heap \
        "$KR_ROOT/pages/gates/font_size_growth.html" >"$log" 2>&1 || code=$?
    for frame in 2400 3600 4800 6000 7200 8400 9600; do
        mb="$(sed -n "s/^karouka-mem-phase frame-$frame .* malloc_mb=\([0-9.]*\) .*/\1/p" "$log")"
        count="$(sed -n "s/^karouka-mem-phase frame-$frame .* font_cache_strikes=\([0-9]*\) .*/\1/p" "$log")"
        if ((code)) || [[ -z "$mb" || -z "$count" ]]; then
            echo "FAIL gates/font_size_growth: the run failed or logged no frame-$frame malloc_mb or font_cache_strikes (see $log)"
            return 1
        fi
        [[ -z "$from" ]] && from="$mb"
        if [[ -z "$peak" ]] || awk -v a="$mb" -v b="$peak" 'BEGIN { exit !(a > b) }'; then
            peak="$mb" peak_frame="$frame"
        fi
        ((count > strikes)) && strikes="$count" strikes_frame="$frame"
    done
    local growth
    growth="$(awk -v a="$from" -v b="$peak" 'BEGIN { printf "%.1f", b - a }')"
    local summary="gates/font_size_growth system malloc +$growth MB from frame 2400 to its high at $peak_frame ($from -> $peak MB), budget $KR_CHECK_FONT_SIZE_GROWTH_MB MB; glyph cache at most $strikes strikes (frame $strikes_frame), budget $KR_CHECK_FONT_SIZE_STRIKES"
    if awk -v g="$growth" -v b="$KR_CHECK_FONT_SIZE_GROWTH_MB" 'BEGIN { exit !(g <= b) }' && ((strikes <= KR_CHECK_FONT_SIZE_STRIKES)); then
        echo "ok   $summary"
    else
        echo "FAIL $summary (see $log; the font cascade memo's limit or the strike cap? docs/MEMORY.md)"
        return 1
    fi
}

# The viewer's scripted input flags a test page asks for, from
#   <meta name="karouka-check-input" content="--scroll 0,100@4..6 --poke 40,40@10">
# read by the viewer's own meta scan, the one --check-title uses (karouka_viewer --print-meta:
# attributes in any order and quoting). Empty for most pages. Word-split by the
# callers: plain flags, no quoting.
check_input() {
    check_meta "$1" input
}

# The content of a check page's <meta name="karouka-check-NAME" content="..."> ($2 is NAME), or
# nothing; the same viewer meta scan as check_input.
check_meta() {
    "$KR_BIN/karouka_viewer" --print-meta "karouka-check-$2" "$1" || true
}

# CAPTURE has the pixels PIXELS (a karouka-check-pixels meta's samples, as
# check_meta reads them) pins; nothing to check when PIXELS is empty. tools/pngdiff.py's sample
# lines go to LOG, then a line naming LABEL when one differs.
#   check_pixels PIXELS CAPTURE LOG LABEL
check_pixels() {
    [[ -z "$1" ]] && return 0
    python3 "$KR_ROOT/tools/pngdiff.py" --pixels "$1" "$2" >>"$3" 2>&1 && return 0
    echo "  $4: $2 doesn't have the pixels its karouka-check-pixels meta pins" >>"$3"
    return 1
}

# This checkout's check output. Every checkout runs check in the one build dir, and the
# build lock only keeps them from running at once: a shared directory let the next checkout's check
# wipe the logs a FAIL line had just pointed at. Named after the checkout's directory and a hash of
# its path; a directory whose checkout no longer exists (a removed worktree) is removed here.
# Files at the top of check/ are left alone.
check_dir() {
    local base="$KR_BUILD/check" dir root
    mkdir -p "$base"
    rm -rf "$base/multi" "$base/demo"
    for dir in "$base"/*/; do
        [[ -f "$dir/checkout" ]] || continue
        root="$(cat "$dir/checkout")"
        [[ -d "$root" ]] || rm -rf "$dir" "${dir%/}.lock"
    done
    check_dir_path
}

# check_dir's path, without the cleanup.
check_dir_path() {
    echo "$KR_BUILD/check/$(checkout_key)"
}

# This checkout's directory name and a hash of its path: names its check and snapshot directories.
checkout_key() {
    echo "$(basename "$KR_ROOT")-$(printf '%s' "$KR_ROOT" | cksum | cut -d ' ' -f 1)"
}

# Renders one page alone for check: CHECK_FRAMES frames with --check-title and the page's scripted
# input (check_input), captured to DIR/NAME.png and logged to DIR/NAME.log, which must have the
# pixels its karouka-check-pixels meta pins; a page with input is
# captured again without it (DIR/NAME.no-input.png) for the multi-view check. Prints its ok/FAIL
# line (NAME after LABEL_PREFIX); fails if the viewer does, or if the page declares a title
# expectation the viewer didn't check. Uses check's $view. With SETTLE (pages/tests), the same run goes
# on to CHECK_SETTLE_FRAMES and captures again (--capture-again, DIR/NAME.settled.png): the same pixels,
# or different ones when the page is marked animated.
#   check_page DIR LABEL_PREFIX PAGE [SETTLE]
check_page() {
    local dir="$1" prefix="$2" page="$3" settle="${4:-}" name input animated="" note="" ok=1
    name="$(page_name "$page")"
    input="$(check_input "$page")"
    [[ -n "$settle" ]] && animated="$(check_meta "$page" animated)"
    # Same for a karouka-check-animated meta with no reason: it would silently be checked as static.
    if [[ -n "$settle" && -z "$animated" ]] && grep -Eiq '<meta[^>]*karouka-check-animated' "$page"; then
        echo "  $name declares karouka-check-animated but no reason was read from it" >"$dir/$name.log"
        echo "FAIL $prefix$name (see $dir/$name.log)"
        return 1
    fi
    # The same for karouka-check-pixels: a meta read as empty would check nothing.
    local pixels
    pixels="$(check_meta "$page" pixels)"
    if [[ -z "$pixels" ]] && grep -Eiq '<meta[^>]*karouka-check-pixels' "$page"; then
        echo "  $name declares karouka-check-pixels but no samples were read from it" >"$dir/$name.log"
        echo "FAIL $prefix$name (see $dir/$name.log)"
        return 1
    fi
    # A page that mentions karouka-check-input but yields no flags would run unscripted and pass:
    # its meta is malformed or empty.
    if [[ -z "$input" ]] && grep -Eiq '<meta[^>]*karouka-check-input' "$page"; then
        echo "  $name declares karouka-check-input but no input flags were read from it" >"$dir/$name.log"
        echo "FAIL $prefix$name (see $dir/$name.log)"
        return 1
    fi
    # With SETTLE the run goes on to CHECK_SETTLE_FRAMES after its capture, title check and
    # the rest at CHECK_FRAMES (title metas pin the value there), and captures again (one run).
    # A static page must capture the same pixels at both frames, an animated one different ones.
    local again=()
    [[ -n "$settle" ]] && again=(--capture-again "$CHECK_SETTLE_FRAMES:$dir/$name.settled.png")
    # shellcheck disable=SC2086 # the page's input flags, word-split on purpose
    "$KR_BIN/karouka_viewer" "${view[@]}" ${again[@]+"${again[@]}"} $input \
        --capture "$dir/$name.png" "$page" >"$dir/$name.log" 2>&1 || ok=0
    # The capture at CHECK_FRAMES (with the page's input, if any) has the pixels the page
    # pins: no title can read a selection highlight or an image's painted colour back.
    if ((ok)) && ! check_pixels "$pixels" "$dir/$name.png" "$dir/$name.log" "$name"; then
        ok=0
        note=", pixels differ"
    fi
    if ((ok)) && [[ -n "$settle" ]]; then
        local same=1
        if [[ ! -f "$dir/$name.settled.png" ]]; then
            echo "  no capture at frame $CHECK_SETTLE_FRAMES ($dir/$name.settled.png)" >>"$dir/$name.log"
            ok=0
        else
            python3 "$KR_ROOT/tools/pngdiff.py" "$dir/$name.png" "$dir/$name.settled.png" \
                >>"$dir/$name.log" 2>&1 || same=0
            if [[ -z "$animated" ]] && ((!same)); then
                echo "  the capture at frame $CHECK_SETTLE_FRAMES differs from the one at frame $CHECK_FRAMES:" \
                    "$name is still changing after frame $CHECK_FRAMES (a page built to keep moving says so" \
                    "with <meta name=\"karouka-check-animated\" content=\"why\">)" >>"$dir/$name.log"
                ok=0
                note=", still changing after frame $CHECK_FRAMES"
            elif [[ -n "$animated" ]] && ((same)); then
                echo "  $name is marked karouka-check-animated ($animated) but captures the same pixels" \
                    "at frames $CHECK_FRAMES and $CHECK_SETTLE_FRAMES: drop the mark" >>"$dir/$name.log"
                ok=0
                note=", marked animated but not moving"
            fi
        fi
    fi
    # A page with scripted input is also captured without it: the multi-view check shows it
    # beside itself, unscripted, to catch input that reaches the wrong view.
    if ((ok)) && [[ -n "$input" ]]; then
        "$KR_BIN/karouka_viewer" "${view[@]}" --capture "$dir/$name.no-input.png" "$page" \
            >>"$dir/$name.log" 2>&1 || ok=0
    fi
    # A page that declares a title expectation must have had it checked: a meta the viewer
    # can't parse would otherwise pass silently.
    if ((ok)) && grep -Eq '<meta[^>]*karouka-check-title' "$page" &&
        ! grep -q "karouka_viewer: title check page=" "$dir/$name.log"; then
        echo "  $name declares karouka-check-title but the viewer checked no title" >>"$dir/$name.log"
        ok=0
    fi
    if ((ok)); then
        echo "ok   $prefix$name${input:+ ($input)}${animated:+ (animated)}"
    else
        echo "FAIL $prefix$name$note (see $dir/$name.log)"
    fi
    ((ok))
}

# check's job pool. check runs its independent renders and test executables
# $KR_CHECK_JOBS at a time (default 3, never more than $KR_JOBS; 1 runs them one after another in
# the parent shell). Each job's output goes to DIR/N.out and its exit status to DIR/N.rc; the
# output is printed in submission order, as soon as every earlier job has finished, so check prints
# the same lines in the same order at any job count. Slots are tokens in a FIFO on fd 8 (bash 3.2:
# no wait -n); a job closes fd 8 for what it runs. A job queued with --late prints after every
# other job instead (pool_wait), so a long one queued first holds back no other job's lines.
# pool_wait_for waits for some jobs only (one round's, which the next round reads) and leaves the
# rest running. Each job's wall time goes to DIR/N.time, and pool_wait appends them to the file
# $pool_times names, for pool_slowest.
#   pool_start DIR; pool_job [--late] CMD ARGS...; ...; [pool_wait_for FIRST END;] ...
#   pool_wait (1 if any job failed); pool_ok N
KR_CHECK_JOBS="${KR_CHECK_JOBS:-$((KR_JOBS < 3 ? KR_JOBS : 3))}"
pool_times=/dev/null
# Seconds since the epoch to a hundredth (bash 3.2: no EPOCHREALTIME), and seconds since such a
# stamp to a tenth.
now_s() { perl -MTime::HiRes=time -e 'printf "%.2f\n", time'; }
since_s() { perl -MTime::HiRes=time -e 'printf "%.1f\n", time - $ARGV[0]' "$1"; }
pool_start() {
    pool_dir="$1" pool_count=0 pool_printed=0 pool_late=" " pool_pids=()
    rm -rf "$pool_dir"
    mkdir -p "$pool_dir"
    if ((KR_CHECK_JOBS > 1)); then
        mkfifo "$pool_dir/slots"
        exec 8<>"$pool_dir/slots"
        rm -f "$pool_dir/slots"
        local i
        for ((i = 0; i < KR_CHECK_JOBS; i++)); do printf . >&8; done
    fi
}
pool_run() {
    local i="$1" rc=0 start
    shift
    start="$(now_s)"
    "$@" >"$pool_dir/$i.out" 2>&1 8>&- || rc=$?
    printf '%s\t%s\n' "$(since_s "$start")" "$(pool_label "$@")" >"$pool_dir/$i.time"
    echo "$rc" >"$pool_dir/$i.rc.tmp"
    mv "$pool_dir/$i.rc.tmp" "$pool_dir/$i.rc"
}
pool_job() {
    local i="$pool_count" slot
    if [[ "$1" == --late ]]; then pool_late+="$i "; shift; fi
    pool_count=$((pool_count + 1))
    if ((KR_CHECK_JOBS > 1)); then
        read -r -n 1 -u 8 slot
        pool_flush
        { pool_run "$i" "$@" || true; printf . >&8; } &
        pool_pids[i]=$!
    else
        pool_run "$i" "$@"
        pool_flush
    fi
}
# Prints the finished jobs' output in order, up to the first job still running; late jobs wait
# for pool_wait.
pool_flush() {
    while ((pool_printed < pool_count)); do
        if [[ "$pool_late" != *" $pool_printed "* ]]; then
            [[ -e "$pool_dir/$pool_printed.rc" ]] || break
            cat "$pool_dir/$pool_printed.out"
        fi
        pool_printed=$((pool_printed + 1))
    done
}
# Waits for jobs FIRST to END-1 and prints what it can; the other jobs keep running.
pool_wait_for() {
    local i
    for ((i = $1; i < $2; i++)); do
        if [[ -n "${pool_pids[i]:-}" ]]; then wait "${pool_pids[i]}" 2>/dev/null || true; fi
    done
    pool_flush
}
pool_ok() {
    [[ "$(cat "$pool_dir/$1.rc" 2>/dev/null)" == 0 ]]
}
# A job's name for the timing list: its function and what it ran on (a test, a page, a group).
pool_label() {
    local f="$1"
    shift 2
    case "$f" in
        check_page) echo "$f $1${2##*/}" ;;
        software_page|host_io_page) local page="${1##*|}" prefix="${1#*|}"; echo "$f ${prefix%%|*}${page##*/}" ;;
        multi_view_run) echo "$f $2-$1" ;;
        wpt_filter_check) echo "$f ($# filters)" ;;
        *) echo "$f${1:+ $1}" ;;
    esac
}
# The N slowest jobs of every round since pool_times was emptied, slowest first, on one line.
pool_slowest() {
    sort -t $'\t' -k1,1 -rn "$pool_times" | head -"$1" |
        awk -F '\t' '{ printf "%s%s %s s", (NR > 1 ? ", " : ""), $2, $1 } END { print "" }'
}
pool_print() {
    if [[ -e "$pool_dir/$1.out" ]]; then cat "$pool_dir/$1.out"; fi
    if [[ ! -e "$pool_dir/$1.rc" ]]; then echo "FAIL check job $1 left no exit status (see $pool_dir)"; fi
}
pool_wait() {
    local i failed=0
    wait
    if ((KR_CHECK_JOBS > 1)); then exec 8>&-; fi
    for ((i = pool_printed; i < pool_count; i++)); do
        [[ "$pool_late" == *" $i "* ]] || pool_print "$i"
    done
    for i in $pool_late; do pool_print "$i"; done
    pool_printed=$pool_count
    for ((i = 0; i < pool_count; i++)); do
        pool_ok "$i" || failed=1
        cat "$pool_dir/$i.time" >>"$pool_times" 2>/dev/null || true
    done
    return $failed
}

# check holds the build lock only to build and snapshot (check_build), then renders from
# the snapshot without it (check), so other checkouts build meanwhile. The snapshot, DIR/build, is
# tools/snapshot_build.py's clone of the build's bin/, lib/ and link map and of Ladybird's Base/res,
# its Mach-O files repointed to load every dylib from its own lib/. check runs everything from it:
# KR_BIN and KR_LIB name it, KR_RESOURCE_ROOT points the engine at its res/, and KR_SOURCE_DIR the
# tests' fonts at this checkout (not the build's karouka-src link, which the next build moves).
# A failed build fails it, with the build's status and before the snapshot (KR_OWNED_EXIT from
# apply_patches.sh included, so locked waits for the tree's owner).
check_build() {
    "$0" _build || return
    local out
    out="$(check_dir)"
    rm -rf "$out"
    mkdir -p "$out"
    printf '%s\n' "$KR_ROOT" >"$out/checkout"
    if ! take_snapshot "$out/build" "$out/snapshot.log"; then
        echo "FAIL snapshot of the build (see $out/snapshot.log)"
        return 1
    fi
}

# Snapshots the build into DIR (tools/snapshot_build.py; DIR is replaced), its output in LOG.
# Under the build lock, right after the build.
#   take_snapshot DIR LOG
take_snapshot() {
    python3 "$KR_ROOT/tools/snapshot_build.py" --build "$KR_BUILD" --resources "$KR_LADYBIRD/Base/res" \
        --out "$1" >"$2" 2>&1
}

# Points KR_BIN, KR_LIB, KR_MAP and the engine's resource root (KR_RESOURCE_ROOT) at the snapshot
# in DIR; with DIR/build_info (from_snapshot's), KR_BUILD_INFO is the build_info its build had.
# Fails when DIR holds no snapshot.
#   use_snapshot DIR
use_snapshot() {
    [[ -x "$1/bin/karouka_viewer" ]] || { echo "dev.sh: no build snapshot in $1" >&2; return 1; }
    KR_BIN="$1/bin" KR_LIB="$1/lib" KR_MAP="$1/libkarouka.map"
    export KR_RESOURCE_ROOT="$1/res"
    if [[ -f "$1/build_info" ]]; then KR_BUILD_INFO="$(cat "$1/build_info")"; fi
}

# run, bench and mem, like check, hold the build lock only to build and snapshot the build
# (_snapshot), then run from the snapshot without it: another checkout's build can relink or
# replace the build's files meanwhile, and nothing they run loads them. wpt, libweb, orderfile and
# startup do the same. bench, mem and startup measure holding the measure lock
# ($KR_MEASURE_LOCK), so they never overlap each other (the shared mem/ directory, and timings two
# measurements at once would skew), though a build can run beside them. build_info is taken under the build lock, so it names the tree the snapshot was
# built from. Each invocation has its own snapshot, $KR_BUILD/snapshots/<checkout_key>.<pid>,
# removed when it exits; one whose process is gone (SIGKILL) is removed by the next.
#   from_snapshot run|python|bench|mem|wpt|libweb|orderfile|census|startup ARGS...
from_snapshot() {
    local cmd="$1" base="$KR_BUILD/snapshots" dir pid snap
    shift
    mkdir -p "$base"
    for dir in "$base"/*; do
        [[ -e "$dir" ]] || continue
        pid="${dir%.log}"
        pid="${pid##*.}"
        [[ "$pid" =~ ^[0-9]+$ ]] && ! kill -0 "$pid" 2>/dev/null && rm -rf "$dir"
    done
    snap="$base/$(checkout_key).$$"
    trap "rm -rf '$snap' '$snap.log'" EXIT
    # While it builds, a signal here waits for the build (the build gets ^C itself, not TERM or HUP),
    # then exits through the trap: stopping the build midway could leave the shared Ladybird tree
    # half patched. From the snapshot on, run_forwarding passes INT, TERM and HUP on.
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
    locked _snapshot "$snap"
    echo "dev.sh: build lock released; $cmd runs from $snap" >&2
    export KR_SNAP="$snap"
    case "$cmd" in
        bench|mem|startup) run_forwarding "$0" _measured "$cmd" "$@" ;;
        *) run_forwarding "$0" "_$cmd" "$@" ;;
    esac
}

# The process run_forwarding waits on (fwd_pid), whether a signal came while it waited (fwd_got),
# the first signal and its exit status (fwd_sig, fwd_caught), and every process it was passed to.
fwd_pid=""
fwd_got=""
fwd_sig=""
fwd_caught=""
fwd_pids=()
# A file holding the pid of a process whose subtree run_forwarding mustn't signal while that process
# runs (check's build); empty for none.
fwd_hold=""

# Sends SIG to fwd_pid and every process under it (all listed before any is signalled), then
# SIGCONT, so that a stopped viewer (--hold, ^Z) gets it too, and notes CODE (128 + SIG's number)
# for run_forwarding. One that comes before fwd_pid is set, run_forwarding passes on once it is.
#   forward_signal SIG CODE
forward_signal() {
    fwd_got="$2"
    # check's build (and the patching under it) must not be stopped midway; the signal waits for it.
    local hold_pid=""
    while [[ -n "${fwd_hold:-}" ]] && hold_pid="$(cat "$fwd_hold" 2>/dev/null)" && [[ -n "$hold_pid" ]] &&
        kill -0 "$hold_pid" 2>/dev/null; do sleep 0.2; done
    [[ -n "$fwd_caught" ]] || { fwd_sig="$1"; fwd_caught="$2"; }
    [[ -n "$fwd_pid" ]] || return 0
    local pids=("$fwd_pid") i=0 kid
    while ((i < ${#pids[@]})); do
        for kid in $(pgrep -P "${pids[i]}" 2>/dev/null); do pids+=("$kid"); done
        i=$((i + 1))
    done
    kill -"$1" "${pids[@]}" 2>/dev/null || true
    kill -CONT "${pids[@]}" 2>/dev/null || true
    fwd_pids+=("${pids[@]}")
}

# Runs CMD... and passes INT, TERM and HUP sent to this shell on to it and every process
# under it (forward_signal). A foreground child would make this shell's trap wait for it to exit,
# and a viewer from run never does. CMD runs in the background with INT and QUIT back at their
# defaults (a background job of a script starts with them ignored), so ^C still stops it. After a
# signal, waits up to 10 s for every process it was passed to, then exits 128 + its number, through
# the EXIT trap (from_snapshot's removes the snapshot only after the viewer is gone); otherwise
# returns CMD's status.
#   run_forwarding CMD...
run_forwarding() {
    local rc t pid=""
    trap 'forward_signal INT 130' INT
    trap 'forward_signal TERM 143' TERM
    trap 'forward_signal HUP 129' HUP
    perl -e '$SIG{INT} = $SIG{QUIT} = "DEFAULT"; exec { $ARGV[0] } @ARGV or die "dev.sh: exec $ARGV[0]: $!\n"' "$@" &
    fwd_pid=$!
    [[ -z "$fwd_sig" ]] || forward_signal "$fwd_sig" "$fwd_caught"
    while :; do
        fwd_got="" rc=0
        wait "$fwd_pid" || rc=$?
        [[ -n "$fwd_got" ]] || break
    done
    [[ -n "$fwd_caught" ]] || return "$rc"
    for ((t = 0; t < 100; t++)); do
        for pid in ${fwd_pids[@]+"${fwd_pids[@]}"}; do kill -0 "$pid" 2>/dev/null && break; pid=""; done
        [[ -n "$pid" ]] || break
        sleep 0.1
    done
    exit "$fwd_caught"
}

check() {
    local out
    out="$(check_dir_path)"
    if [[ ! -x "$out/build/bin/karouka_viewer" ]]; then
        echo "FAIL no build snapshot in $out/build (check_build makes it)"
        return 1
    fi
    use_snapshot "$out/build"
    export KR_SOURCE_DIR="$KR_ROOT"
    # Every viewer check runs (wpt.py's and the multi-view groups' too) keeps its shader
    # cache in this run's own file for its page (karouka_viewer's KR_SHADER_CACHE_DIR), not the
    # machine-wide ~/Library/Caches/karouka/skia-shaders.bin: a page's first run here builds its
    # programs and later runs of it read them, whatever page ran last on the machine. check's own
    # pages stay off that file as well, so a later `run` or `mem` of one page doesn't precompile
    # them all. startup_check names its own file.
    export KR_SHADER_CACHE_DIR="$out/shader-cache"
    mkdir -p "$KR_SHADER_CACHE_DIR"
    local failed=0 started load_start phases=() stamp
    # check's wall time from here (the build is done) and its phases' are printed at the
    # end, with the slowest pool jobs of both rounds.
    started="$(now_s)" stamp="$started" load_start="$(sysctl -n vm.loadavg | awk '{ print $2 }')"
    pool_times="$out/job_times.tsv"
    : >"$pool_times"
    phase() { phases+=("$1 $(since_s "$stamp") s"); stamp="$(now_s)"; }
    # README lists every patch, dev.sh command and viewer flag in the tree, and nothing else.
    if python3 "$KR_ROOT/tools/readme_sync.py" >"$out/readme_sync.log" 2>&1; then
        echo "ok   readme_sync"
    else
        echo "FAIL readme_sync: $(head -1 "$out/readme_sync.log") (see $out/readme_sync.log)"
        failed=1
    fi
    # The vendored WPT corpus is exactly the pinned tree (tests/wpt/corpus.pin) and the
    # working tree hasn't changed it, so `dev.sh wpt`'s ratchet counts the corpus it was written for.
    if "$KR_ROOT/tools/wpt_vendor.sh" --check >"$out/wpt_vendor.log" 2>&1; then
        echo "ok   wpt_vendor --check"
    else
        local why
        why="$(head -1 "$out/wpt_vendor.log")"
        echo "FAIL wpt_vendor --check: ${why#wpt_vendor: } (see $out/wpt_vendor.log)"
        failed=1
    fi
    # From here to the startup gate everything runs through the job pool in two rounds: the
    # WPT filters, the test executables and every page alone, then everything that compares against
    # those captures (and the layout and texture checks, independent of both, in their place in the
    # output). The malloc and font size growth gates are queued first and may span both rounds;
    # their lines print last.
    pool_start "$out/jobs"
    pool_job --late malloc_growth_check "$out"
    pool_job --late font_size_growth_check "$out"
    # The WPT reftests a Ladybird patch fixed, by corpus-path substring (tests/wpt/check_filters.txt),
    # rendered and ratcheted as dev.sh wpt does (seconds, unlike the whole corpus), so a patch-series change
    # that breaks them again fails check rather than only the next full wpt run.
    # One job, one wpt.py run for every filter, so the corpus walk and the first viewer
    # launches from the new snapshot are paid once, not per filter.
    local filter filters=()
    while IFS= read -r filter; do
        filter="${filter%%#*}"
        filter="${filter%"${filter##*[![:space:]]}"}"
        [[ -z "$filter" ]] && continue
        filters+=("$filter")
    done <"$KR_ROOT/tests/wpt/check_filters.txt"
    if ((${#filters[@]})); then pool_job wpt_filter_check "$out" "${filters[@]}"; fi
    local test
    for test in "${KAROUKA_TESTS[@]}"; do
        pool_job check_test "$out" "$test"
    done
    # The _karouka module's tests (tests/python/), as dev.sh python runs them.
    for test in "$KR_ROOT"/tests/python/*.py; do
        pool_job python_test "$out" "$test"
    done
    local view=(--headless --size 800x600 --frames "$CHECK_FRAMES" --check-title)
    local page passed=() pages=() demos=() first_page first_demo
    first_page=$pool_count
    for page in "$KR_ROOT"/pages/tests/*.html; do
        pages+=("$page")
        pool_job check_page "$out" "" "$page" settle
    done
    # The demo pages render the same way (logs and captures in check/demo/), so a demo
    # page's title meta is enforced too: trellis_page.html's needs the stand-in host to answer its
    # engine.trigger("echo", ...). They stay out of the multi-view groups below.
    mkdir -p "$out/demo"
    while IFS= read -r page; do demos+=("$page"); done < <(demo_pages)
    first_demo=$pool_count
    for page in ${demos[@]+"${demos[@]}"}; do
        pool_job check_page "$out/demo" demo/ "$page"
    done
    pool_wait_for "$first_page" "$pool_count"
    phase "round 1"
    # Every page that passed alone, as METAL_CAPTURE|LABEL_PREFIX|PAGE, for the software and host io runs.
    local alone=() i
    for ((i = 0; i < ${#pages[@]}; i++)); do
        if pool_ok $((first_page + i)); then
            passed+=("${pages[i]}")
            alone+=("$out/$(page_name "${pages[i]}").png||${pages[i]}")
        fi
    done
    for ((i = 0; i < ${#demos[@]}; i++)); do
        if pool_ok $((first_demo + i)); then
            alone+=("$out/demo/$(page_name "${demos[i]}").png|demo/|${demos[i]}")
        fi
    done
    software_check "$out" ${alone[@]+"${alone[@]}"}
    host_io_check "$out" ${alone[@]+"${alone[@]}"}
    # Once loaded (frame 10 on), animations_page.html (compositor animations) and
    # the static demo pages run no layout update (kr_view_stats.layout_updates): a rendering update
    # nothing invalidated skips step 16's layout (patch 0046). The counter itself is checked by every
    # run laying out while it loads (frames 0-2).
    # hud_page.html (bindings written every frame) lays out once a frame; the second, no-op
    # update_layout() LocalNavigable::paint_next_frame_if_needed ran before it paints is gone (0046).
    # trellis_page.html scrolled by a wheel step a frame lays out in none of them either: a wheel step and the
    # viewport scroll it performs lay out only when something invalidated layout (patch 0065). An entry's third field
    # is the run's input flags, and its log is named <page>_<first flag>_layouts.log (trellis_scroll_layouts.log).
    # Nor does a mouse move a frame across trellis and showcase (hover rules met on the way included), nor a
    # down-arrow press a frame on trellis: the event handler's entry points lay out only when something invalidated
    # layout (patch 0068). Nor a mouse move a frame across sashimi, whose compositor animations (a spinner's
    # rotation, a pulse's opacity) the move's hit test reads off the visual context tree sampled at the compositor's
    # time instead of restyling their targets and laying out first (patch 0071; without it, 20 layouts in 20 moves).
    # Nor a click (--poke: a move, then down and up a frame apart) on trellis or on sashimi: an event handler
    # entry point that finds only style pending (the :active, :focus and :hover states the dispatch set) brings style up
    # to date and lays out only if that left layout unclean (patch 0074), and selectionchange no longer lays out to read
    # the selected text for a primary clipboard karouka doesn't have (without these, 3 and 4 layouts a click). A move a frame
    # across animations_page lays out once in all, in the rendering update after a mouseenter toggles a hover class on
    # whose transition starts (2 without them): an entry's limit N@F,T also caps the run's total from F on at T.
    local layout_check
    for layout_check in animations_page:0@10 hud_page:1@10 restyle_page:0@10 sashimi_page:0@10 \
        showcase_page:0@10 demo_index:0@10 trellis_page:0@10 "trellis_page:0@10:--scroll 0,20@10..29" \
        "trellis_page:0@10:--move 50,50:700,500@10x20" "showcase_page:0@10:--move 50,50:700,500@10x20" \
        "sashimi_page:0@10:--move 50,50:700,500@10x20" \
        "trellis_page:0@10:--key 125@10..29" "trellis_page:0@10:--poke 100,100@15" \
        "sashimi_page:0@10:--poke 100,100@15" "animations_page:1@10,1:--move 50,50:700,500@10x20"; do
        pool_job layout_check_run "$out" "$layout_check"
    done
    # The off-screen animation cull. sashimi's only rendered animations (a spinner and a pulse) sit
    # ~1050 px down, so at 1280x1200 they are on screen and every one of 600 frames renders, and at 1280x720 they
    # are off screen and the page renders its first frame and one more. ~1 s each.
    pool_job cull_check_run "$out" 1200 590 ge
    pool_job cull_check_run "$out" 720 3 le
    # Drawn straight into a texture of the viewer's (kr_view_set_output2), with no IOSurface,
    # an animated page and a scrolled one match a reference view of the same page in its IOSurface.
    local texture_check
    for texture_check in "demo/animations_page.html" "tests/scroll_input.html --scroll 0,100@4..6 --poke 40,40@10"; do
        pool_job texture_check_run "$out" "$texture_check"
    done
    multi_view_check "$out" ${passed[@]+"${passed[@]}"}
    pool_wait || failed=1
    phase "round 2"
    # The startup gate times the viewer, so it takes the measure lock as bench, mem and startup do
    # (waiting while another checkout measures, and making them wait): _check_startup runs it under that lock.
    with_lock_at "$KR_MEASURE_LOCK" "the measure lock (another checkout's bench, mem or startup is running)" \
        "$0" _check_startup "$out" || failed=1
    orderfile_check "$out"
    phase startup
    local summary="" p
    for p in "${phases[@]}"; do summary+="${summary:+, }$p"; done
    echo "time check $(since_s "$started") s after the build ($summary), load $load_start -> $(sysctl -n vm.loadavg | awk '{ print $2 }')"
    echo "time slowest jobs: $(pool_slowest 6)"
    echo "check output: $out"
    return $failed
}

# check's run of the WPT filters (the lines of tests/wpt/check_filters.txt), all in one wpt.py run
# (a document runs when it matches any filter, and each filter must match one), logged to
# DIR/wpt.log, its captures and results in DIR/wpt/. One viewer at a time: it is a pool job.
#   wpt_filter_check DIR FILTER...
wpt_filter_check() {
    local out="$1" filter args=()
    shift
    for filter in "$@"; do args+=(--filter "$filter"); done
    if nice -n 10 python3 "$KR_ROOT/tools/wpt.py" --viewer "$KR_BIN/karouka_viewer" --out "$out/wpt" \
        --jobs 1 "${args[@]}" >"$out/wpt.log" 2>&1; then
        for filter in "$@"; do echo "ok   wpt $filter"; done
    else
        echo "FAIL wpt, $# check filters (see $out/wpt.log)"
        return 1
    fi
}

# check's run of one test executable, logged to DIR/TEST.log.
#   check_test DIR TEST
check_test() {
    if "$KR_BIN/$2" >"$1/$2.log" 2>&1; then
        echo "ok   $2"
    else
        echo "FAIL $2 (see $1/$2.log)"
        return 1
    fi
}

# Runs one tests/python/ script against the _karouka module in $KR_LIB (a snapshot's), with the
# interpreter it was built for, logged to DIR/python_NAME.log.
#   python_test DIR TEST.py
python_test() {
    local name python
    name="$(basename "$2" .py)"
    if ! python="$(cat "$KR_LIB/_karouka.python" 2>/dev/null)" || [[ ! -x "$python" ]]; then
        echo "FAIL python $name: no interpreter for the _karouka module ($KR_LIB/_karouka.python)"
        return 1
    fi
    if PYTHONPATH="$KR_LIB" KR_SOURCE_DIR="$KR_ROOT" "$python" -s "$2" >"$1/python_$name.log" 2>&1; then
        echo "ok   python $name"
    else
        echo "FAIL python $name (see $1/python_$name.log)"
        return 1
    fi
}

# dev.sh python: the given tests/python/ scripts, or all of them, one after another.
#   python_tests [TEST.py...]
python_tests() {
    local out="$KR_BUILD/python/$(basename "$KR_ROOT")" test failed=0 tests=("$@")
    ((${#tests[@]})) || tests=("$KR_ROOT"/tests/python/*.py)
    mkdir -p "$out"
    for test in "${tests[@]}"; do
        python_test "$out" "$(cd "$(dirname "$test")" && pwd)/$(basename "$test")" || failed=1
    done
    return $failed
}

# One of check's layout-count gates: ENTRY is PAGE:LIMIT[:FLAGS] (check's list explains them).
# Uses check's $view.
#   layout_check_run DIR ENTRY
layout_check_run() {
    local out="$1" name limit total flags first_flag log ran
    name=${2%%:*}
    limit=${2#*:}
    flags=
    if [[ "$limit" == *:* ]]; then flags=${limit#*:}; limit=${limit%%:*}; fi
    total= ran=
    if [[ "$limit" == *,* ]]; then total=${limit#*,}; limit=${limit%%,*}; fi
    first_flag=${flags%% *}
    log="$out/${name%_page}${flags:+_${first_flag#--}}_layouts.log"
    # shellcheck disable=SC2086 # the entry's input flags split into words
    if "$KR_BIN/karouka_viewer" "${view[@]}" --max-layouts-per-frame "$limit" $flags \
        "$KR_ROOT/pages/demo/$name.html" >"$log" 2>&1 &&
        ran=$(sed -n 's/.*layout check .* ran \([0-9]*\) layout updates.*/\1/p' "$log") &&
        [[ -z "$total" || ( -n "$ran" && "$ran" -le "$total" ) ]]; then
        echo "ok   $name${flags:+ ($flags)} layouts ($(sed -n 's/.*layout check .* frames \([0-9-]*\) ran \([0-9]*\) layout updates, most \([0-9]*\) .*/frames \1: \2, most \3 a frame/p' "$log")${total:+, at most $total in all})"
    elif [[ -n "$total" && -n "${ran:-}" && "$ran" -gt "$total" ]]; then
        echo "FAIL $name${flags:+ ($flags)} layouts ($ran in all, at most $total; see $log)"
        return 1
    else
        echo "FAIL $name${flags:+ ($flags)} layouts (see $log)"
        return 1
    fi
}

# One of check's animation cull gates: sashimi_page.html at 1280xHEIGHT for 600 frames renders
# (--stats' rendered=) at least (ge) or at most (le) LIMIT of them. Logs to DIR/sashimi_HEIGHT_cull.log.
#   cull_check_run DIR HEIGHT LIMIT ge|le
cull_check_run() {
    local out="$1" height="$2" limit="$3" op="$4" log rendered want
    log="$out/sashimi_${height}_cull.log"
    want="at least $limit"
    [[ "$op" == ge ]] || want="at most $limit"
    if "$KR_BIN/karouka_viewer" --headless --size "1280x$height" --frames 600 --stats \
        "$KR_ROOT/pages/demo/sashimi_page.html" >"$log" 2>&1 &&
        rendered=$(sed -n 's/.*karouka-stats .* rendered=\([0-9]*\) .*/\1/p' "$log") && [[ -n "$rendered" ]]; then
        if [[ ( "$op" == ge && "$rendered" -ge "$limit" ) || ( "$op" == le && "$rendered" -le "$limit" ) ]]; then
            echo "ok   sashimi_page at 1280x$height renders $rendered of 600 frames (animation cull, $want)"
            return 0
        fi
        echo "FAIL sashimi_page at 1280x$height rendered $rendered of 600 frames (want $want; see $log)"
        return 1
    fi
    echo "FAIL sashimi_page at 1280x$height (see $log)"
    return 1
}

# One of check's output texture runs: ENTRY is a page under pages/ and its input flags.
#   texture_check_run DIR ENTRY
texture_check_run() {
    local out="$1" name
    name=$(basename "${2%% *}" .html)
    # shellcheck disable=SC2086 # the page's input flags split into words
    if "$KR_BIN/karouka_viewer" "${view[@]}" --output-texture "$KR_ROOT/pages/"$2 \
        >"$out/${name}_texture.log" 2>&1 && grep -q "output texture .* matches" "$out/${name}_texture.log"; then
        echo "ok   $name output texture ($(sed -n 's/.*(\([0-9]* pixels differ\)).*/\1/p' "$out/${name}_texture.log"))"
    else
        echo "FAIL $name output texture (see $out/${name}_texture.log)"
        return 1
    fi
}

# Every page that passed alone (pages/tests and the demo pages) renders again on the software
# backend (--backend software, KR_BACKEND_SOFTWARE: Skia's CPU rasterizer, no GPU context, the viewer
# makes no Metal device), with the same frames, scripted input and --check-title, captured to
# check/software/[demo/]NAME.png. Each capture must match the page's Metal capture within
# CHECK_SOFTWARE_TOLERANCE. Arguments: METAL_CAPTURE|LABEL_PREFIX|PAGE, one per page.
software_check() {
    local out="$1/software" entry
    shift
    mkdir -p "$out/demo"
    for entry in "$@"; do
        pool_job software_page "$out" "$entry"
    done
}
# One page of software_check, a check job: OUT is check/software, ENTRY one METAL_CAPTURE|LABEL_PREFIX|PAGE.
software_page() {
    local out="$1" entry="$2" ref prefix page name input dir summary
    ref="${entry%%|*}" page="${entry##*|}" prefix="${entry#*|}" prefix="${prefix%%|*}"
    name="$(page_name "$page")" input="$(check_input "$page")" dir="$out${prefix:+/${prefix%/}}"
    # shellcheck disable=SC2086 # the page's input flags, word-split on purpose
    if "$KR_BIN/karouka_viewer" "${view[@]}" --backend software $input \
        --capture "$dir/$name.png" "$page" >"$dir/$name.log" 2>&1 &&
        python3 "$KR_ROOT/tools/pngdiff.py" --tolerance "$CHECK_SOFTWARE_TOLERANCE" "$ref" "$dir/$name.png" \
            >>"$dir/$name.log" 2>&1 &&
        check_pixels "$(check_meta "$page" pixels)" "$dir/$name.png" "$dir/$name.log" "$name"; then
        summary="$(sed -n 's/^pngdiff: .*(\([0-9.]*%\)) differ by more than \([0-9]*\), largest channel delta \([0-9]*\).*/\1 over \2, max delta \3/p' "$dir/$name.log")"
        echo "ok   software $prefix$name (${summary:-identical to Metal})"
    else
        echo "FAIL software $prefix$name (see $dir/$name.log)"
        return 1
    fi
}

# Every page that passed alone renders again with its loads routed through the
# host (--host-io async: the viewer's kr_host_io.request queues each read and completes it with
# kr_io_complete, its buffer borrowed until release, at the start of the next frame), with the same
# frames, scripted input and --check-title, captured to check/host_io/[demo/]NAME.png, and in the same
# run checks partial raster (--check-full-raster). Host io: the capture must match the page's own
# capture (ResourceLoader reading the files itself) exactly, the viewer's closing "host io served N
# reads" line must count at least the page itself (the loads really went through the host), and no
# completed read may have kept its borrowed buffer. Reads still queued at the end are allowed: a page
# that loads every frame (resource_churn) always has the next one.
# Full raster: the run's last frame, rasterized whole, must match the pixels its partial rasters (each
# frame rasterized into its damage) left exactly: damage that misses a change leaves stale pixels there
# (animations_page's background-color animation did, before patch 0066 compared sampled colors). Metal
# only: Skia's CPU rasterizer covers an edge cut by the damage's clip slightly differently
# (karouka_partial_raster_test). Damage that goes wrong only with the files read in the request leaves
# the page's own capture stale instead, and its host io capture differs from it; when that happens, or
# the run ended before its full raster check, full_raster_page decides the full raster line with a
# separate run: one with KR_FULL_RASTER=1 (each rendered frame rasterized whole) must
# capture the page's own pixels exactly.
# Arguments: METAL_CAPTURE|LABEL_PREFIX|PAGE, one per page.
host_io_check() {
    local out="$1" entry
    shift
    mkdir -p "$out/host_io/demo" "$out/full_raster/demo"
    for entry in "$@"; do
        pool_job host_io_page "$out" "$entry"
    done
}
# One page of host_io_check, a check job printing its host io and full raster lines: OUT is check's
# directory, ENTRY one METAL_CAPTURE|LABEL_PREFIX|PAGE.
host_io_page() {
    local out="$1" entry="$2" ref prefix page name input dir log reads why="" rc=0 raster
    ref="${entry%%|*}" page="${entry##*|}" prefix="${entry#*|}" prefix="${prefix%%|*}"
    name="$(page_name "$page")" input="$(check_input "$page")"
    dir="$out/host_io${prefix:+/${prefix%/}}" log="$out/host_io${prefix:+/${prefix%/}}/$name.log"
    # shellcheck disable=SC2086 # the page's input flags, word-split on purpose
    "$KR_BIN/karouka_viewer" "${view[@]}" --host-io async --check-full-raster $input \
        --capture "$dir/$name.png" "$page" >"$log" 2>&1 || rc=$?
    # The viewer exits 4 when its full raster check was all that failed.
    if ((rc != 0 && rc != 4)); then
        why="the viewer failed"
    elif ! python3 "$KR_ROOT/tools/pngdiff.py" "$ref" "$dir/$name.png" >>"$log" 2>&1; then
        why="differs from its capture without host io"
    elif ! check_pixels "$(check_meta "$page" pixels)" "$dir/$name.png" "$log" "$name"; then
        why="pixels differ"
    fi
    reads="$(sed -n 's/^karouka_viewer: host io served \([0-9]*\) reads.*/\1/p' "$log")"
    if [[ -z "$why" ]] && ((${reads:-0} < 1)); then
        echo "  $name: the host served no reads (karouka_viewer: host io served ... line: ${reads:-none})" >>"$log"
        why="no reads went through the host"
    elif [[ -z "$why" ]] && grep -q "was completed but its buffer not released" "$log"; then
        why="a borrowed buffer was not released"
    fi
    if [[ -z "$why" ]]; then
        echo "ok   host io $prefix$name ($reads reads)"
    else
        echo "FAIL host io $prefix$name: $why (see $log)"
    fi
    raster="$(sed -En 's/^karouka_viewer: full raster check .*: the whole raster (matches|DIFFERS FROM) .*/\1/p' "$log")"
    if [[ "$raster" == "DIFFERS FROM" ]]; then
        echo "FAIL full raster $prefix$name: the last frame rasterized whole differs from its partial rasters (see $log)"
        why="${why:-full raster}"
    elif [[ "$raster" == matches && "$why" != "differs from its capture without host io" && "$why" != "the viewer failed" ]]; then
        echo "ok   full raster $prefix$name"
    else
        full_raster_page "$out/full_raster" "$entry" || why="${why:-full raster}"
    fi
    [[ -z "$why" ]]
}
# host_io_page's fallback, a full raster run of one page: OUT is
# check/full_raster, ENTRY one METAL_CAPTURE|LABEL_PREFIX|PAGE.
full_raster_page() {
    local out="$1" entry="$2" ref prefix page name input dir
    ref="${entry%%|*}" page="${entry##*|}" prefix="${entry#*|}" prefix="${prefix%%|*}"
    name="$(page_name "$page")" input="$(check_input "$page")" dir="$out${prefix:+/${prefix%/}}"
    # shellcheck disable=SC2086 # the page's input flags, word-split on purpose
    if KR_FULL_RASTER=1 "$KR_BIN/karouka_viewer" "${view[@]}" $input \
        --capture "$dir/$name.png" "$page" >"$dir/$name.log" 2>&1 &&
        python3 "$KR_ROOT/tools/pngdiff.py" "$ref" "$dir/$name.png" >>"$dir/$name.log" 2>&1; then
        echo "ok   full raster $prefix$name"
    else
        echo "FAIL full raster $prefix$name (see $dir/$name.log)"
        return 1
    fi
}

# The pages that rendered alone, again four views to a system (--second), and again with the second
# view closed halfway (--close-second): every view still alive at the end has to capture exactly the
# pixels its page captured alone. The pages without scripted input go four to a group, wrapping
# around to the first pages so each run has four views. A page with scripted input (check_input)
# gets two groups of its own. In the first it leads (the viewer's default input view): itself with
# the input, itself again without (held to its no-input capture), then the first two pages without
# input. In the second it comes last and gets the input through --input-view 4, behind
# itself without input: input that lands on the first view instead of a later one changes the first
# view's capture and leaves the fourth's unscrolled. pages/tests/clock_animating.html, still
# animating at the last frame, is put first (sorting alone would put the
# animated_* pages ahead of it), so it leads the first group and sits third in each scripted
# one: a view whose clock runs apart from the others', or input that reaches the wrong view, shows
# as a capture that differs.
# One rendering update covers every view of the system, so each surviving view's --stats line has to
# report the same nonzero updates= count (kr_view_stats.updates_run), not only the view that ran it.
multi_view_check() {
    local ref="$1" out="$1/multi"; shift
    local group=0 start i mode page
    local plain=() scripted=() groups=()
    for page in "$@"; do
        if [[ -n "$(check_input "$page")" ]]; then
            scripted+=("$page")
        elif [[ "$(basename "$page")" == clock_animating.html ]]; then
            plain=("$page" ${plain[@]+"${plain[@]}"})
        else
            plain+=("$page")
        fi
    done
    rm -rf "$out"
    mkdir -p "$out"
    # A group is four "page|input flags|reference capture" members, tab-separated.
    member() { printf '%s|%s|%s' "$1" "$2" "$3"; }
    # The i-th page without input (wrapping around), or the first scripted page without its input.
    filler() {
        if ((${#plain[@]})); then
            local page="${plain[$(($1 % ${#plain[@]}))]}"
            member "$page" "" "$ref/$(basename "$page" .html).png"
        else
            member "${scripted[0]}" "" "$ref/$(basename "${scripted[0]}" .html).no-input.png"
        fi
    }
    for page in ${scripted[@]+"${scripted[@]}"}; do
        local name with without
        name="$(basename "$page" .html)"
        with="$(member "$page" "$(check_input "$page")" "$ref/$name.png")"
        without="$(member "$page" "" "$ref/$name.no-input.png")"
        groups+=("$with"$'\t'"$without"$'\t'"$(filler 0)"$'\t'"$(filler 1)")
        groups+=("$without"$'\t'"$(filler 1)"$'\t'"$(filler 0)"$'\t'"$with")
    done
    for ((start = 0; start < ${#plain[@]}; start += 4)); do
        local line=""
        for ((i = 0; i < 4; i++)); do
            page="${plain[$(((start + i) % ${#plain[@]}))]}"
            ((i)) && line+=$'\t'
            line+="$(member "$page" "" "$ref/$(basename "$page" .html).png")"
        done
        groups+=("$line")
    done
    local spec
    for spec in ${groups[@]+"${groups[@]}"}; do
        group=$((group + 1))
        for mode in views close; do
            pool_job multi_view_run "$out" "$group" "$mode" "$spec"
        done
    done
}

# One run of multi_view_check, a check job: group number GROUP of four tab-separated members, as
# multi_view_check builds them, in MODE views (four views) or close (the second closed halfway).
#   multi_view_run OUT GROUP MODE SPEC
multi_view_run() {
    local out="$1" group="$2" mode="$3" spec="$4" i page
    local members=() refs=() names=() args=() m input=""
    IFS=$'\t' read -r -a members <<<"$spec"
    for ((i = 0; i < 4; i++)); do
        IFS='|' read -r page m refs[i] <<<"${members[i]}"
        # At most one member per group has input; the viewer sends it to that view.
        [[ -n "$m" ]] && input="$m --input-view $((i + 1))"
        members[i]="$page"
        names[i]="$(basename "$page" .html)${m:++input}"
    done
    args=("${members[0]}")
    for ((i = 1; i < 4; i++)); do args+=(--second "${members[i]}"); done
    local label="$mode-$group" extra=()
    [[ "$mode" == close ]] && extra=(--close-second $((CHECK_FRAMES / 2)))
    local log="$out/$label.log" ok=1
    # shellcheck disable=SC2086 # the input member's flags, word-split on purpose
    if ! "$KR_BIN/karouka_viewer" --headless --size 800x600 --frames "$CHECK_FRAMES" --stats --check-title \
        ${extra[@]+"${extra[@]}"} $input --capture "$out/$label.png" "${args[@]}" >"$log" 2>&1; then
        ok=0
    fi
    for ((i = 0; i < 4; i++)); do
        local shot="$out/$label.png"
        ((i)) && shot="$out/$label-$((i + 1)).png"
        if [[ "$mode" == close && $i == 1 ]]; then
            # The closed view captures nothing.
            [[ -e "$shot" ]] && { echo "closed view 2 still captured $shot" >>"$log"; ok=0; }
            continue
        fi
        if [[ ! -e "$shot" ]]; then
            echo "view $((i + 1)) (${names[i]}): no capture" >>"$log"
            ok=0
        elif ! python3 "$KR_ROOT/tools/pngdiff.py" "${refs[i]}" "$shot" >>"$log" 2>&1; then
            echo "view $((i + 1)) (${names[i]}): differs from its single-view capture ${refs[i]}" >>"$log"
            ok=0
        elif [[ "${refs[i]}" != *.no-input.png ]] &&
            ! check_pixels "$(check_meta "${members[i]}" pixels)" "$shot" "$log" "view $((i + 1)) (${names[i]})"; then
            # The samples hold for a view that renders the page as its alone capture did
            # (with its input, if any), not for a page shown without the input it was pinned with.
            ok=0
        fi
    done
    local views=4 updates
    [[ "$mode" == close ]] && views=3
    updates="$(sed -n 's/^karouka-stats .* updates=\([0-9]*\) .*/\1/p' "$log" | tr '\n' ' ')"
    # shellcheck disable=SC2086 # one word per view
    if [[ "$(printf '%s\n' $updates | wc -l | tr -d ' ')" != "$views" \
        || "$(printf '%s\n' $updates | sort -u | wc -l | tr -d ' ')" != 1 || "${updates%% *}" == 0 ]]; then
        echo "updates_run per view: ${updates:-none}; want $views equal nonzero counts" >>"$log"
        ok=0
    fi
    local what="4 views"
    [[ "$mode" == close ]] && what="4 views, close 2nd"
    if ((ok)); then
        echo "ok   $what: ${names[*]}"
    else
        echo "FAIL $what: ${names[*]} (see $log)"
        return 1
    fi
}

# mem's held viewer while it runs. kill_held (its EXIT trap) SIGKILLs it, stopped or not: SIGKILL is
# the one signal a stopped process doesn't keep pending.
held_pid=""
kill_held() {
    [[ -n "$held_pid" ]] || return 0
    kill -KILL "$held_pid" 2>/dev/null || true
    wait "$held_pid" 2>/dev/null || true
    held_pid=""
}

# A viewer held by hand (--hold, KR_MEM_HOLD=<phase>, or ^Z) stays stopped until someone
# sends it SIGCONT or kills it. It keeps its memory, IOSurfaces and GPU driver memory, which skew
# the next mem measurement (and, when held by mem, the measure lock, which every bench and mem waits
# for). check and mem kill such viewers before they take the build lock. Every checkout runs a
# snapshot of the one shared build's viewer, so this can't tell checkouts apart: it takes any of
# this user's stopped karouka_viewer processes, except mem's own held run (its parent runs dev.sh
# _mem): that is another checkout's mem, which holds the measure lock while vmmap reads the run.
reap_stopped_viewers() {
    local pid ppid stat comm parent
    while read -r pid ppid stat comm; do
        [[ "$stat" == T* && "${comm##*/}" == karouka_viewer ]] || continue
        parent="$(ps -o command= -p "$ppid" 2>/dev/null || true)"
        [[ "$parent" == *"dev.sh _mem"* ]] && continue
        if kill -KILL "$pid" 2>/dev/null; then
            echo "dev.sh: killed stopped karouka_viewer $pid (held outside dev.sh mem: $comm)" >&2
        fi
    done < <(ps -U "$(id -u)" -o pid=,ppid=,stat=,comm=)
    return 0
}

# Median of the arguments (numbers), one decimal.
median() {
    printf '%s\n' "$@" | sort -n | awk '{ v[NR] = $1 } END { if (NR % 2) printf "%.1f", v[(NR + 1) / 2]; else printf "%.1f", (v[NR / 2] + v[NR / 2 + 1]) / 2 }'
}

# mem's numeric flags and their $KR_MEM_* defaults, checked before mem takes the build lock:
# the viewer atoi()s --frames, so --frames -5 or --frames x ran it with no frame limit, and it held
# the lock until killed. --frames is 0 or more (0 loads without rendering); --runs and --views are 1
# or more. Plain decimal, at most 9 digits: bash reads a leading 0 as octal and atoi overflows.
# Exits 2 with the reason.
mem_check_count() { # NAME VALUE MIN (0 or 1)
    local pattern='^[1-9][0-9]{0,8}$'
    (($3 == 0)) && pattern='^(0|[1-9][0-9]{0,8})$'
    [[ "$2" =~ $pattern ]] || { echo "dev.sh mem: $1 must be an integer, at least $3 (got '$2')" >&2; exit 2; }
}
mem_check_args() {
    local name value
    mem_check_count '$KR_MEM_FRAMES' "${KR_MEM_FRAMES:-600}" 0
    mem_check_count '$KR_MEM_RUNS' "${KR_MEM_RUNS:-5}" 1
    mem_check_count '$KR_MEM_VIEWS' "${KR_MEM_VIEWS:-1}" 1
    while (($#)); do
        case "$1" in
            --frames|--runs|--views)
                name="$1"
                (($# >= 2)) || { echo "dev.sh mem: $name needs a value" >&2; exit 2; }
                value="$2"
                if [[ "$name" == --frames ]]; then mem_check_count "$name" "$value" 0; else mem_check_count "$name" "$value" 1; fi
                shift 2 ;;
            *) shift ;;
        esac
    done
}

# Peak RSS and peak footprint (from /usr/bin/time -l) of $KR_MEM_RUNS headless runs, each run and the
# median, then one more run held at its end (--hold) for vmmap's IOSurface region count.
#   tools/dev.sh mem [page] [--frames N] [--runs N] [--views N] [--attribute] [--no-render]
#                    [--hold] [--malloc-history]
# --hold also keeps `vmmap -v -wide` and `footprint` of the held run, and runs it with
# --memory-stats for its malloc_zone_mb and font_cache_strikes (printed, and added to the karouka-mem
# line). --malloc-history
# implies --hold and runs the held run under MallocStackLogging=lite, adding `heap -s` and
# `malloc_history -allBySize`: MSL's own bookkeeping is in that run's zone and footprint, so its
# vmmap and malloc_zone_mb read higher than a plain hold's (14.5 vs 12.8 MB dirty).
# --views N (default $KR_MEM_VIEWS or 1) opens N views of the page in one system, the first
# plus N-1 --second, so footprint(N) - footprint(1) is what N-1 more views cost.
# --no-render passes the viewer's --no-render: frames advance (style, layout, display list) but
# are never rendered, so the numbers leave out the Metal driver and the render target.
# --frames 0 loads the page without rendering it. --attribute: one --mem-phases-heap run with
# src/tools/miprof.cpp inserted, then tools/miprof.py's report of the live kmalloc bytes per call
# site and per mimalloc heap at each phase (default --frames 1; raw snapshots in mem/miprof/). The last line is for scripts:
#   karouka-mem page=... frames=N views=N runs=N rss_mb=M footprint_mb=M iosurface_regions=N iosurface_mb=M
#       ioaccel_mb=M ladybird_tree=ID series=match|differs owner=... karouka=COMMIT  (build_info)
mem() {
    local arg
    for arg in "$@"; do [[ "$arg" == --all-demo ]] && { mem_all_demo "$@"; return; }; done
    mem_check_args "$@" # dispatch checked these before the lock; this covers _mem and --all-demo's pages
    local page="" frames="" runs="${KR_MEM_RUNS:-5}" views="${KR_MEM_VIEWS:-1}" attribute=0 extra=() hold=0 msl=0
    while (($#)); do
        case "$1" in
            --attribute) attribute=1; shift ;;
            --hold) hold=1; shift ;;
            --malloc-history) hold=1; msl=1; shift ;;
            --no-render) extra+=(--no-render); shift ;;
            --frames) frames="$2"; shift 2 ;;
            --runs) runs="$2"; shift 2 ;;
            --views) views="$2"; shift 2 ;;
            -*) echo "dev.sh mem: unknown flag $1" >&2; return 2 ;;
            *) page="$(resolve_page "$1")"; shift ;;
        esac
    done
    local dir="$KR_BUILD/mem" info
    mkdir -p "$dir"
    [[ -n "$page" ]] || page="$(empty_page)"
    info="${KR_BUILD_INFO:-$(build_info)}"
    # Views 2..N: the same page again, each its own view of the one system.
    local seconds=() v
    for ((v = 2; v <= views; v++)); do seconds+=(--second "$page"); done
    # The shader cache: this page's own, not the viewer's default ~/Library/Caches one, whose warm
    # list is whatever page last ran on the machine (49 other pages' programs precompiled at
    # kr_system_create2 cost the empty page 1.9 MB footprint and 3.5 MB RSS, also after 600 frames).
    # Remade every time by one unmeasured run of at least recorded_frames (4) frames, so the measured
    # runs are a second launch of an app that has shown this page before.
    local shader_cache="$dir/shader-cache/$(printf '%s' "$page" | shasum | cut -c1-12).bin"
    mem_seed_shader_cache() {
        mkdir -p "$(dirname "$shader_cache")"
        rm -f "$shader_cache"
        "$KR_BIN/karouka_viewer" "$page" ${seconds[@]+"${seconds[@]}"} --headless --frames "$(($1 > 4 ? $1 : 4))" \
            --shader-cache "$shader_cache" >/dev/null 2>"$dir/seed.log" || { cat "$dir/seed.log" >&2; return 1; }
    }
    if ((attribute)); then
        ((!hold)) || { echo "dev.sh mem: --attribute takes no --hold/--malloc-history (it holds no run)" >&2; return 2; }
        frames="${frames:-1}"
        mem_seed_shader_cache "$frames"
        local out="$dir/miprof"
        rm -rf "$out"; mkdir -p "$out"
        echo "page            $page"
        echo "frames          $frames (karouka_miprof inserted; allocation is ~10x slower)"
        echo "views           $views"
        echo "build           $info"
        KR_MIPROF_DIR="$out" DYLD_INSERT_LIBRARIES="$KR_LIB/libkarouka_miprof.dylib" \
            "$KR_BIN/karouka_viewer" "$page" ${seconds[@]+"${seconds[@]}"} --headless --frames "$frames" ${extra[@]+"${extra[@]}"} --shader-cache "$shader_cache" --mem-phases-heap >/dev/null 2>"$out/phases.log" \
            || { cat "$out/phases.log" >&2; return 1; }
        grep '^karouka-mem-phase' "$out/phases.log"
        python3 "$KR_ROOT/tools/miprof.py" "$out" ${KR_MIPROF_ARGS:-}
        return
    fi
    frames="${frames:-${KR_MEM_FRAMES:-600}}"
    mem_seed_shader_cache "$frames"
    local viewer=("$KR_BIN/karouka_viewer" "$page" ${seconds[@]+"${seconds[@]}"} --headless --frames "$frames" ${extra[@]+"${extra[@]}"} --shader-cache "$shader_cache")
    local log="$dir/time.log" rss=() fp=() i r f
    echo "page            $page"
    echo "frames          $frames"
    echo "views           $views"
    echo "build           $info"
    for ((i = 1; i <= runs; i++)); do
        /usr/bin/time -l "${viewer[@]}" >/dev/null 2>"$log" || { cat "$log" >&2; return 1; }
        read -r r f < <(awk '
            /maximum resident set size/ { rss = $1 }
            /peak memory footprint/     { fp = $1 }
            END { printf "%.1f %.1f\n", rss / 1048576, fp / 1048576 }' "$log")
        rss+=("$r"); fp+=("$f")
        printf 'run %-2d          RSS %6.1f MB   footprint %6.1f MB\n' "$i" "$r" "$f"
    done
    local rss_mb fp_mb
    rss_mb="$(median "${rss[@]}")"; fp_mb="$(median "${fp[@]}")"
    printf 'median of %-4s  RSS %6.1f MB   footprint %6.1f MB\n' "$runs" "$rss_mb" "$fp_mb"

    # The held run stops itself (SIGSTOP) after its last frame; vmmap reads it, SIGCONT lets it exit.
    # A stopped process keeps every signal but SIGKILL pending until it is continued. When this shell
    # died between the stop and the SIGCONT while its process group lived on (the caller's shell
    # still running, so the kernel's SIGHUP+SIGCONT to an orphaned group never came), the viewer
    # stayed stopped for good, holding the measure lock's fd with it. The EXIT trap SIGKILLs
    # it on any exit before it is reaped (failure, INT, TERM, HUP), and a watchdog that ignores
    # those signals does the same within 0.5 s if this shell is SIGKILLed.
    local vmmap="$dir/vmmap.txt" state="" t held_out=/dev/null held_env=() kept=""
    if ((hold)); then
        kept="$dir/hold/$(page_name "$page")"
        mkdir -p "$dir/hold"
        rm -f "$kept".*.txt
        held_out="$kept.stats.txt"
        ((msl)) && held_env=(MallocStackLogging=lite)
    fi
    env ${held_env[@]+"${held_env[@]}"} "${viewer[@]}" --hold ${kept:+--memory-stats} >"$held_out" 2>"$log" &
    held_pid=$!
    trap 'kill_held' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
    (
        trap '' INT TERM HUP
        while kill -0 "$held_pid" 2>/dev/null; do
            kill -0 "$$" 2>/dev/null || { kill -KILL "$held_pid" 2>/dev/null; break; }
            sleep 0.5
        done
    ) </dev/null >/dev/null 2>&1 &
    for ((t = 0; t < 1200; t++)); do
        state="$(ps -o stat= -p "$held_pid" 2>/dev/null || true)"
        [[ -z "$state" || "$state" == T* ]] && break
        sleep 0.1
    done
    if [[ "$state" != T* ]]; then
        echo "dev.sh mem: held run did not stop (state '${state:-exited}')" >&2
        cat "$log" >&2
        return 1
    fi
    vmmap --summary "$held_pid" >"$vmmap" 2>&1 || true
    if ((hold)); then
        vmmap -v -wide "$held_pid" >"$kept.vmmap.txt" 2>&1 || true
        footprint "$held_pid" >"$kept.footprint.txt" 2>&1 || true
        if ((msl)); then
            heap -s "$held_pid" >"$kept.heap.txt" 2>&1 || true
            malloc_history "$held_pid" -allBySize >"$kept.malloc_history.txt" 2>&1 || true
        fi
    fi
    kill -CONT "$held_pid"
    local held_ok=1
    wait "$held_pid" || held_ok=0
    held_pid=""
    ((held_ok)) || { echo "dev.sh mem: held run failed" >&2; cat "$log" >&2; return 1; }
    local surfaces surface_mb
    # Columns: VIRTUAL RESIDENT DIRTY SWAPPED VOLATILE NONVOL EMPTY REGION-COUNT; no line, no surface.
    read -r surfaces surface_mb < <(awk '
        function mb(v) { u = substr(v, length(v)); n = v + 0; return u == "G" ? n * 1024 : u == "M" ? n : u == "K" ? n / 1024 : n / 1048576 }
        $1 == "IOSurface" { count = $9; size = mb($2) }
        END { printf "%d %.1f\n", count, size }' "$vmmap")
    # The GPU driver's memory: "IOAccelerator" and "IOAccelerator (graphics)" rows, dirty + swapped columns. The
    # AGX driver allocates ~3.8 MB of it on the process's first render pass (docs/MEMORY.md).
    local ioaccel_mb
    ioaccel_mb="$(awk '
        function mb(v) { u = substr(v, length(v)); n = v + 0; return u == "G" ? n * 1024 : u == "M" ? n : u == "K" ? n / 1024 : n / 1048576 }
        $1 == "IOAccelerator" { i = ($2 == "(graphics)") ? 5 : 4; dirty += mb($i) + mb($(i + 1)) }
        END { printf "%.1f\n", dirty }' "$vmmap")"
    grep -q '^REGION TYPE' "$vmmap" || { echo "dev.sh mem: vmmap failed (see $vmmap)" >&2; surfaces="?"; surface_mb="?"; ioaccel_mb="?"; }
    echo "IOSurface       $surfaces regions, $surface_mb MB virtual (vmmap at the end of the run, $vmmap)"
    echo "IOAccelerator   $ioaccel_mb MB dirty+swapped (GPU driver memory, same vmmap)"
    local held_fields=""
    if ((hold)); then
        local zone_mb strikes
        zone_mb="$(sed -n 's/^karouka-memory .*malloc_zone_mb=\([0-9.]*\).*/\1/p' "$held_out")"
        strikes="$(sed -n 's/^karouka-memory-usage .*font_cache_strikes=\([0-9]*\).*/\1/p' "$held_out")"
        echo "malloc zone     ${zone_mb:-?} MB (--memory-stats at the hold$( ((msl)) && echo ', under MallocStackLogging=lite'))"
        echo "glyph cache     ${strikes:-?} strikes of 256 (font_cache_strikes, same run)"
        echo "held run        $(printf '%s ' "$kept".*.txt)"
        held_fields=" malloc_zone_mb=${zone_mb:-?} font_cache_strikes=${strikes:-?} msl=$msl"
    fi
    local line="karouka-mem page=$page frames=$frames views=$views runs=$runs rss_mb=$rss_mb footprint_mb=$fp_mb iosurface_regions=$surfaces iosurface_mb=$surface_mb ioaccel_mb=$ioaccel_mb$held_fields $info"
    echo "$line"
    [[ -z "${mem_lines:-}" ]] || echo "$line" >>"$mem_lines"
}

# A key=value field of a karouka-mem line, or ? when it has none.
mem_field() { if [[ " $1 " =~ \ $2=([^ ]*)\  ]]; then echo "${BASH_REMATCH[1]}"; else echo "?"; fi; }

# mem --all-demo [flags]: mem of every demo page (demo_pages, as mem --list prints them),
# one after another with the same flags, then a table of their medians. A page that fails is a
# FAILED row, and the rest still run; the exit status is 1 if any failed. Each page's own
# karouka-mem line is printed as it finishes. The table's last line is for scripts:
#   karouka-mem-all pages=N failed=N frames=N views=N runs=N
mem_all_demo() {
    local args=() arg pages=() page
    for arg in "$@"; do
        case "$arg" in
            --all-demo) ;;
            --attribute) echo "dev.sh mem: --all-demo doesn't take --attribute (one page at a time)" >&2; return 2 ;;
            -*) args+=("$arg") ;;
            *) # a flag's value (--frames N) is a number; anything else is a page
                [[ "$arg" =~ ^[0-9]+$ ]] || { echo "dev.sh mem: --all-demo takes no page ($arg)" >&2; return 2; }
                args+=("$arg") ;;
        esac
    done
    while IFS= read -r page; do pages+=("$page"); done < <(demo_pages)
    ((${#pages[@]})) || { echo "dev.sh mem: no demo pages under $KR_ROOT/pages/demo" >&2; return 1; }
    local lines="$KR_BUILD/mem/all-demo.txt" failed=() rc
    mkdir -p "$KR_BUILD/mem"
    : >"$lines"
    for page in "${pages[@]}"; do
        echo "== demo/$(page_name "$page")"
        # Its own shell, so a failing page (mem returns 1, or set -e) ends only its run; the EXIT trap
        # there kills its held viewer. set -e stays on inside it.
        set +e
        (set -e; mem_lines="$lines" mem "$page" ${args[@]+"${args[@]}"})
        rc=$?
        set -e
        ((rc == 0)) || { failed+=("$page"); echo "dev.sh mem: demo/$(page_name "$page") failed (exit $rc)" >&2; }
        case "$rc" in
            2) return 2 ;; # a bad flag fails every page the same way
            129|130|143) return "$rc" ;; # mem's HUP/INT/TERM traps: stop, don't go on to the next page
        esac
    done
    echo "== all demo pages (medians; $lines)"
    printf '%-20s %9s %13s %10s %12s\n' page "RSS MB" "footprint MB" IOSurfaces "IOAccel MB"
    local line="" last=""
    for page in "${pages[@]}"; do
        line="$(grep -F "karouka-mem page=$page " "$lines" | tail -n 1 || true)"
        if [[ -z "$line" ]]; then
            printf '%-20s %9s\n' "$(page_name "$page")" FAILED
            continue
        fi
        last="$line"
        printf '%-20s %9s %13s %10s %12s\n' "$(page_name "$page")" "$(mem_field "$line" rss_mb)" \
            "$(mem_field "$line" footprint_mb)" "$(mem_field "$line" iosurface_regions)" "$(mem_field "$line" ioaccel_mb)"
    done
    echo "karouka-mem-all pages=${#pages[@]} failed=${#failed[@]} frames=$(mem_field "$last" frames) views=$(mem_field "$last" views) runs=$(mem_field "$last" runs)"
    ((${#failed[@]} == 0))
}

# bench --save NAME: copies the build that just finished out of the shared build dir, which the
# next build from any checkout overwrites: karouka_viewer, libkarouka.dylib and every dylib they load
# through @rpath (the vcpkg ones, mimalloc among them, and Skia's), found as snapshot_build.py
# resolves them. The viewer keeps its rpath to the shared dir, so compare.py runs it with
# DYLD_LIBRARY_PATH=NAME/ and checks that libkarouka.dylib and every other dylib NAME holds came from NAME.
bench_save() {
    local name="${1:-}"
    [[ -n "$name" && "$name" != current && "$name" != */* ]] ||
        { echo "dev.sh bench --save: give a NAME (not 'current', no '/')" >&2; return 2; }
    local dir="$KR_BENCH_BUILDS/$name" snap="$KR_BUILD/snapshots/bench-save.$$" lib count
    # snapshot_build.py clones every dylib the build loads into snap/lib; the dirs are named
    # <something>.<pid> so from_snapshot removes one a killed save leaves.
    mkdir -p "$KR_BUILD/snapshots"
    rm -rf "$snap"
    if ! take_snapshot "$snap" "$snap.log"; then
        echo "dev.sh bench --save: snapshot of the build failed (see $snap.log)" >&2
        return 1
    fi
    rm -rf "$dir"
    mkdir -p "$dir"
    cp "$KR_BIN/karouka_viewer" "$KR_BUILD/lib/libkarouka.dylib" "$dir/"
    for lib in "$snap"/lib/*.dylib; do
        case "$(basename "$lib")" in
            libkarouka.dylib | libkarouka_miprof.dylib | libkarouka_ordertrace.dylib) ;;
            *) cp -c -P "$lib" "$dir/" 2>/dev/null || cp -P "$lib" "$dir/" ;;
        esac
    done
    count="$(ls "$dir"/*.dylib | wc -l | tr -d ' ')"
    rm -rf "$snap" "$snap.log"
    {
        echo "build    $(build_info)"
        echo "checkout $KR_ROOT"
        echo "saved    $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "dylib    $(stat -f %z "$dir/libkarouka.dylib") bytes"
        echo "dylibs   $count (libkarouka and the vcpkg and Skia dylibs it loads, e.g. $(cd "$dir" && ls libmimalloc*.dylib | head -n 1))"
    } >"$dir/build.txt"
    cat "$dir/build.txt"
    echo "dev.sh bench --save: $dir (compare with: tools/dev.sh bench --ab $name current)"
}

# package [DIR]: the shipped form of the build that just finished. The dSYM is made
# from the build's dylib, whose debug map names the object files it was linked from, so it must
# run before the next build replaces them (package holds the lock throughout).
package() {
    local dir="${1:-$KR_BUILD/package/$(basename "$KR_ROOT")}" built="$KR_BUILD/lib/libkarouka.dylib"
    local lib warnings exports_built exports_packed uuid_lib uuid_dsym log
    [[ "$dir" == /* ]] || dir="$PWD/$dir"
    lib="$dir/lib/libkarouka.dylib"
    # Replace an earlier package, never some other directory DIR happens to name.
    if [[ -e "$dir" && ! -f "$dir/build.txt" ]] && [[ -n "$(ls -A "$dir")" ]]; then
        echo "dev.sh package: $dir exists and isn't a package (no build.txt); give an empty or new DIR" >&2
        return 2
    fi
    rm -rf "$dir"
    mkdir -p "$dir/lib" "$dir/include"
    cp -R "$KR_ROOT/include/karouka" "$dir/include/"
    warnings="$(nice -n 10 dsymutil "$built" -o "$lib.dSYM" 2>&1)" || { echo "$warnings" >&2; return 1; }
    if [[ -n "$warnings" ]]; then
        echo "$warnings" >&2
        echo "dev.sh package: dsymutil warned (an object file the debug map names is gone?); the dSYM is incomplete" >&2
        return 1
    fi
    cp "$built" "$lib"
    strip -x "$lib" # re-signs the ad-hoc signature
    codesign --verify "$lib"
    uuid_lib="$(dwarfdump --uuid "$lib" | awk '{print $2}')"
    uuid_dsym="$(dwarfdump --uuid "$lib.dSYM" | awk '{print $2}')"
    [[ -n "$uuid_lib" && "$uuid_lib" == "$uuid_dsym" ]] ||
        { echo "dev.sh package: dylib UUID $uuid_lib, dSYM UUID $uuid_dsym" >&2; return 1; }
    exports_built="$(nm -gU "$built" | awk '{print $NF}' | sort)"
    exports_packed="$(nm -gU "$lib" | awk '{print $NF}' | sort)"
    [[ "$exports_built" == "$exports_packed" ]] ||
        { echo "dev.sh package: strip changed the exported symbols" >&2; return 1; }
    log="$dir/smoke.log"
    if ! DYLD_LIBRARY_PATH="$dir/lib" DYLD_PRINT_LIBRARIES=1 "$KR_BIN/karouka_viewer" "$(empty_page)" \
        --headless --frames 60 >"$log" 2>&1; then
        echo "dev.sh package: the viewer failed with the packaged dylib ($log)" >&2
        return 1
    fi
    grep -qF "$lib" "$log" || { echo "dev.sh package: the viewer didn't load $lib ($log)" >&2; return 1; }
    {
        echo "build    $(build_info)"
        echo "checkout $KR_ROOT"
        echo "uuid     $uuid_lib"
        echo "dylib    $(stat -f %z "$lib") bytes (unstripped $(stat -f %z "$built"))"
        echo "dSYM     $(du -sk "$lib.dSYM" | cut -f 1) KB"
    } >"$dir/build.txt"
    cat "$dir/build.txt"
    echo "dev.sh package: $dir"
}

# wheel [DIR]: the karouka wheel (tools/wheel.py), then its smoke test (wheel_smoke).
wheel() {
    local dir="${1:-$KR_BUILD/wheel/$(basename "$KR_ROOT")}" python whl
    [[ "$dir" == /* ]] || dir="$PWD/$dir"
    # Replace an earlier wheel dir, never some other directory DIR happens to name.
    if [[ -e "$dir" ]] && ls -A "$dir" | grep -qv -e '^stage$' -e '^smoke$' -e '^karouka-.*\.whl$'; then
        echo "dev.sh wheel: $dir holds more than an earlier wheel; give an empty or new DIR" >&2
        return 2
    fi
    python="$(cat "$KR_LIB/_karouka.python")"
    python3 "$KR_ROOT/tools/wheel.py" --build "$KR_BUILD" --resources "$KR_LADYBIRD/Base/res" --out "$dir" \
        --forbid "$KR_ROOT" --forbid "$KR_MAIN_ROOT" --forbid "$KR_LADYBIRD" || return
    whl="$(ls "$dir"/karouka-*.whl)"
    wheel_smoke "$whl" "$python" "$dir/smoke" || return
    echo "dev.sh wheel: $whl"
}

# Installs WHEEL into a fresh venv of PYTHON (outside the checkout) and runs python -m karouka
# from it with the checkout, the main checkout and the Ladybird tree (the build in it) unreadable
# (sandbox-exec), on a copy of pages/demo/demo_page.html (whose capture must match the build's
# module's, pixel for pixel: the packaged resources and fonts are the build's) and on a page whose
# text/python writes a file. Logs and captures in OUT.
#   wheel_smoke WHEEL PYTHON OUT
wheel_smoke() {
    local whl="$1" python="$2" out="$3" tmp rc=0 deny
    rm -rf "$out" && mkdir -p "$out"
    tmp="$(realpath "$(mktemp -d "${TMPDIR:-/tmp}/karouka-wheel.XXXXXX")")"
    mkdir -p "$tmp/pages/demo" "$tmp/app"
    cp "$KR_ROOT/pages/demo/demo_page.html" "$tmp/pages/demo/" && cp -R "$KR_ROOT/pages/fonts" "$tmp/pages/"
    cat >"$tmp/app/index.html" <<'HTML'
<!doctype html><html><head><title>wheel</title></head><body><p id="out"></p>
<script type="text/python">
import importlib.machinery, pathlib, sys
document.getElementById("out").textContent = f"{window.innerWidth}"
module = importlib.machinery.PathFinder.find_spec("_karouka").origin
pathlib.Path(document.URL.removeprefix("file://")).with_name("ran.txt").write_text(
    f"{document.getElementById('out').textContent} {module} {sys.prefix}\n")
</script></body></html>
HTML
    deny="(version 1)(allow default)(deny file-read* (subpath \"$KR_ROOT\") (subpath \"$KR_MAIN_ROOT\") (subpath \"$KR_LADYBIRD\"))"
    if ! "$python" -m venv "$tmp/venv" >"$out/venv.log" 2>&1 ||
        ! "$tmp/venv/bin/python" -m pip install --no-index --no-deps --disable-pip-version-check "$whl" >>"$out/venv.log" 2>&1; then
        echo "dev.sh wheel: pip install into a fresh venv failed ($out/venv.log)" >&2
        rc=1
    elif ! (cd "$tmp" && env -u KR_RESOURCE_ROOT -u PYTHONPATH -u PYTHONHOME \
            sandbox-exec -p "$deny" env DYLD_PRINT_LIBRARIES=1 "$tmp/venv/bin/python" -I -m karouka --software --headless --frames 60 \
            --capture "$tmp/demo.png" --size 800x600 "$tmp/pages/demo/demo_page.html") >"$out/demo.log" 2>&1 ||
        ! (cd "$tmp" && env -u KR_RESOURCE_ROOT -u PYTHONPATH -u PYTHONHOME \
            sandbox-exec -p "$deny" "$tmp/venv/bin/python" -I -m karouka --software --headless --frames 10 --size 800x600 \
            "$tmp/app/index.html") >"$out/app.log" 2>&1; then
        echo "dev.sh wheel: python -m karouka failed from the wheel's venv ($out/demo.log, $out/app.log)" >&2
        rc=1
    elif ! grep -q "^800 $tmp/venv/.*/_karouka.cpython-[0-9]*-darwin.so $tmp/venv\$" "$tmp/app/ran.txt" 2>/dev/null; then
        echo "dev.sh wheel: the page's text/python didn't run from the venv's module (ran.txt: $(cat "$tmp/app/ran.txt" 2>/dev/null))" >&2
        rc=1
    elif ! sed -n 's/^dyld\[[0-9]*\]: <[^>]*> //p' "$out/demo.log" >"$out/images.log" ||
        grep -e "^$KR_ROOT/" -e "^$KR_MAIN_ROOT/" -e "^$KR_LADYBIRD/" "$out/images.log" ||
        ! grep -q "^$tmp/venv/.*/karouka/.dylibs/libskia.dylib$" "$out/images.log"; then
        echo "dev.sh wheel: the demo run loaded an image from the build tree, or not the venv's dylibs ($out/images.log)" >&2
        rc=1
    elif ! (cd "$tmp" && env -u KR_RESOURCE_ROOT PYTHONPATH="$KR_LIB" "$python" -s -m karouka --software --headless \
            --frames 60 --capture "$out/demo.build.png" --size 800x600 "$tmp/pages/demo/demo_page.html") \
            >"$out/demo.build.log" 2>&1; then
        echo "dev.sh wheel: the build's module failed on the demo page ($out/demo.build.log)" >&2
        rc=1
    elif ! python3 "$KR_ROOT/tools/pngdiff.py" "$out/demo.build.png" "$tmp/demo.png" >"$out/pngdiff.log" 2>&1; then
        echo "dev.sh wheel: the wheel's demo capture differs from the build's ($out/pngdiff.log)" >&2
        rc=1
    fi
    cp "$tmp/demo.png" "$out/" 2>/dev/null || true
    cp "$tmp/app/ran.txt" "$out/" 2>/dev/null || true
    rm -rf "$tmp"
    ((rc == 0)) && echo "wheel smoke: ok (venv install, demo page = build's pixels, text/python ran; $out)"
    return "$rc"
}

# The empty page as mem writes it, then the given pages (default: demo_pages, pages/demo/*.html and
# pages/demo/*/index.html), then with --tests every pages/tests page with a
# karouka-check-input, from the snapshot (from_snapshot). --input, --fresh and the --stats
# flags go to orderfile.py. The build_info line, the snapshot's build (KR_BUILD_INFO), is printed and
# written into the order file's header.
orderfile() {
    local args=() pages=() info page tests=0
    while (($#)); do
        case "$1" in
            --stats|--data|--unplaced|--fresh) args+=("$1"); shift ;;
            --input) (($# >= 2)) || { echo "dev.sh orderfile: --input needs FLAGS" >&2; return 2; }
                args+=("--input=$2"); shift 2 ;;
            --input=*) args+=("$1"); shift ;;
            --tests) tests=1; shift ;;
            -*) echo "dev.sh orderfile: unknown flag $1" >&2; return 2 ;;
            *) pages+=("$(resolve_page "$1")"); shift ;;
        esac
    done
    if ! ((${#pages[@]})); then
        while IFS= read -r page; do pages+=("$page"); done < <(demo_pages)
    fi
    if ((tests)); then
        for page in "$KR_ROOT"/pages/tests/*.html; do
            [[ -n "$(check_input "$page")" ]] && pages+=("$page")
        done
    fi
    info="${KR_BUILD_INFO:-$(build_info)}"
    echo "karouka-build $info"
    python3 "$KR_ROOT/tools/orderfile.py" --viewer "$KR_BIN/karouka_viewer" \
        --tracer "$KR_LIB/libkarouka_ordertrace.dylib" --map "$KR_MAP" \
        --empty "$(empty_page)" --out "$KR_ROOT/src/libkarouka.order" --build-info "$info" \
        ${args[@]+"${args[@]}"} "${pages[@]}"
}

cmd="${1:-build}"
shift || true
case "$cmd" in
    bootstrap) exec "$KR_ROOT/tools/bootstrap.sh" ;;
    ladybird) locked _ladybird ;;
    build) locked _build ;;
    # The build lock only for the build and its snapshot; this checkout's own check lock
    # throughout, so a second check here can't remove the snapshot the first is rendering from.
    # run_forwarding passes INT, TERM and HUP on to every process under it, the renders included.
    check) reap_stopped_viewers
        fwd_hold="$(check_dir_path).building"
        run_forwarding "$0" _check_locked ;;
    _check_locked) with_lock_at "$(check_dir_path).lock" "this checkout's other check" "$0" _check_all ;;
    _check_all) KR_LOCK_REPORT="build lock" locked _check_build && check ;;
    # run, bench and mem: the build lock only for the build and its snapshot (from_snapshot).
    # bench --save only copies the build, under the build lock.
    run) from_snapshot run "$@" ;;
    python) from_snapshot python "$@" ;;
    bench) if [[ "${1:-}" == --save ]]; then locked _bench_save "${2:-}"; else from_snapshot bench "$@"; fi ;;
    # wpt, orderfile and startup too; startup measures holding the measure lock, as bench
    # and mem do. package holds the build lock throughout: dsymutil reads the build's object files.
    wpt) from_snapshot wpt "$@" ;;
    # census as wpt: counts, not timings, so no measure lock.
    census) from_snapshot census "$@" ;;
    # libweb as wpt. --compare reads two results files and --list the test tree, so neither builds;
    # --list rewrites this checkout's copy of the tests, so it takes libweb's lock (_libweb).
    libweb) for arg in "$@"; do
            case "$arg" in
                --compare) exec python3 "$KR_ROOT/tools/libweb_tests.py" --saved-dir "$KR_BUILD/libweb/saved" "$@" ;;
                --list) with_lock_at "$KR_BUILD/libweb/$(basename "$KR_ROOT").lock" "this checkout's other libweb" \
                        python3 "$KR_ROOT/tools/libweb_tests.py" --out "$KR_BUILD/libweb/$(basename "$KR_ROOT")" "$@"
                    exit ;;
            esac
        done
        # Bad flags or a --save NAME already saved fail here, before the build.
        python3 "$KR_ROOT/tools/libweb_tests.py" --preflight --saved-dir "$KR_BUILD/libweb/saved" "$@" || exit
        from_snapshot libweb "$@" ;;
    package) locked _package "$@" ;;
    wheel) locked _wheel "$@" ;;
    startup) from_snapshot startup ;;
    # --list prints the demo pages they take by name (orderfile's default set), without building.
    mem|orderfile) if [[ "${1:-}" == --list ]]; then list_demo_pages; exit 0; fi
        if [[ "$cmd" == mem ]]; then mem_check_args "$@"; reap_stopped_viewers; fi
        from_snapshot "$cmd" "$@" ;;
    patches) locked _patches "$@" ;;
    own) with_lock "$0" _own "$@" ;;
    release) with_lock "$0" _release "$@" ;;
    # The same steps without taking the lock; with_lock runs these.
    _patches) exec "$KR_ROOT/tools/apply_patches.sh" "$@" ;;
    _own) own "$@" ;;
    _release) release "$@" ;;
    _ladybird) ladybird ;;
    _build) build ;;
    # Holds the signals run_forwarding would pass on (fwd_hold) while it builds.
    _check_build) hold="$(check_dir_path).building"
        echo $$ >"$hold"
        rc=0
        check_build || rc=$?
        rm -f "$hold"
        exit "$rc" ;;
    # check's startup gate, under the measure lock; $1 is check's output directory.
    _check_startup) use_snapshot "$1/build" && startup_check "$1" ;;
    # Under the build lock (from_snapshot): build, snapshot into DIR, and what the build was.
    _snapshot) "$0" _build || exit
        take_snapshot "$1" "$1.log" || { echo "dev.sh: snapshot of the build failed (see $1.log)" >&2; exit 1; }
        build_info >"$1/build_info" ;;
    # Build as its own process, as _build: configure cds into the Ladybird tree (relative paths in "$@"
    # are the caller's), and set -e doesn't apply to a function called on the left of &&.
    # From the snapshot in $KR_SNAP, without the build lock (from_snapshot): run, wpt and orderfile.
    # Each page keeps its own shader cache file under this checkout's run/ directory (the
    # viewer's KR_SHADER_CACHE_DIR, as check does), not the machine-wide skia-shaders.bin
    # whatever page ran last left there: a page's first run builds its programs and later runs read
    # them, the same count every time. A KR_SHADER_CACHE_DIR or --shader-cache of the caller's wins.
    _run) use_snapshot "$KR_SNAP" &&
        export KR_SHADER_CACHE_DIR="${KR_SHADER_CACHE_DIR:-$KR_BUILD/run/$(basename "$KR_ROOT")/shader-cache}" &&
        mkdir -p "$KR_SHADER_CACHE_DIR" && exec "$KR_BIN/karouka_viewer" "$@" ;;
    _bench)
        use_snapshot "$KR_SNAP"
        echo "build    $KR_BUILD_INFO" >"$KR_SNAP/build.txt"
        KAROUKA_VIEWER="$KR_BIN/karouka_viewer" KAROUKA_BENCH_BUILDS="$KR_BENCH_BUILDS" KAROUKA_BENCH_LIB="$KR_LIB" \
            KAROUKA_CURRENT_BUILD_INFO="$KR_SNAP/build.txt" exec python3 "$KR_ROOT/bench/compare.py" "$@" ;;
    _bench_save) "$0" _build && bench_save "$@" ;;
    _mem) use_snapshot "$KR_SNAP" && mem "$@" ;;
    # bench, mem or startup from the snapshot, holding the measure lock (from_snapshot).
    _measured) with_lock_at "$KR_MEASURE_LOCK" "the measure lock (another checkout's bench, mem or startup is running)" \
            "$0" "_$1" "${@:2}" ;;
    # wpt's own lock for this checkout's output directory: two wpt runs here take turns.
    _wpt) with_lock_at "$KR_BUILD/wpt/$(basename "$KR_ROOT").lock" "this checkout's other wpt" "$0" _wpt_run "$@" ;;
    # The wpt run's viewers cache shaders per page in the run's own output directory.
    _wpt_run) use_snapshot "$KR_SNAP" &&
        export KR_SHADER_CACHE_DIR="${KR_SHADER_CACHE_DIR:-$KR_BUILD/wpt/$(basename "$KR_ROOT")/shader-cache}" &&
        mkdir -p "$KR_SHADER_CACHE_DIR" &&
        exec nice -n 10 python3 "$KR_ROOT/tools/wpt.py" --viewer "$KR_BIN/karouka_viewer" --out "$KR_BUILD/wpt/$(basename "$KR_ROOT")" \
            --prune-checkouts "$@" ;;
    # libweb's own lock for this checkout's output directory, as wpt's: libweb_tests.py replaces its copy of the tests.
    _libweb) with_lock_at "$KR_BUILD/libweb/$(basename "$KR_ROOT").lock" "this checkout's other libweb" "$0" _libweb_run "$@" ;;
    _libweb_run) use_snapshot "$KR_SNAP" &&
        export KR_SHADER_CACHE_DIR="${KR_SHADER_CACHE_DIR:-$KR_BUILD/libweb/$(basename "$KR_ROOT")/shader-cache}" &&
        mkdir -p "$KR_SHADER_CACHE_DIR" &&
        exec nice -n 10 python3 "$KR_ROOT/tools/libweb_tests.py" --viewer "$KR_BIN/karouka_viewer" \
            --out "$KR_BUILD/libweb/$(basename "$KR_ROOT")" --saved-dir "$KR_BUILD/libweb/saved" "$@" ;;
    _orderfile) use_snapshot "$KR_SNAP" && orderfile "$@" ;;
    _python) use_snapshot "$KR_SNAP" && python_tests "$@" ;;
    # census's own lock for this checkout's output directory, as wpt's; each page its own shader cache.
    _census) with_lock_at "$KR_BUILD/census/$(basename "$KR_ROOT").lock" "this checkout's other census" "$0" _census_run "$@" ;;
    _census_run) use_snapshot "$KR_SNAP" &&
        exec nice -n 10 python3 "$KR_ROOT/tools/census.py" --viewer "$KR_BIN/karouka_viewer" \
            --out "$KR_BUILD/census/$(basename "$KR_ROOT")" --prune-checkouts --jobs "${KR_CHECK_JOBS:-3}" \
            --commands-header "$KR_LADYBIRD/Libraries/LibCompositing/DisplayList/DisplayListCommand.h" "$@" ;;
    _startup) use_snapshot "$KR_SNAP" && startup_check "$KR_BUILD/startup/$(basename "$KR_ROOT")" ;;
    _package) "$0" _build && package "$@" ;;
    _wheel) "$0" _build && wheel "$@" ;;
    *) echo "unknown command: $cmd" >&2; exit 2 ;;
esac
