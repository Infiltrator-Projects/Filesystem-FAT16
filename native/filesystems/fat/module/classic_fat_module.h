/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Infiltrator Filesystems — experimental freestanding CLASSIC_FAT module ABI.
 * Portable source derived from the format rules used by Defragmenter's
 * fat_volume.c and FAT Test Media, with no Linux VFS or libc dependencies.
 * Version 1 is deliberately read-only: no unsafe write/defrag claim.
 */
#ifndef INFILTRATOR_CLASSIC_FAT_MODULE_H
#define INFILTRATOR_CLASSIC_FAT_MODULE_H

#include <stddef.h>
#include <stdint.h>

typedef int (*IfsClassicFatReadAt)(void *context, uint64_t offset, void *buffer,
                             uint32_t bytes);
typedef struct {
    IfsClassicFatReadAt read_at; /* Returns zero for a complete read. */
    void *context;
    uint64_t device_bytes; /* Length of volume, NOT size of whole disk. */
} IfsClassicFatIo;

typedef struct {
    uint64_t volume_bytes;
    uint64_t fat_offset;
    uint64_t root_offset;
    uint64_t data_offset;
    uint32_t cluster_bytes;
    uint32_t cluster_count;
    uint32_t total_sectors;
    uint32_t root_entries;
    uint16_t bytes_per_sector;
    uint16_t sectors_per_fat;
    uint8_t sectors_per_cluster;
    uint8_t fat_copies;
} IfsClassicFatVolume;

typedef struct {
    char name[13]; /* Canonical 8.3 ASCII name, NUL terminated. No LFN claim. */
    uint32_t first_cluster;
    uint32_t size_bytes;
    uint8_t attributes;
} IfsClassicFatFile;

/* Internal arithmetic and FAT chain inspection; not a separate ABI. */
int ifs_classic_fat_probe(const IfsClassicFatIo *, IfsClassicFatVolume *);
int ifs_classic_fat_root_file(const IfsClassicFatIo *, const IfsClassicFatVolume *,
                              uint32_t, IfsClassicFatFile *);
int ifs_classic_fat_read_file(const IfsClassicFatIo *, const IfsClassicFatVolume *,
                              const IfsClassicFatFile *, uint64_t, void *, uint32_t);
int ifs_classic_fat_root_file_fragments(const IfsClassicFatIo *,
                                        const IfsClassicFatVolume *,
                                        const IfsClassicFatFile *, uint32_t *);
#endif
