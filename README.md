# Filesystem FAT16

Standalone filesystem repository migration in progress.
This migration branch contains the full original Filesystems source at
commit `d7a572dcd0d11f7bc69cc05e09e3e944be747838` as a safety-preserving starting snapshot.
It intentionally contains unrelated filesystem code to be trimmed after
independent FAT16.so, fat16.ko and FAT16.efi
builds, tests and packaging are created. No release is authorised by this copy.

The FAT16 defragmentation and recovery engine must remain in
FAT16.so with the ABI expected by Defragmenter. The central
Filesystems repository and Defragmenter have not been modified.
The original upstream README is FILESYSTEMS-SOURCE-README.md.
