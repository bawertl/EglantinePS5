#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Narrow, fail-closed backport of dual NUP record layout support.

The original NUP implementation is fetched from an immutable Lichii commit by
`generate-nup-backport.py`. This helper adjusts only the NUP container source.
No runtime checks are removed. Not a general-purpose NUP format detector.
"""


def modify_nup_container(text: str) -> str:
    path = "src/core/file_sys/nup_container.cpp"

    def replace_once(old: str, new: str) -> None:
        nonlocal text
        hits = text.count(old)
        if hits != 1:
            raise ValueError(f"{path}: anchor count {hits}, expected 1: {old[:100]!r}")
        text = text.replace(old, new, 1)

    # Preserve the upstream packed record definitions as the legacy decoding.
    # Both new structures are packed to preserve their exact 0x40/0x50 size;
    # the additional u32 in the package header accounts for the wire padding.
    replace_once('struct TlvHeader {', '''struct PackageRecordAligned {
    u64_le title_id;
    u32_le root_dir;
    u32_le exefs_dir;
    u32_le romfs_dir;
    u32_le version;
    u8 kind;
    u8 flags;
    u16_le reserved;
    u32_le aligned_reserved;
    u64_le meta_offset;
    u32_le meta_size;
    u32_le reserved2;
    std::array<u8, 16> reserved3;
};
static_assert(sizeof(PackageRecordAligned) == PackageRecordSize);
static_assert(offsetof(PackageRecordAligned, meta_offset) == 0x20);
static_assert(offsetof(PackageRecordAligned, meta_size) == 0x28);

struct FileRecordAligned {
    u32_le name_offset;
    u32_le name_length;
    u64_le size;
    u64_le extent_offset;
    u64_le extent_size;
    std::array<u8, 0x20> sha256;
    u8 codec;
    u8 codec_flags;
    u16_le reserved2;
    std::array<u8, 12> reserved3;
};
static_assert(sizeof(FileRecordAligned) == FileRecordSize);
static_assert(offsetof(FileRecordAligned, size) == 0x08);
static_assert(offsetof(FileRecordAligned, extent_offset) == 0x10);
static_assert(offsetof(FileRecordAligned, extent_size) == 0x18);
static_assert(offsetof(FileRecordAligned, sha256) == 0x20);
static_assert(offsetof(FileRecordAligned, codec) == 0x40);

struct TlvHeader {''')

    replace_once('#include <algorithm>\n', '#include <algorithm>\n#include <cstddef>\n')

    replace_once('bool Sha256(const u8* data, std::size_t size, std::array<u8, 0x20>& out) {', '''// Decode aligned records into the original, canonical on-disk record type.
// The decoder is intentionally independent of the package metadata layout.
FileRecord DecodeFileRecord(const u8* source, bool aligned) {
    FileRecord record{};
    if (!aligned) {
        std::memcpy(&record, source, sizeof(record));
        return record;
    }
    FileRecordAligned raw{};
    std::memcpy(&raw, source, sizeof(raw));
    record.name_offset = raw.name_offset;
    record.name_length = raw.name_length;
    record.size = raw.size;
    record.sha256 = raw.sha256;
    record.extent_offset = raw.extent_offset;
    record.extent_size = raw.extent_size;
    record.codec = raw.codec;
    record.codec_flags = raw.codec_flags;
    record.reserved2 = raw.reserved2;
    return record;
}

// These are the original NUP parser's record constraints, expressed with
// subtraction instead of additions so untrusted offsets cannot overflow.
bool ValidNupFileRecord(const FileRecord& record, u64 blob_begin, u64 file_end,
                        u64 pool_size) {
    if (record.codec > CodecZstd || record.codec_flags != 0 ||
        (record.size == 0 && (record.extent_offset != 0 || record.extent_size != 0))) {
        return false;
    }
    if (record.size != 0 &&
        (record.extent_size == 0 || record.extent_offset < blob_begin ||
         record.extent_offset % 0x10 != 0 || record.extent_offset > file_end ||
         record.extent_size > file_end - record.extent_offset)) {
        return false;
    }
    return record.name_offset <= pool_size &&
           record.name_length <= pool_size - record.name_offset;
}

// A missing metadata block is valid. A present one must be wholly inside the
// physical container. The original parser's bounds check was less strict.
bool ValidNupMeta(u64 offset, u32 size, u64 file_end) {
    if (size == 0) return offset == 0;
    return offset != 0 && offset <= file_end && size <= file_end - offset;
}

bool Sha256(const u8* data, std::size_t size, std::array<u8, 0x20>& out) {''')

    replace_once('''    const u64 needed = TocHeaderSize + static_cast<u64>(header.package_count) * PackageRecordSize +
                       header.dir_count * DirRecordSize + header.file_count * FileRecordSize;
''', '''    // Guard against overflow in untrusted table counts before the additions.
    if (header.package_count > toc.size() / PackageRecordSize ||
        header.dir_count > toc.size() / DirRecordSize ||
        header.file_count > toc.size() / FileRecordSize) {
        LOG_ERROR(Loader, "NUP-DIAG: TOC table counts exceed physical TOC bounds");
        status = Loader::ResultStatus::ErrorNUPBadFormat;
        return false;
    }
    const u64 needed = TocHeaderSize + static_cast<u64>(header.package_count) * PackageRecordSize +
                       header.dir_count * DirRecordSize + header.file_count * FileRecordSize;
''')

    replace_once('''    std::size_t pos = TocHeaderSize;
    packages.reserve(header.package_count);
''', '''    // Determine the file-record layout from ALL records, never just one.
    // Both layouts must pass the same original format and bounds checks.
    const u64 file_table = TocHeaderSize + static_cast<u64>(header.package_count) * PackageRecordSize +
                           header.dir_count * DirRecordSize;
    bool legacy_files = true;
    bool aligned_files = true;
    u64 legacy_failed_at = 0;
    u64 aligned_failed_at = 0;
    for (u64 i = 0; i < header.file_count; ++i) {
        const u8* raw = base + static_cast<std::size_t>(file_table + i * FileRecordSize);
        if (legacy_files && !ValidNupFileRecord(DecodeFileRecord(raw, false), blob_offset,
                                                file_size, header.pool_size)) {
            legacy_files = false;
            legacy_failed_at = i;
        }
        if (aligned_files && !ValidNupFileRecord(DecodeFileRecord(raw, true), blob_offset,
                                                 file_size, header.pool_size)) {
            aligned_files = false;
            aligned_failed_at = i;
        }
        if (!legacy_files && !aligned_files) break;
    }
    if (!legacy_files && !aligned_files) {
        LOG_ERROR(Loader, "NUP-DIAG: both file layouts rejected (legacy at {}, aligned at {})",
                  legacy_failed_at, aligned_failed_at);
        status = Loader::ResultStatus::ErrorNUPBadFormat;
        return false;
    }
    // An ambiguous nonempty file table must never silently select an
    // incompatible layout. Empty tables use the original legacy convention.
    if (header.file_count != 0 && legacy_files && aligned_files) {
        LOG_ERROR(Loader, "NUP-DIAG: file layout ambiguous across {} records", header.file_count);
        status = Loader::ResultStatus::ErrorNUPBadFormat;
        return false;
    }
    const bool use_aligned_files = aligned_files && !legacy_files;
    LOG_INFO(Loader, "NUP-DIAG: {} file layout; {} record(s) validated",
             use_aligned_files ? "aligned" : "legacy", static_cast<u64>(header.file_count));

    std::size_t pos = TocHeaderSize;
    packages.reserve(header.package_count);
''')

    replace_once('''        PackageRecord record{};
        std::memcpy(&record, base + pos, sizeof(record));
        pos += PackageRecordSize;
''', '''        PackageRecord record{};
        PackageRecordAligned aligned_record{};
        std::memcpy(&record, base + pos, sizeof(record));
        std::memcpy(&aligned_record, base + pos, sizeof(aligned_record));
        pos += PackageRecordSize;

        const bool valid_legacy = ValidNupMeta(record.meta_offset, record.meta_size, file_size);
        const bool valid_aligned = ValidNupMeta(aligned_record.meta_offset,
                                                aligned_record.meta_size, file_size);
        if (!valid_legacy && !valid_aligned) {
            LOG_ERROR(Loader, "NUP-DIAG: package {} metadata bounds invalid in both layouts "
                              "(legacy off={}, size={}; aligned off={}, size={}; file={})",
                      i, static_cast<u64>(record.meta_offset), static_cast<u32>(record.meta_size),
                      static_cast<u64>(aligned_record.meta_offset),
                      static_cast<u32>(aligned_record.meta_size), file_size);
            status = Loader::ResultStatus::ErrorNUPBadFormat;
            return false;
        }
        if (valid_legacy && valid_aligned &&
            (record.meta_offset != aligned_record.meta_offset ||
             record.meta_size != aligned_record.meta_size)) {
            // Only resolve truly ambiguous metadata via an unambiguous file
            // layout; never silently prefer a new interpretation on legacy data.
            if (header.file_count == 0) {
                LOG_ERROR(Loader, "NUP-DIAG: package {} metadata layout ambiguous", i);
                status = Loader::ResultStatus::ErrorNUPBadFormat;
                return false;
            }
        }
        const bool aligned_package = valid_aligned &&
                                     (!valid_legacy || (valid_legacy && use_aligned_files));
        if (aligned_package) {
            record.meta_offset = aligned_record.meta_offset;
            record.meta_size = aligned_record.meta_size;
        }
        LOG_INFO(Loader, "NUP-DIAG: package {} uses {} metadata layout, size={}",
                 i, aligned_package ? "aligned" : "legacy", static_cast<u32>(record.meta_size));
''')

    replace_once('''        FileRecord record{};
        std::memcpy(&record, base + pos, sizeof(record));
        pos += FileRecordSize;
        if (record.codec > CodecZstd || record.codec_flags != 0 ||
            (record.size == 0 && (record.extent_offset != 0 || record.extent_size != 0)) ||
            (record.size != 0 &&
             (record.extent_size == 0 || record.extent_offset < blob_offset ||
              record.extent_offset % 0x10 != 0 ||
              record.extent_offset + record.extent_size > file_size)) ||
            record.name_offset + record.name_length > header.pool_size) {
''', '''        FileRecord record = DecodeFileRecord(base + pos, use_aligned_files);
        pos += FileRecordSize;
        if (!ValidNupFileRecord(record, blob_offset, file_size, header.pool_size)) {
''')

    return text
