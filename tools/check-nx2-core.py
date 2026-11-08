#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the submodule core's shader, readback and mapping regression tests on the host."""
from pathlib import Path
import json
import os
import subprocess

root = Path(__file__).resolve().parents[1]
cache = Path((root / '.local/headless-cache').read_text().strip())
build = root / '.local/nx2-core-check'
command = ['cmake', '-S', str(root / 'headless/nx2-core-check'), '-B', str(build),
           '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', '-DEDEN_SOURCE=' + str(root / 'Eglantine'),
           '-DFMT_INCLUDE=' + str(cache / 'source/.cache/cpm/fmt/12.1.0/include'),
           '-DDEPENDENCY_SOURCE=' + str(cache / 'source')]
# Catch2 used to be downloaded late in the release build by CMake FetchContent.
# A transient GitHub archive HTTP 504 made the entire build fail after compilation.
# `make deps` now fetches the exact pinned Catch2 Git commit before the build;
# use that checkout instead of making a second archive request in FetchContent.
# A caller-provided source remains possible for development builds.
if override := os.environ.get('EDEN_CATCH2_SOURCE'):
    catch2_source = Path(override).resolve()
else:
    manifest = json.loads((root / 'tools/deps.json').read_text())
    catch2_pin = next(item for item in manifest['items'] if item['name'] == 'catch2')
    eden_cpm = json.loads((root / 'Eglantine/cpmfile.json').read_text())
    if eden_cpm['catch2']['version'] != catch2_pin['version']:
        raise RuntimeError('Catch2 pin differs from Eglantine/cpmfile.json: refusing mismatched test dependency')
    catch2_source = (root / catch2_pin['path']).resolve()
    if not (catch2_source / 'CMakeLists.txt').is_file():
        raise RuntimeError(f'Pinned Catch2 is missing at {catch2_source}; run make deps first')
    pinned_head = subprocess.check_output(['git', '-C', str(catch2_source),
                                           'rev-parse', 'HEAD'], text=True).strip()
    if pinned_head != catch2_pin['commit']:
        raise RuntimeError(f'Catch2 checkout is not pinned: {pinned_head} != {catch2_pin["commit"]}')
command.append('-DFETCHCONTENT_SOURCE_DIR_CATCH2=' + str(catch2_source))
subprocess.run(command, check=True)
subprocess.run(['cmake', '--build', str(build), '--parallel', '4'], check=True)
subprocess.run([str(build / 'nx2-core-check')], check=True, timeout=120)
