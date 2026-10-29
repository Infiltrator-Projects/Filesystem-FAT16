# Filesystem-FAT16 ABI and consumer contract

**One-driver endpoint:** [FAT16.so is shared by applications and BOOT](ONE_MODULE_END_STATE.md). The same freestanding ELF now exposes a generic boot ABI as well as the existing filesystem and Defragmenter interfaces. Kernel-side SO loading remains separate work. The `.ko`/`.efi` code below is transitional.

## Shipped shared object

Filename: `FAT16.so` under `/System/Filesystems`. Architecture: x86-64 ELF shared object. The independent module must export:

- `infiltrator_filesystem_module_v1`: format-specific read and fragment analysis.
- `infiltrator_filesystem_module_v3`: portable writable filesystem and file/directory operations.
- `infiltrator_filesystem_module_v4`: formatting, attributes, timestamps and free-space reporting.
- `infiltrator_filesystem_module_v5`: complete creation/modification/access metadata, volume labels/serial reads, OEM code-page selection and flushing; contains a pointer to V4.
- `infiltrator_filesystem_defrag_v1`: relocation, journal and crash recovery, invoked in a dedicated Defragmenter child-process host.
- `infiltrator_filesystem_boot_v1`: generic read-only mount, streaming file contexts, directory enumeration and volume labels for Boot's UEFI bridge.

The `.ifsmeta` identity contains `IFS-MODULE:fat16:1`, `IFS-MODULE:fat16:3`, `IFS-MODULE:fat16:4` and `IFS-MODULE:fat16:5`. A caller must check ABI versions, structure lengths, the actual detected FAT width and function pointers, not merely the filename. The defrag ABI host must supply all function pointers defined in `native/filesystems/fat/defrag/fat_defrag_abi.h`. The child-process lifetime must keep the module loaded for cleanup handlers.

## V5 metadata and volume operations

The declarations are in `native/filesystems/fat/portable/fatfs_module.h`.
V5 is additive: no V1/V3/V4, Boot or Defragmenter structure changes.
Operations return zero on success and a negative value on failure, as V3/V4 do.

`metadata(path, out)` returns size, attributes, UTF-8 long and short names, and
packed FAT local dates/times. Creation fractions count 10 ms units (0–199)
within the packed two-second creation interval. Access has date precision.
`set_times(path, times, mask)` requires `structure_bytes == sizeof(*times)`
and reserved fields zero. Mask bits 1/2/4 select creation/modification/access;
unselected fields are preserved. Invalid dates, including 2100-02-29, times
or fractions are rejected before writing. A zero creation date/time/fraction
or zero access date explicitly clears that optional field. Modification dates
must be valid and nonzero. Writes update modification and access dates from
the caller's clock; successful nonempty V3 reads update the access date if
the caller supplies a valid current date. Boot's separate read-only interface
never performs this update. V4 modification-only updates preserve creation.

`get_label(buffer, bytes, serial)` returns the UTF-8 root volume label and,
if requested, the BPB volume serial. Use a 34-byte label buffer. `set_label`
accepts up to eleven OEM bytes, uppercases the label, trims trailing spaces,
and removes it for an empty string. Invalid characters or unrepresentable
names fail. The authoritative root label and an existing extended BPB label
are updated together; ordinary FAT writes are not failure-atomic.

`set_codepage(cp)` is allowed only while unmounted. CP437 is the default;
supported pages are 437, 720, 737, 771, 775, 850, 852, 855, 857, 860, 861,
862, 863, 864, 865, 866, 869, 932, 936, 949 and 950. The volume does not
record its OEM page; the caller selects it. Long-name API strings remain
UTF-8. Each separately loaded image owns its selection. `flush()` reports the
host's durable-flush result. Filesystem operations already close and sync
their temporary handles before returning success.

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
