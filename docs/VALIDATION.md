# Filesystem-FAT16 validation and release criteria

**Completion standard:** [one FAT16.so shared across consumers](ONE_MODULE_END_STATE.md). Boot's actual SO loading/Linux handoff and Defragmenter's unchanged write/recovery host are now exercised against identical module bytes. Kernel SO mount/root behavior and physical firmware remain separate acceptance gates.

## Shared-module integration

Boot's `tests/run-so-tests.sh` validates the matching generic ABI header,
malformed ELF rejection and the production UEFI file adapter against independent
FAT media. `tests/test_so_boot.py` boots the production Boot EFI and a real Linux
EFI-stub kernel/initramfs through this same object in OVMF, including a rejected
module case that cannot silently boot through firmware FAT.

This repository's `tests/check-fat16-lifecycle.sh` retains V3 read/write and
V4 format/metadata/free-space behavior with independent dosfstools checks at
512-byte and 4-KiB sector sizes. `tests/boot_defrag_compat.py` builds the unchanged
Defragmenter host/core and its authoritative Common target from the pinned
consumer checkout. It checks identical module hashes, the unchanged ABI header,
Defragment/Growth Defrag, wrong-format rejection, recovery at four journal
stages, wrong-inode refusal and interruptions after real device-write calls.
These process-interruption tests do not simulate physical power loss.

## Evidence separation

1. Source copied: import hash, local source files and preserved notices, but NO functional qualification.
2. Build: native compiler produces an ELF DYN `FAT16.so` with no unexpected dynamic dependencies.
3. ABI: correct width metadata, V1/V3/V4 and Defragmenter entry points, no substitution by another format.
4. Fixture: current `tests/fat16_module_test.c` runs against the exact standalone shared object on an in-memory volume.
5. Integration: Defragmenter's versioned child-worker maps, relocates and recovers disposable independently formatted FAT images, including interrupted-journal stages and independent post-verification.
6. Packaging: inspect exact owned paths in the Debian archive; install the native `.run`, verify native package version, BUILD-INFO and module SHA-256, and ensure the other format remains unchanged.
7. Hardware: physical removable media, supported distributions/kernels and actual UEFI firmware testing. CI and QEMU are not substitutes for hardware evidence.

## Native PGO qualification

The aggressive native installer compiles a temporary instrumented shared object and trains it with the V1 fragmented-file read fixture and the V4 formatting/V3 writing/metadata fixture on a disposable regular-file image. A nonempty measured GCC profile is mandatory before rebuilding with PGO; only the temporary training object may link the host profiling runtime. The final -O3, CPU-native, LTO and trained-PGO module must retain freestanding -nostdlib linkage, zero dynamic dependencies and its exact FAT ABI identity.

The training data does not cover every defragmentation or crash-recovery path, and successful optimisation flags do not establish a measured performance improvement.

## CI contract

Run `make check`, `make release`, inspect the resulting package, invoke `.run --profile aggressive --system-package-mode` in a disposable Ubuntu runner, and independently verify installed ABI and package ownership. Publishing is permitted only after the successful release-job gate on the exact main commit. GitHub release source ZIP is automatic with the version tag and is not a third uploaded asset.

## Outstanding confidence limits

The first standalone package covers only the shared object, not independent `.ko` or `.efi` install/boot. Broad fuzzing of malformed BPBs, interrupted media writes, durability under physical power loss, alignment/geometry variations, cross-architecture support and exact Defragmenter release pairing remain separate gates. Do not label these fully qualified merely from a green compilation workflow.
