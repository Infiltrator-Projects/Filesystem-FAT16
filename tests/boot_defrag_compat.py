#!/usr/bin/env python3
"""Exercise the unchanged Defragmenter host against the boot-capable FAT16.so.

The small CMake target compiles production host/core files and the production
Common target. Fixtures and verification come from the pinned Defragmenter
checkout; this test contains no filesystem implementation or alternate host.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def execute(command, **kwargs):
    return subprocess.run([str(x) for x in command], check=True, **kwargs)


def build_host(source, work):
    core = source / "src/core"
    common = source / "shared/infiltratr-common"
    assert (common / "VERSION").is_file(), "Initialise Defragmenter's pinned Common submodule"
    work.mkdir()
    version = (source / "VERSION").read_text().strip()
    (work / "version.h").write_text((core / "version.h.in").read_text().replace(
        "@DEFRAGMENTER_PACKAGE_VERSION@", version))
    (work / "CMakeLists.txt").write_text(f'''cmake_minimum_required(VERSION 3.20)
project(Fat16BootCompatibility C)
set(INFILTRATR_COMMON_BUILD_TESTS OFF)
set(INFILTRATR_COMMON_BUILD_SHARED OFF)
add_subdirectory("{common}" common)
add_executable(fat-worker "{source}/native/fat_module_loader.c"
 "{core}/ld_runtime.c" "{core}/ld_io.c" "{core}/ld_device.c"
 "{core}/ld_stop.c" "{core}/ld_path.c" "{core}/ld_protocol.c")
target_include_directories(fat-worker PRIVATE "{core}" "{source}/native" "{work}")
target_compile_definitions(fat-worker PRIVATE _GNU_SOURCE _FILE_OFFSET_BITS=64 IFS_FAT_TESTING)
target_compile_options(fat-worker PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_link_libraries(fat-worker PRIVATE InfiltratrCommon::Common dl pthread)
''')
    execute(["cmake", "-S", work, "-B", work / "build"])
    execute(["cmake", "--build", work / "build", "-j", "4"])
    return work / "build/fat-worker"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--defragmenter-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.defragmenter_source.resolve() / "defragger"
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    module = args.module.resolve()
    root = Path(__file__).resolve().parents[1]
    assert (root / "native/filesystems/fat/defrag/fat_defrag_abi.h").read_bytes() == (
        source / "native/fat_defrag_abi.h").read_bytes(), "Defragmenter ABI drift"
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    fixture = source / "tests/make_fat12_16_image.py"
    verifier = source / "tests/verify_growth_fat12_16.py"
    # Trusted /tmp ancestry is part of the production journal safety contract.
    with tempfile.TemporaryDirectory(prefix="ifs-fat16-compat-") as temporary:
        work = Path(temporary)
        installed = work / "Filesystems"
        installed.mkdir()
        shutil.copyfile(module, installed / "FAT16.so")
        assert digest(module) == digest(installed / "FAT16.so")
        environment = dict(os.environ, IFS_TEST_MODULE_PARENT=str(work))
        worker = build_host(source, work / "host")

        def make_image(name, kind="fat16"):
            image = work / (name + ".img")
            execute(["python3", fixture, kind, image, "fragmented"])
            return image

        def operation(command, image, journal, name, extra=None, expected=0):
            env = dict(environment, **(extra or {}))
            with (output / (name + ".log")).open("w") as log:
                result = subprocess.run([str(worker), command, str(image), "--write",
                                         "--confirm", str(image), "--journal", str(journal)],
                                        env=env, stdout=log, stderr=subprocess.STDOUT)
            assert result.returncode == expected, (name, result.returncode)

        for command in ["defrag", "growth-defrag"]:
            image = make_image(command)
            operation(command, image, work / (command + ".journal"), command)
            execute(["python3", verifier, "fat16", image])

        foreign = make_image("foreign", "fat12")
        before = digest(foreign)
        operation("defrag", foreign, work / "foreign.journal", "foreign", expected=1)
        assert digest(foreign) == before and not (work / "foreign.journal").exists()

        for stage in range(1, 5):
            name = "journal-" + str(stage)
            image = make_image(name)
            journal = work / (name + ".journal")
            operation("defrag", image, journal, name,
                      {"IFS_TEST_CRASH_AFTER_JOURNAL": str(stage)}, 86)
            assert journal.is_file()
            wrong = work / "wrong-inode.img"
            shutil.copyfile(image, wrong)
            before = digest(wrong)
            operation("recover", wrong, journal, name + "-wrong-target", expected=1)
            assert digest(wrong) == before and journal.is_file()
            operation("recover", image, journal, name + "-recover")
            assert not journal.exists()
            operation("defrag", image, journal, name + "-finish")
            execute(["python3", verifier, "fat16", image])

        exercised = 0
        for write in range(1, 9):
            name = "device-write-" + str(write)
            image = make_image(name)
            journal = work / (name + ".journal")
            with (output / (name + ".log")).open("w") as log:
                status = subprocess.run([str(worker), "defrag", str(image), "--write",
                                         "--confirm", str(image), "--journal", str(journal)],
                    env=dict(environment, IFS_TEST_CRASH_AFTER_DEVICE_WRITE=str(write)),
                    stdout=log, stderr=subprocess.STDOUT).returncode
            assert status in (0, 87), (name, status)
            if status == 87:
                exercised += 1
                assert journal.is_file()
                operation("recover", image, journal, name + "-recover")
                operation("defrag", image, journal, name + "-finish")
            execute(["python3", verifier, "fat16", image])
        assert exercised > 0, "No real source-write interruption was exercised"
        assert digest(module) == digest(installed / "FAT16.so")
    print("FAT16-BOOT-DEFRAGMENTER-ABI-WRITE-RECOVERY-PASS", digest(module))


if __name__ == "__main__":
    main()
