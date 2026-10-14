#!/usr/bin/env bash
# Builds the engines perfcmp.py compares into the work dir (default bench/engines/.work, or
# $KR_ENGINES_WORK). Nothing is installed system-wide and nothing goes on PATH.
#
#   bench/engines/setup.sh                    # every engine
#   bench/engines/setup.sh karouka tauri      # just these
#
#   karouka   tools/dev.sh build, then a snapshot of the build (tools/snapshot_build.py) in
#             WORK/karouka-snap, so another checkout's build can't change it mid-run
#   ladybird  only checks that the release build is there (LADYBIRD_BIN, default ~/ladybird's)
#   electron  npm install electron@$ELECTRON_VERSION into WORK/electron
#   tauri     cargo build --release from apps/tauri (Cargo.lock pinned to crates that build on
#             Homebrew's rustc 1.89) into WORK/tauri-target, at $KR_JOBS jobs
#   tinyjs    the $TINYJS_VERSION release tarball, checked against its checksums.txt, unpacked
#             into WORK/tinyjs-home; then apps/tinyjs + page/bench.html built in WORK/tinyjs
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WORK="${KR_ENGINES_WORK:-$HERE/.work}"
JOBS="${KR_JOBS:-4}"
ELECTRON_VERSION="${ELECTRON_VERSION:-41.10.7}"
TINYJS_VERSION="${TINYJS_VERSION:-v0.50.1}"
LADYBIRD_BIN="${LADYBIRD_BIN:-$HOME/ladybird/Build/release/bin/Ladybird.app/Contents/MacOS/Ladybird}"
mkdir -p "$WORK"

karouka() {
    "$ROOT/tools/dev.sh" build
    # The build dir paths, as dev.sh sees them (a worktree shares the main checkout's build).
    local build res
    build="$(source "$ROOT/tools/env.sh" && echo "$KR_BUILD")"
    res="$(source "$ROOT/tools/env.sh" && echo "$KR_LADYBIRD/Base/res")"
    rm -rf "$WORK/karouka-snap"
    python3 "$ROOT/tools/snapshot_build.py" --build "$build" --resources "$res" --out "$WORK/karouka-snap"
    git -C "$ROOT" rev-parse --short HEAD >"$WORK/karouka-snap/commit"
}

ladybird() {
    if [[ ! -x "$LADYBIRD_BIN" ]]; then
        echo "setup.sh: no Ladybird at $LADYBIRD_BIN (set LADYBIRD_BIN, and pass perfcmp.py --ladybird)" >&2
        return 1
    fi
    echo "ladybird: $LADYBIRD_BIN"
}

electron() {
    mkdir -p "$WORK/electron"
    cp "$HERE/apps/electron/package.json" "$HERE/apps/electron/main.js" "$WORK/electron/"
    (cd "$WORK/electron" && npm install --no-audit --no-fund "electron@$ELECTRON_VERSION")
}

tauri() {
    nice -n 10 cargo build --release --locked -j "$JOBS" \
        --manifest-path "$HERE/apps/tauri/Cargo.toml" --target-dir "$WORK/tauri-target"
}

tinyjs() {
    local dl="$WORK/dl/tinyjs-$TINYJS_VERSION" asset="tinyjs-macos-$(uname -m | sed 's/aarch64/arm64/').tar.gz"
    local url="https://github.com/tarwin/tinyjsapp/releases/download/$TINYJS_VERSION"
    mkdir -p "$dl"
    curl -fsSL -o "$dl/$asset" "$url/$asset"
    curl -fsSL -o "$dl/checksums.txt" "$url/checksums.txt"
    (cd "$dl" && grep " $asset\$" checksums.txt | shasum -a 256 -c -)
    rm -rf "$WORK/tinyjs-home" "$WORK/tinyjs"
    mkdir -p "$WORK/tinyjs-home"
    tar -xzf "$dl/$asset" -C "$WORK/tinyjs-home" --strip-components 1
    cp -R "$HERE/apps/tinyjs" "$WORK/tinyjs"
    mkdir -p "$WORK/tinyjs/src/frontend"
    cp "$HERE/page/bench.html" "$WORK/tinyjs/src/frontend/index.html"
    cp "$WORK/tinyjs-home/template/icon.png" "$WORK/tinyjs/"
    (cd "$WORK/tinyjs" && "$WORK/tinyjs-home/tinyjs" build)
}

steps=("$@")
((${#steps[@]})) || steps=(karouka ladybird electron tauri tinyjs)
for step in "${steps[@]}"; do
    case "$step" in
        karouka | ladybird | electron | tauri | tinyjs) echo "== $step" && "$step" ;;
        *) echo "setup.sh: unknown engine $step" >&2 && exit 2 ;;
    esac
done
echo "setup.sh: done; run python3 -I $HERE/perfcmp.py"
