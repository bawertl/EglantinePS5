#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Static guard for NUP integration: does not replace a compiler or console test."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
read = lambda name: (ROOT / name).read_text()
expected = {
    "headless/settings_store.h": ('extension == ".nup"',),
    "headless/eglantineps5/eden_services.cpp": ('format != "NUP"', '".nup"'),
    "headless/metadata_bridge.cpp": ('#include "core/loader/nup.h"', 'Loader::AppLoader_NUP loader(file);',
                                     'loader.ReadIcon(icon)', 'loader.ReadProgramId(program_id)',
                                     'loader.ReadControlData(control)'),
    "headless/main.cpp": ('extension != ".nup"',),
    "tools/generate-nup-backport.py": ('31b901b93b992580d608fc2f4db9ddac1d755e43',
                                       '3140648a668aaebf87bae2dea17512fdca125ba0',
                                       '0018-add-native-nup-support.patch'),
}
for file, anchors in expected.items():
    source = read(file)
    for anchor in anchors:
        if anchor not in source:
            sys.exit(f"NUP static check: MISSING {anchor!r} in {file}")

# When the actual git submodule is present, additionally check that the generated
# code was applied and the pinned base stayed intact.
core = ROOT / "Eglantine/src/core"
if core.is_dir() and (core / "loader/nup.cpp").exists():
    for file, tokens in {
        "loader/nup.cpp": ("AppLoader_NUP::AppLoader_NUP", "ReadRomFS", "secondary_loader"),
        "file_sys/nup_container.cpp": ('SuperblockSize = 0x80', 'TocMagic = 0x01434F54', 'ZSTD_decompress'),
        "loader/loader.cpp": ('FileType::NUP', 'AppLoader_NUP'),
        "loader/loader.h": ('ErrorNUPBadFormat', 'ErrorNUPNoBasePackage'),
    }.items():
        contents = (core / file).read_text()
        for token in tokens:
            if token not in contents:
                sys.exit(f"NUP generated source check: MISSING {token!r} in Eglantine/src/core/{file}")
print("NUP bridge/static anchors OK (not a toolchain or gameplay validation)")
