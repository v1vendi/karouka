#!/usr/bin/env bash
# Installs the pinned build toolchain into .toolchain/ (gitignored):
#   - CMake >= 3.30 (Ladybird's vcpkg needs it; Homebrew may be older)
#   - the Rust version pinned by third_party/ladybird/rust-toolchain.toml
#   - sccache, Ladybird's rustc wrapper for its Rust crates (local disk cache only)
set -euo pipefail
source "$(dirname "$0")/env.sh"

for pkg in autoconf autoconf-archive automake ccache libtool nasm ninja pkgconf llvm; do
    brew list --versions "$pkg" >/dev/null || { echo "missing Homebrew package: $pkg (brew install $pkg)"; exit 1; }
done

mkdir -p "$KR_TOOLCHAIN"
if [[ ! -x "$KR_TOOLCHAIN/cmake-venv/bin/cmake" ]]; then
    python3 -m venv "$KR_TOOLCHAIN/cmake-venv"
    "$KR_TOOLCHAIN/cmake-venv/bin/pip" -q install 'cmake>=3.30,<4'
fi

if [[ ! -x "$KR_RUST_BIN/rustc" ]]; then
    curl --proto '=https' --tlsv1.2 -sSf --retry 5 https://sh.rustup.rs -o "$KR_TOOLCHAIN/rustup-init.sh"
    sh "$KR_TOOLCHAIN/rustup-init.sh" -y -q --no-modify-path --profile minimal \
        --default-toolchain "$KR_RUST_VERSION" -c rustfmt -c clippy
fi

if [[ ! -x "$KR_SCCACHE_BIN/sccache" ]]; then
    # --no-default-features: no S3/redis/GHA backends and no OpenSSL, only the local disk cache.
    CARGO_TARGET_DIR="$(mktemp -d)" nice -n 10 cargo install sccache --version "$KR_SCCACHE_VERSION" --locked \
        --no-default-features --root "$KR_TOOLCHAIN/sccache" -j "$KR_JOBS"
fi

cmake --version | head -1
rustc --version
"$KR_SCCACHE_BIN/sccache" --version
