# FAT16 shared-module completion

Version 0.1.6 completes the shared module's file, directory, metadata and
volume operations while preserving the released Boot and Defragmenter ABIs.
The on-disk reference is Microsoft's FAT specification, sections 3.5, 4 and 6:
https://www.scs.stanford.edu/~zyedidia/docs/_other/fat.pdf.

| Operation or format rule | Interface | Verification |
| --- | --- | --- |
| Read/write, create, append, truncate, delete, rename | V3 | Independent FAT images, readback, fsck, full-media failure |
| Fixed root, growing subdirectories, valid directory reparenting | V3 | Root exhaustion/reuse; nested directories; ancestry and alias checks |
| Long Unicode names and OEM short names | V3/V5 | UTF-8 lifecycle; independently supplied CP437/850/932/936/949/950 names |
| FAT16 classification: 4,085–65,524 clusters | All module engines | Exact endpoint images; foreign width rejected without writes |
| Sector sizes 512/1024/2048/4096; clusters up to 128 sectors | V3/V4 | 32 combinations including one/two FATs; independent FAT-copy comparison |
| Formatting and free-space reporting | V4 | All four sector sizes, wrong-width write-free preflight, fsck |
| Read-only/hidden/system/archive attributes | V4 | Read-only mutation refusal, raw entry and lifecycle checks |
| Creation time/fraction, modification time, access date | V5, V4 compatibility | Raw directory offsets; leap years; invalid-input no-write; write/read/remount/rename preservation |
| Volume label set/get/remove and serial read | V5 | Root/BPB comparison, invalid labels, fsck and mtools |
| File size up to 0xFFFFFFFF bytes | V3 | Sparse independent chain, last-byte read/write, overflow/EOF rejection |
| Bad/free/reserved/EOC chain values | Shared FAT/Defragmenter engines | Allocation tests and maximal-volume high-cluster relocation |
| Explicit flush and propagated I/O failures | V3/V5 | Callback failures, lifecycle and firmware I/O-failure tests |
| Defragmentation, growth defrag and recovery | Existing defrag V1 | Unchanged production host, interrupted journal/device writes, wrong-inode recovery refusal |
| Read-only boot from identical SO bytes | Existing boot V1 | Production ELF/UEFI tests, sanitizers and real Linux boot under OVMF |
| FAT sector size independent of device block size | Existing boot V1 | All four FAT sector sizes with 512-byte and 4096-byte host blocks; byte-identical media after boot reads |
| Portable and native packages | Standalone release | Native measured PGO/LTO; module exports, imports, package contents and exact hash |

Creation fractions are represented explicitly as 0–199 ten-millisecond units.
V4 modification-only updates do not overwrite creation fields. Normal V3 reads
maintain access dates from a valid caller clock; Boot remains read-only.
Selectable OEM pages belong to each module image and default to CP437.
Malformed control characters are rejected instead of truncating a path.

The same count-based rules apply inside the portable engine, format preview,
legacy reader and defragmentation engine. FAT16's last valid cluster is
`CountOfClusters + 1`; on maximal volumes FFF0–FFF5 are valid links. Reserved
values start beyond that volume's last cluster. Reserved FAT entry 1's
clean/error status flags do not change the legacy reader's format identity.
Defragmenter retains its stricter clean-volume write preconditions.

The module remains serialized and owns one mounted volume per loaded image.
FAT mutations are not transactions: a full device or failed write may leave
partial extension, and the host must honor flush and exclusive-ownership
contracts. Process-interruption recovery tests do not certify physical power
loss. A kernel-side SO bridge, signed-module policy and physical hardware
qualification remain separate integration work; this release does not claim
those have been implemented by adding filesystem operations.
