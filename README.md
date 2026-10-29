# Filesystem-FAT16

**Shared driver:** [FAT16.so is the sole filesystem implementation for its consumers](docs/ONE_MODULE_END_STATE.md). Applications and BOOT can now use the same object through their respective interfaces; Boot's generic ELF/UEFI bridge is tested in OVMF with a real Linux kernel/initramfs. Kernel SO integration remains separate. Existing Linux `.ko` and UEFI `.efi` code remains transitional.

Independent InfiltratorOS FAT16 filesystem repository. One repository is authoritative for exactly one installed shared-object module: `/System/Filesystems/FAT16.so`.

## Actual status

The full source was copied from Infiltrator-Projects/Filesystems, pinned to commit `d7a572dcd0d11f7bc69cc05e09e3e944be747838`, including the FAT filesystem interface, its FAT-specific defragmentation and recovery engine, portable FatFs, the Linux VFS source, TianoCore EFI driver source, tests, and Common support source. Import alone is NOT a qualified standalone release.

`make` builds `build/FAT16.so` solely from this repository. `make check` checks module exports, format identity, and the existing standalone FAT fixture. `make release` produces the generic `.deb` and native `.run`; a published GitHub release tag supplies GitHub's automatic source ZIP (not a third uploaded asset). Releases are permitted only when the exact HEAD qualifies in CI.

## Ownership

- This repository: fat16 interpretation, read/write/file APIs, formatting, allocation, fat16 relocation, journal/recovery, format-specific kernel and EFI source and tests.
- Filesystems: discovery, selection and management; it must not silently overwrite or install a second copy of this module after package ownership transfers.
- Defragmenter: the worker and UI; it dynamically loads the installed `FAT16.so` and calls `infiltrator_filesystem_defrag_v1` via the existing versioned host ABI.
- Linux/UEFI transition: existing `fat16.ko` and `FAT16.efi` remain useful compatibility paths. Boot's generic loader uses the **same `FAT16.so`**, including its existing Defragmenter interface. Physical firmware and a kernel-side SO bridge require separate qualification.

## Filesystem qualification scope

FAT16 16-bit allocation entries, fixed-root directories and the complete 4,085–65,524 data-cluster range. Foreign formats and malformed geometry are rejected before changes. V3 provides full file/directory read and write; V4 adds formatting, attributes, modification times and free space. V5 completes creation time (including the 10 ms fraction), access dates, volume labels/serial reads, OEM code-page selection and explicit flushing. The existing Boot and Defragmenter interfaces retain their layouts. See the [completion and test matrix](docs/FAT16_COMPLETION.md), [Validation](docs/VALIDATION.md) and [API](docs/API.md). Destructive testing uses disposable images only.

## Documentation

[Architecture](docs/ARCHITECTURE.md) · [Design](docs/DESIGN.md) · [Validation](docs/VALIDATION.md) · [Packaging](docs/PACKAGING.md) · [Source provenance](docs/SOURCE.md) · [Security](docs/SECURITY.md) · [Roadmap](docs/ROADMAP.md) · [Documentation index](docs/README.md)
