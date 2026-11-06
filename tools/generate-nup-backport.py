#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate the PS5 NUP core backport from the *real* upstream source commit.

The Eglantine gitlink is fixed to 3140648a...; this does NOT update it.  The four
new source files come from the pinned NUP introduction commit. V1.000.003
additionally adapts only nup_container.cpp to handle both validated record
layouts; existing loader, system and CMake registrations are retained.
The generated 0018 patch participates in the ordinary 0001..0018 apply/revert
sequence.  Run this after `git submodule update --init` and before apply patches.

No source is downloaded from an unpinned branch.  The commit may be fetched from
its own git remote, but never checked out and never made the submodule's HEAD.
"""
from __future__ import annotations
from nup_v1000003_layout import modify_nup_container
import argparse
import difflib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE = ROOT / "Eglantine"
PATCH = ROOT / "tools/eglantine-patches/0018-add-native-nup-support.patch"
BASE = "3140648a668aaebf87bae2dea17512fdca125ba0"
SOURCE = "31b901b93b992580d608fc2f4db9ddac1d755e43"
NEW_FILES = (
    "src/core/file_sys/nup_container.cpp",
    "src/core/file_sys/nup_container.h",
    "src/core/loader/nup.cpp",
    "src/core/loader/nup.h",
)

class BackportError(RuntimeError):
    pass


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(CORE), *args],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def git_bytes(ref: str, path: str) -> bytes:
    try:
        return git("show", f"{ref}:{path}").stdout
    except subprocess.CalledProcessError as exc:
        raise BackportError(f"Unable to read {path} at {ref[:12]}: {exc.stderr.decode(errors='replace')}") from exc


def replace_once(source: str, old: str, new: str, path: str) -> str:
    count = source.count(old)
    if count != 1:
        raise BackportError(f"Expected one anchor in {path}, found {count}: {old[:110]!r}")
    return source.replace(old, new, 1)


def replace(path: str, text: str) -> str:
    original = text
    def do(old: str, new: str) -> None:
        nonlocal text
        text = replace_once(text, old, new, path)

    if path == "src/core/CMakeLists.txt":
        do("    file_sys/registered_cache.h\n", "    file_sys/registered_cache.h\n    file_sys/nup_container.cpp\n    file_sys/nup_container.h\n")
        do("    loader/nsp.h\n", "    loader/nsp.h\n    loader/nup.cpp\n    loader/nup.h\n")
    elif path == "src/core/loader/loader.h":
        do("    KIP,\n    DeconstructedRomDirectory,", "    KIP,\n    NUP,\n    DeconstructedRomDirectory,")
        do("    ErrorIntegrityVerificationFailed,\n};", "    ErrorIntegrityVerificationFailed,\n    ErrorNUPBadFormat,\n    ErrorNUPNoBasePackage,\n};")
    elif path == "src/core/loader/loader.cpp":
        do('#include "core/loader/nsp.h"\n', '#include "core/loader/nsp.h"\n#include "core/loader/nup.h"\n')
        do('    } else if (const auto xci_type = IdentifyFileLoader<AppLoader_XCI>(file)) {\n        return *xci_type;\n',
           '    } else if (const auto xci_type = IdentifyFileLoader<AppLoader_XCI>(file)) {\n        return *xci_type;\n'
           '    } else if (const auto nup_type = IdentifyFileLoader<AppLoader_NUP>(file)) {\n        return *nup_type;\n')
        do('    return type == FileType::NSP || type == FileType::NSZ || type == FileType::XCI ||\n           type == FileType::XCZ;',
           '    return type == FileType::NSP || type == FileType::NSZ || type == FileType::XCI ||\n           type == FileType::XCZ || type == FileType::NUP;')
        do('    if (!IsContainerType(type)) {\n        return false;\n    }', '''    if (type == FileType::NUP) {
        FileSys::NupContainer nup{file};
        if (nup.GetStatus() != ResultStatus::Success) return false;
        if (const auto base = nup.FindBasePackage();
            base && nup.GetExeFSDir(*base) != nullptr) return true;
        if (const auto update = nup.FindBestUpdatePackage();
            update && nup.GetExeFSDir(*update) != nullptr) return true;
        return false;
    }

    if (!IsContainerType(type)) {
        return false;
    }''')
        do('    else if (extension == "nsp")\n        return FileType::NSP;\n',
           '    else if (extension == "nsp")\n        return FileType::NSP;\n'
           '    else if (extension == "nup")\n        return FileType::NUP;\n')
        do('    case FileType::NSZ:\n        return "NSZ";\n',
           '    case FileType::NSZ:\n        return "NSZ";\n'
           '    case FileType::NUP:\n        return "NUP";\n')
        do('constexpr std::array<const char*, 68> RESULT_MESSAGES{',
           'constexpr std::array<const char*, 70> RESULT_MESSAGES{')
        do('    "Integrity verification failed.",\n',
           '    "Integrity verification failed.",\n'
           '    "The NUP container is malformed or its TOC hash does not match.",\n'
           '    "The NUP container does not contain a loadable base package.",\n')
        do('    // NX deconstructed ROM directory.\n    case FileType::DeconstructedRomDirectory:',
           '    // NUP (NX Package) container.\n    case FileType::NUP:\n'
           '        return std::make_unique<AppLoader_NUP>(std::move(file));\n\n'
           '    // NX deconstructed ROM directory.\n    case FileType::DeconstructedRomDirectory:')
    elif path == "src/core/core.cpp":
        do('#include "core/file_sys/fs_filesystem.h"\n',
           '#include "core/file_sys/fs_filesystem.h"\n#include "core/file_sys/nup_container.h"\n')
        do('''bool IsSwitch2Program(const FileSys::VirtualFile& file) {
    const auto dir = file != nullptr ? file->GetContainingDirectory() : nullptr;
    const auto npdm = dir != nullptr ? dir->GetFile("main.npdm") : nullptr;
    FileSys::ProgramMetadata metadata;
    return npdm != nullptr && metadata.Load(npdm) == Loader::ResultStatus::Success &&
           metadata.IsSwitch2();
}''', '''bool IsSwitch2Program(const FileSys::VirtualFile& file) {
    FileSys::ProgramMetadata metadata;
    if (FileSys::NupContainer::IsNupFile(file)) {
        FileSys::NupContainer nup{file};
        if (nup.GetStatus() != Loader::ResultStatus::Success) return false;
        std::optional<std::size_t> program;
        if (const auto base = nup.FindBasePackage();
            base && nup.GetExeFSDir(*base) != nullptr) {
            program = base;
        } else if (const auto update = nup.FindBestUpdatePackage();
                   update && nup.GetExeFSDir(*update) != nullptr) {
            program = update;
        }
        const auto exefs = program ? nup.GetExeFSDir(*program) : nullptr;
        const auto npdm = exefs != nullptr ? exefs->GetFile("main.npdm") : nullptr;
        return npdm != nullptr && metadata.Load(npdm) == Loader::ResultStatus::Success &&
               metadata.IsSwitch2();
    }
    const auto dir = file != nullptr ? file->GetContainingDirectory() : nullptr;
    const auto npdm = dir != nullptr ? dir->GetFile("main.npdm") : nullptr;
    return npdm != nullptr && metadata.Load(npdm) == Loader::ResultStatus::Success &&
           metadata.IsSwitch2();
}''')
    else:
        raise BackportError(f"Unexpected port file {path}")
    if text == original:
        raise BackportError(f"No changes made to {path}")
    return text


def make_diff(path: str, before: bytes, after: bytes) -> str:
    before_text = before.decode("utf-8")
    after_text = after.decode("utf-8")
    oldname = "a/" + path if before else "/dev/null"
    newname = "b/" + path
    lines = list(difflib.unified_diff(before_text.splitlines(keepends=True),
                                      after_text.splitlines(keepends=True),
                                      fromfile=oldname, tofile=newname, n=3))
    if not lines:
        raise BackportError(f"No diff for {path}")
    header = f"diff --git a/{path} b/{path}\n"
    if not before:
        header += "new file mode 100644\n"
    return header + "".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Don't write; verify existing 0018 matches pinned sources")
    args = parser.parse_args()
    if not (CORE / ".git").exists():
        raise BackportError("The Eglantine submodule is missing; run git submodule update --init Eglantine")
    head = git("rev-parse", "HEAD").stdout.decode().strip()
    if head != BASE:
        raise BackportError(f"Safety stop: pinned core must be {BASE}, found {head}; no full-core update allowed")
    if git("cat-file", "-e", f"{SOURCE}^{{commit}}", check=False).returncode:
        print(f"Fetching pinned NUP source commit {SOURCE[:12]} (without switching core HEAD)")
        result = git("fetch", "--no-tags", "origin", SOURCE, check=False)
        if result.returncode:
            raise BackportError(f"Cannot fetch upstream NUP commit: {result.stderr.decode(errors='replace')}")
    changes = []
    for path in NEW_FILES:
        if git("cat-file", "-e", f"HEAD:{path}", check=False).returncode == 0:
            raise BackportError(f"Safety stop: {path} already exists in the pinned core")
        original = git_bytes(SOURCE, path)
        if path == "src/core/file_sys/nup_container.cpp":
            try:
                original = modify_nup_container(original.decode("utf-8")).encode("utf-8")
            except ValueError as error:
                raise BackportError(f"NUP V1.000.003 layout patch rejected: {error}") from error
        if not original.endswith(b"\n"):
            raise BackportError(f"Source file {path} unexpectedly has no final newline")
        changes.append(make_diff(path, b"", original))
    for path in ("src/core/CMakeLists.txt", "src/core/loader/loader.h",
                 "src/core/loader/loader.cpp", "src/core/core.cpp"):
        before = git_bytes("HEAD", path)
        after = replace(path, before.decode("utf-8")).encode("utf-8")
        changes.append(make_diff(path, before, after))
    content = ("".join(changes)).encode("utf-8")
    if args.check:
        if not PATCH.is_file() or PATCH.read_bytes() != content:
            raise BackportError("0018 patch missing or differs from the exact pinned source")
    elif not PATCH.is_file() or PATCH.read_bytes() != content:
        PATCH.write_bytes(content)
    print(f"NUP core patch ready: {PATCH.relative_to(ROOT)} ({len(content)} bytes), pinned {BASE[:12]} + NUP {SOURCE[:12]}")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BackportError, UnicodeDecodeError) as exc:
        print(f"NUP BACKPORT FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
