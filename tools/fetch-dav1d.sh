#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Separate from tools/deps.json to preserve the expensive RADV cache across AV1 updates.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
pin=b546257f770768b2c88258c533da38b91a06f737
src="$root/.deps/dav1d-src"
if [[ -f "$src/meson.build" ]] && [[ $(git -C "$src" rev-parse HEAD) == "$pin" ]]; then exit 0; fi
[[ ! -e "$src" ]] || { echo 'Unexpected dav1d checkout; refusing to overwrite' >&2; exit 1; }
mkdir -p "$root/.deps"
tmp="$src.fetch.$$"
trap 'rm -rf "$tmp"' EXIT
git init -q "$tmp"
git -C "$tmp" remote add origin https://github.com/videolan/dav1d.git
git -C "$tmp" fetch -q --depth=1 origin refs/tags/1.5.3
git -C "$tmp" -c advice.detachedHead=false checkout -q --detach FETCH_HEAD
[[ $(git -C "$tmp" rev-parse HEAD) == "$pin" ]] || { echo 'dav1d commit mismatch' >&2; exit 1; }
mv "$tmp" "$src"
