#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
module=$(realpath "${1:?pass FAT16.so}")
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
cc=${CC:-cc}
"$cc" -std=c11 -O2 -Wall -Wextra -Werror \
    -I "$root/native/filesystems/fat/portable" \
    "$root/tests/fatfs_v3_realimage_test.c" -ldl -o "$work/v3"
"$cc" -std=c11 -O2 -Wall -Wextra -Werror \
    -I "$root/native/filesystems/fat/portable" \
    "$root/tests/fatfs_v4_format_test.c" -ldl -o "$work/v4"
truncate -s 1440K "$work/foreign.img"
truncate -s 32M "$work/own.img"
mkfs.fat -F 12 -I "$work/foreign.img"
mkfs.fat -F 16 -I "$work/own.img"
before=$(sha256sum "$work/foreign.img")
"$work/v3" "$module" "$work/own.img" "$work/foreign.img"
fsck.fat -n "$work/own.img"
"$work/v3" "$module" "$work/own.img" "$work/foreign.img" cleanup
test "$(sha256sum "$work/foreign.img")" = "$before"
for sector in 512 4096; do
    truncate -s 32M "$work/format-$sector.img"
    "$work/v4" "$module" "$work/format-$sector.img" "$sector" 4096
    fsck.fat -n "$work/format-$sector.img"
done
echo FAT16-BOOT-MODULE-V3-V4-LIFECYCLE-PASS
