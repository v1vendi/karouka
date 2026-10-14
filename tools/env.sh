# Sourced by tools/*.sh. Pins the toolchain karouka builds with (in .toolchain/), without touching
# the system (Homebrew) cmake/rust.
KR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# A git worktree of this repository has no Ladybird submodule and no toolchain of its own: it shares
# the main checkout's. The one Ladybird build dir builds the src/
# of whichever checkout last ran tools/dev.sh, which is why dev.sh serializes builds on KR_LOCK.
KR_MAIN_ROOT="$(cd "$KR_ROOT" && common="$(git rev-parse --git-common-dir 2>/dev/null)" && cd "$common/.." && pwd || echo "$KR_ROOT")"
KR_TOOLCHAIN="$KR_MAIN_ROOT/.toolchain"
KR_LADYBIRD="${KR_LADYBIRD:-$KR_MAIN_ROOT/third_party/ladybird}"
KR_LADYBIRD_BUILD="$KR_LADYBIRD/Build/release"
KR_LOCK="$KR_LADYBIRD/Build/karouka.lock"
KR_BUILD="$KR_LADYBIRD_BUILD/karouka"
KR_BIN="$KR_BUILD/bin"
# The build compiles karouka through this symlink to the building checkout, never through the
# checkout's own path, so every checkout's compile commands are identical and ccache hits on code
# another checkout already built (dev.sh configure retargets it).
KR_SRC_LINK="$KR_LADYBIRD_BUILD/karouka-src"

# ccache, for karouka's builds only (~/Library/Preferences/ccache/ccache.conf is shared with other
# projects): a file written seconds ago, or a __DATE__/__TIME__ user, can still hit or be
# stored. No CCACHE_BASEDIR: there is one build dir, so paths already match across checkouts, and
# relative paths would only change every cache key and make compiler errors print ../../ paths.
export CCACHE_SLOPPINESS="include_file_mtime,include_file_ctime,time_macros,pch_defines"

# Parallel jobs for every build step (override with KR_JOBS).
KR_JOBS="${KR_JOBS:-4}"
export CARGO_BUILD_JOBS="$KR_JOBS"
export VCPKG_MAX_CONCURRENCY="$KR_JOBS"

KR_RUST_VERSION="$(sed -n 's/^channel *= *"\(.*\)"/\1/p' "$KR_LADYBIRD/rust-toolchain.toml")"
export RUSTUP_HOME="$KR_TOOLCHAIN/rustup"
export CARGO_HOME="$KR_TOOLCHAIN/cargo"
KR_RUST_BIN="$RUSTUP_HOME/toolchains/$KR_RUST_VERSION-aarch64-apple-darwin/bin"

# sccache, installed by bootstrap. Ladybird's rust_crate.cmake finds it on PATH and passes
# it to cargo as RUSTC_WRAPPER; the cache lives in Build/caches/sccache, beside the vcpkg binary cache.
KR_SCCACHE_VERSION=0.18.0
KR_SCCACHE_BIN="$KR_TOOLCHAIN/sccache/bin"
export SCCACHE_DIR="$KR_LADYBIRD/Build/caches/sccache"
export SCCACHE_CACHE_SIZE="${SCCACHE_CACHE_SIZE:-4G}"

export PATH="$KR_RUST_BIN:$KR_SCCACHE_BIN:$KR_TOOLCHAIN/cmake-venv/bin:$PATH"
export CC="${CC:-/opt/homebrew/opt/llvm/bin/clang}"
export CXX="${CXX:-/opt/homebrew/opt/llvm/bin/clang++}"
export LADYBIRD_SOURCE_DIR="$KR_LADYBIRD"

# Ownership of the shared Ladybird tree. A checkout that edits third_party/ladybird and regenerates
# patches/ladybird/ runs `tools/dev.sh own` before its first edit and `tools/dev.sh release` when its
# patches are saved. While the marker names another checkout,
# apply_patches.sh leaves the tree alone, so other checkouts' builds build against the owner's tree
# (its series plus its unsaved edits) instead of resetting it to theirs. The owner's own builds
# keep its unsaved edits too (KR_APPLIED_FILE below). A strict checkout (KR_SERIES_STRICT=1), whose
# `dev.sh check` must verify its own series, can't build against someone else's tree: apply_patches.sh
# exits KR_OWNED_EXIT and dev.sh waits (without the build lock, so the owner can keep building) for the
# owner to release.
KR_OWNER_FILE="$KR_LADYBIRD/Build/karouka.tree-owner"
KR_OWNED_EXIT=75
# What each waiting dev.sh process waits for (a lock, or the tree owner), one record per process,
# removed when the wait ends.
KR_WAITS_DIR="$KR_LADYBIRD/Build/karouka.waits"
KR_SERIES_STRICT="${KR_SERIES_STRICT:-0}"

# Prints the checkout that owns the Ladybird tree, or nothing. A marker naming a checkout that no
# longer exists (a removed worktree) is stale and is removed.
kr_tree_owner() {
    [[ -f "$KR_OWNER_FILE" ]] || return 0
    local owner
    owner="$(sed -n 's/^root=//p' "$KR_OWNER_FILE")"
    if [[ -z "$owner" || ! -d "$owner" ]]; then
        echo "ladybird tree: owner ${owner:-?} no longer exists; dropping its stale marker" >&2
        rm -f "$KR_OWNER_FILE"
        return 0
    fi
    echo "$owner"
}

# The tree apply_patches.sh last wrote (a git tree id in the Ladybird repo), so it can tell the
# owner's hand edits (files that differ from it) from series changes (files that still match it).
KR_APPLIED_FILE="$KR_LADYBIRD/Build/karouka.tree-applied"

# Prints the last applied tree id, or nothing if there is no record or its tree is gone.
kr_applied_tree() {
    [[ -f "$KR_APPLIED_FILE" ]] || return 0
    local tree
    tree="$(sed -n 's/^tree=//p' "$KR_APPLIED_FILE")"
    if [[ -n "$tree" ]] && git -C "$KR_LADYBIRD" cat-file -e "$tree^{tree}" 2>/dev/null; then
        echo "$tree"
    fi
}

kr_record_applied() {
    mkdir -p "$(dirname "$KR_APPLIED_FILE")"
    printf 'tree=%s\nroot=%s\nat=%s\n' "$1" "$KR_ROOT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$KR_APPLIED_FILE"
}
