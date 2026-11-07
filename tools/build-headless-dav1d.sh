#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# VideoLAN dav1d 1.5.3 -- PS5 cross-compiled, pure C static software AV1 decoder.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
scratch=$(cat "$root/.local/headless-cache")
[[ "$(cat "$scratch/owner")" == "$root" ]]
export PS5_PAYLOAD_SDK="$scratch/sdk"
source="$root/.deps/dav1d-src"
[[ -f "$source/meson.build" ]] || { echo 'dav1d source missing; run make deps' >&2; exit 1; }
mkdir -p "$scratch/dav1d-native"
cat > "$scratch/dav1d-native/ps5-cross.ini" <<EOF
[binaries]
c = ['bash', '$root/tools/ffmpeg-ps5-cc.sh']
ar = 'llvm-ar-18'
strip = 'llvm-strip-18'
pkg-config = 'pkg-config'
[host_machine]
system = 'freebsd'
cpu_family = 'x86_64'
cpu = 'x86_64'
endian = 'little'
[properties]
needs_exe_wrapper = true
EOF
build="$scratch/dav1d-native/build"
prefix="$scratch/dav1d-native/install"
if [[ ! -f "$build/build.ninja" ]]; then
    meson setup "$build" "$source" --cross-file "$scratch/dav1d-native/ps5-cross.ini" \
        --prefix="$prefix" --libdir=lib --buildtype=release --default-library=static \
        -Denable_asm=false -Denable_tools=false -Denable_tests=false -Denable_examples=false \
        -Denable_docs=false -Db_lto=false -Db_pie=false
fi
meson compile -C "$build" -j "${EDEN_BUILD_JOBS:-$(nproc)}"
meson install -C "$build"
[[ -s "$prefix/lib/libdav1d.a" && -f "$prefix/include/dav1d/dav1d.h" ]] || {
    echo 'dav1d PS5 static build incomplete' >&2; exit 1;
}
llvm-nm-18 "$prefix/lib/libdav1d.a" | grep 'dav1d_send_data' >/dev/null || {
    echo 'dav1d static archive missing dav1d_send_data' >&2; exit 1;
}
