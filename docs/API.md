# Filesystem-FAT16 ABI and consumer contract

The x86-64 ELF shared object at `/System/Filesystems/FAT16.so` exposes
`infiltrator_filesystem_api_v2` for applications and BOOT. The Common
descriptor identifies `fat16` and exposes CORE file and directory operations
and VOLUME query, label, sync and format operations. The ELF identity marker
is `IFS-MODULE:fat16:common2`.

The dedicated relocation and journal recovery interface remains available
through Defragmenter's process host while the corresponding Common V2
operations are qualified.

## V5 metadata and volume operations

The declarations are in `native/filesystems/fat/portable/fatfs_module.h`.
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
the caller supplies a valid current date. BOOT's Common V2 read-only host
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

BOOT runs the freestanding Common V2 ELF through its generic loader.
One relocated image owns one mount. It supplies bounded read-only block
I/O and never invokes the relocation or journal recovery interface.
Native builds use CPU tuning, LTO and trained PGO and avoid AVX/AMX state
requirements in firmware.

The portable API supports one active volume per module, requires serialized access and exclusive device ownership. Formatting is destructive and not atomic on write failure. On full media or interrupted allocation, partial extension may occur. Format-identity checks and independent readback are required. The module's own source and documented on-disk contracts are authoritative; a GUI geometry guess does not authorise mutation.

## Transitional platform adapters (not the end state)

`fat16.ko` is kernel-version dependent and relies on a compatible Linux FAT core. `FAT16.efi` requires EDK2 and firmware qualification. Neither is treated as the same ABI as this shared object and neither is installed by the independent initial Debian package.
