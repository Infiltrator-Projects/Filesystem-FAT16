# Filesystem-FAT16 ABI and consumer contract

**One-driver endpoint:** [FAT16.so is shared by applications and BOOT](ONE_MODULE_END_STATE.md). The same freestanding ELF now exposes a generic boot ABI as well as the existing filesystem and Defragmenter interfaces. Kernel-side SO loading remains separate work. The `.ko`/`.efi` code below is transitional.

## Shipped shared object

Filename: `FAT16.so` under `/System/Filesystems`. Architecture: x86-64 ELF shared object. The independent module must export:

- `infiltrator_filesystem_module_v1`: format-specific read and fragment analysis.
- `infiltrator_filesystem_module_v3`: portable writable filesystem and file/directory operations.
- `infiltrator_filesystem_module_v4`: formatting, attributes, timestamps and free-space reporting.
- `infiltrator_filesystem_defrag_v1`: relocation, journal and crash recovery, invoked in a dedicated Defragmenter child-process host.
- `infiltrator_filesystem_boot_v1`: generic read-only mount, streaming file contexts, directory enumeration and volume labels for Boot's UEFI bridge.

The `.ifsmeta` identity must contain `IFS-MODULE:fat16:1`, `IFS-MODULE:fat16:3` and `IFS-MODULE:fat16:4`. A caller must check ABI versions, structure lengths, the actual detected FAT width and function pointers, not merely the filename. The defrag ABI host must supply all function pointers defined in `native/filesystems/fat/defrag/fat_defrag_abi.h`. The child-process lifetime must keep the module loaded for cleanup handlers.

## Constraints

The boot ABI is defined in `native/include/infiltratr/fs/boot_module.h`. Its
fixed `.ifsboot` manifest declares ELF machine 62, profile 1 and format `fat16`.
Calls and host read callbacks use SysV x86-64, including from Microsoft-ABI
UEFI protocol functions. All filesystem interpretation remains in this module.
One relocated image owns one mount; Boot creates another image per volume.
Read-only boot mounting installs a rejecting write callback into the same
FatFs engine, and never invokes the Defragmenter host. File contexts retain
FatFs cursors for sequential kernel/initramfs reads. The native profile retains
O3, native tuning, LTO and trained PGO while disabling AVX/AMX state requirements
that firmware has not promised to enable. Defragmenter's ABI layout, entry
point, host callbacks and process lifetime contract are unchanged.

The portable API supports one active volume per module, requires serialized access and exclusive device ownership. Formatting is destructive and not atomic on write failure. On full media or interrupted allocation, partial extension may occur. Format-identity checks and independent readback are required. The module's own source and documented on-disk contracts are authoritative; a GUI geometry guess does not authorise mutation.

## Transitional platform adapters (not the end state)

`fat16.ko` is kernel-version dependent and relies on a compatible Linux FAT core. `FAT16.efi` requires EDK2 and firmware qualification. Neither is treated as the same ABI as this shared object and neither is installed by the independent initial Debian package.
