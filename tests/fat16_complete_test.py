#!/usr/bin/env python3
"""FAT16 V1/V3/V4/V5 tests with independent on-disk geometry/metadata oracles.

Only disposable regular files are used. Sparse files cover the maximum file
size without writing gigabytes. dosfstools/mtools check ordinary images too.
"""
import argparse
import ctypes as C
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import tempfile


class Times(C.Structure):
    _fields_ = [("structure_bytes", C.c_uint32),
                *[(n, C.c_uint16) for n in ("created_date", "created_time",
                  "modified_date", "modified_time", "accessed_date")],
                ("created_10ms", C.c_uint8), ("reserved", C.c_uint8)]


class Metadata(C.Structure):
    _fields_ = [("structure_bytes", C.c_uint32), ("bytes", C.c_uint32),
                ("attributes", C.c_uint8), ("reserved", C.c_uint8 * 3),
                ("times", Times), ("name", C.c_char * 768),
                ("short_name", C.c_char * 37)]


READ = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_uint64, C.c_void_p, C.c_uint32)
WRITE = READ
FLUSH = C.CFUNCTYPE(C.c_int, C.c_void_p)
CLOCK = C.CFUNCTYPE(C.c_uint32, C.c_void_p)


class Io(C.Structure):
    _fields_ = [("user", C.c_void_p), ("partition_bytes", C.c_uint64),
                ("sector_bytes", C.c_uint32), ("read_at", READ),
                ("write_at", WRITE), ("flush", FLUSH), ("fat_timestamp", CLOCK)]


class V3(C.Structure):
    _fields_ = [("version", C.c_uint32), ("size", C.c_uint32),
                ("format", C.c_char_p), ("caps", C.c_uint64)] + [
                    (n, C.c_void_p) for n in ("mount", "unmount", "create", "read",
                    "write", "truncate", "mkdir", "unlink", "rename", "stat",
                    "directory_entry")]


class V4(C.Structure):
    _fields_ = [("version", C.c_uint32), ("size", C.c_uint32),
                ("format", C.c_char_p), ("caps", C.c_uint64),
                ("v3", C.POINTER(V3))] + [(n, C.c_void_p) for n in (
                    "format_volume", "set_attributes", "set_modified_time",
                    "get_modified_time", "space")]


class V5(C.Structure):
    _fields_ = [("version", C.c_uint32), ("size", C.c_uint32),
                ("format", C.c_char_p), ("caps", C.c_uint64),
                ("v4", C.POINTER(V4))] + [(n, C.c_void_p) for n in (
                    "metadata", "set_times", "get_label", "set_label", "set_codepage", "flush")]


class BootIo(C.Structure):
    _fields_ = [("context", C.c_void_p), ("media_bytes", C.c_uint64),
                ("block_bytes", C.c_uint32), ("structure_bytes", C.c_uint32),
                ("read_at", READ)]


class BootV1(C.Structure):
    _fields_ = [("version", C.c_uint32), ("size", C.c_uint32),
                ("format", C.c_char * 16), ("context_bytes", C.c_uint32),
                ("reserved", C.c_uint32)] + [(n, C.c_void_p) for n in (
                    "mount", "unmount", "open", "close", "read", "directory_entry", "volume_label")]


class BootInfo(C.Structure):
    _fields_ = [("bytes", C.c_uint64), ("attributes", C.c_uint32),
                ("reserved", C.c_uint32), ("name", C.c_char * 768)]


def date(y, m, d):
    return ((y - 1980) << 9) | (m << 5) | d


def time(h, m, s):
    return (h << 11) | (m << 5) | (s // 2)


NOW = (date(2026, 10, 29) << 16) | time(12, 34, 56)


def fixture(path, clusters=8192, bps=512, spc=1, fats=2, roots=512):
    """Construct geometry from Microsoft's FAT sections 3.5/4/6, not FatFs."""
    fat_sectors = ((clusters + 2) * 2 + bps - 1) // bps
    root_sectors = (roots * 32 + bps - 1) // bps
    total = 1 + fats * fat_sectors + root_sectors + clusters * spc
    b = bytearray(bps)
    b[:11] = b'\xeb\x3c\x90MSDOS5.0'
    struct.pack_into('<HBHBHHBHHHII', b, 11, bps, spc, 1, fats, roots,
                     total if total < 65536 else 0, 0xf8, fat_sectors, 32, 64,
                     0, total if total >= 65536 else 0)
    b[36], b[38] = 0x80, 0x29
    struct.pack_into('<I', b, 39, 0x12345678)
    b[43:62] = b'NO NAME    FAT16   '
    b[510:512] = b'\x55\xaa'
    with path.open('wb') as f:
        f.truncate(total * bps)
        f.seek(0)
        f.write(b)
        for n in range(fats):
            f.seek((1 + n * fat_sectors) * bps)
            f.write(b'\xf8\xff\xff\xff')
    return dict(bps=bps, spc=spc, fats=fats, fat_sectors=fat_sectors,
                root=(1 + fats * fat_sectors) * bps, roots=roots,
                data=(1 + fats * fat_sectors + root_sectors) * bps,
                clusters=clusters)


def entries(path, g):
    with path.open('rb') as f:
        f.seek(g['root'])
        b = f.read(g['roots'] * 32)
    return [b[i:i+32] for i in range(0, len(b), 32)
            if b[i] not in (0, 0xe5) and b[i+11] != 15]


class Host:
    def __init__(self, path, bps):
        assert path.is_file() and not path.is_symlink()
        self.fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        self.now, self.writes, self.fail_write, self.fail_flush = NOW, 0, False, False
        def read(_, at, out, n):
            try:
                b = os.pread(self.fd, n, at)
                if len(b) != n:
                    return -1
                C.memmove(out, b, n)
                return 0
            except OSError:
                return -1
        def write(_, at, src, n):
            self.writes += 1
            if self.fail_write:
                return -1
            try:
                return 0 if os.pwrite(self.fd, C.string_at(src, n), at) == n else -1
            except OSError:
                return -1
        def flush(_):
            if self.fail_flush:
                return -1
            os.fsync(self.fd)
            return 0
        self.callbacks = READ(read), WRITE(write), FLUSH(flush), CLOCK(lambda _: self.now)
        self.io = Io(None, os.fstat(self.fd).st_size, bps, *self.callbacks)

    def close(self):
        os.close(self.fd)


class Api:
    def __init__(self, module):
        self.lib = C.CDLL(str(module))
        self.lib.infiltrator_filesystem_module_v5.restype = C.POINTER(V5)
        a = self.lib.infiltrator_filesystem_module_v5().contents
        assert a.version == 5 and a.size == C.sizeof(V5) and a.format == b'fat16'
        assert a.caps & (2048 | 4096 | 8192) == (2048 | 4096 | 8192)
        b, c = a.v4.contents, a.v4.contents.v3.contents
        assert b.version == 4 and b.size == C.sizeof(V4)
        assert c.version == 3 and c.size == C.sizeof(V3)
        def bind(owner, name, *args):
            setattr(self, name, C.CFUNCTYPE(C.c_int, *args)(getattr(owner, name)))
        for n in ('create', 'mkdir', 'unlink'):
            bind(c, n, C.c_char_p)
        bind(c, 'mount', C.POINTER(Io))
        bind(c, 'unmount')
        bind(c, 'rename', C.c_char_p, C.c_char_p)
        bind(c, 'truncate', C.c_char_p, C.c_uint32)
        for n in ('read', 'write'):
            bind(c, n, C.c_char_p, C.c_uint32, C.c_void_p, C.c_uint32)
        bind(b, 'set_attributes', C.c_char_p, C.c_uint8, C.c_uint8)
        bind(b, 'set_modified_time', C.c_char_p, C.c_uint16, C.c_uint16)
        bind(b, 'format_volume', C.POINTER(Io), C.c_uint32)
        bind(a, 'metadata', C.c_char_p, C.POINTER(Metadata))
        bind(a, 'set_times', C.c_char_p, C.POINTER(Times), C.c_uint32)
        bind(a, 'get_label', C.c_void_p, C.c_uint32, C.POINTER(C.c_uint32))
        bind(a, 'set_label', C.c_char_p)
        bind(a, 'set_codepage', C.c_uint16)
        bind(a, 'flush')

    def meta(self, path):
        m = Metadata()
        assert self.metadata(path, C.byref(m)) == 0, path
        assert m.structure_bytes == C.sizeof(m)
        assert m.times.structure_bytes == C.sizeof(Times)
        return m

    def label(self):
        b, serial = C.create_string_buffer(34), C.c_uint32()
        assert self.get_label(b, len(b), C.byref(serial)) == 0
        return b.value, serial.value


def metadata_test(api, work):
    p = work / 'metadata.img'
    subprocess.run(['mkfs.fat', '-F', '16', '-C', str(p), '32768'], check=True,
                   stdout=subprocess.DEVNULL)
    with p.open('rb') as f:
        b = f.read(512)
    bps, fats, fs, roots = struct.unpack_from('<H', b, 11)[0], b[16], struct.unpack_from('<H', b, 22)[0], struct.unpack_from('<H', b, 17)[0]
    g = dict(root=(struct.unpack_from('<H', b, 14)[0] + fats * fs) * bps, roots=roots)
    host = Host(p, bps)
    assert api.mount(C.byref(host.io)) == 0
    assert api.label()[1] == struct.unpack_from('<I', b, 39)[0]
    assert api.set_codepage(850) != 0
    name = b'0:/STAMP.TXT'
    assert api.create(name) == 0
    m = api.meta(name)
    assert m.times.created_date == m.times.accessed_date == NOW >> 16
    assert m.times.created_time == NOW & 0xffff
    t = Times(C.sizeof(Times), date(2000, 2, 29), time(23, 59, 58),
              date(2107, 12, 31), time(1, 2, 4), date(1980, 1, 1), 199, 0)
    assert api.set_times(name, C.byref(t), 7) == 0
    raw = next(e for e in entries(p, g) if e[:11] == b'STAMP   TXT')
    assert raw[13] == 199 and struct.unpack_from('<HHH', raw, 14) == (
        t.created_time, t.created_date, t.accessed_date)
    assert struct.unpack_from('<HH', raw, 22) == (t.modified_time, t.modified_date)
    assert api.set_modified_time(name, date(2024, 2, 29), time(3, 4, 6)) == 0
    m = api.meta(name)
    assert m.times.created_10ms == 199 and m.times.created_date == t.created_date
    assert m.times.accessed_date == t.accessed_date
    before = hashlib.sha256(p.read_bytes()).digest()
    invalid = [(date(2100, 2, 29), 0, 0), (date(2026, 13, 1), 0, 0),
               (date(2026, 1, 0), 0, 0), (date(2026, 1, 1), 24 << 11, 0),
               (date(2026, 1, 1), 60 << 5, 0), (date(2026, 1, 1), 30, 0),
               (date(2026, 1, 1), 0, 200)]
    for d, clock, fraction in invalid:
        bad = Times(C.sizeof(Times), d, clock, 0, 0, 0, fraction, 0)
        assert api.set_times(name, C.byref(bad), 1) != 0
    assert api.set_times(name, C.byref(t), 8) != 0
    assert api.set_times(name, C.byref(t), 0) != 0
    for bad_path in (b'0:/CUT\nOFF', b'0:/CUT/\n', b'0:/CUT\x01', b'0:/\n'):
        assert api.create(bad_path) != 0
        assert api.mkdir(bad_path) != 0
    assert hashlib.sha256(p.read_bytes()).digest() == before
    assert api.write(name, 0, b'abc', 3) == 0
    m = api.meta(name)
    assert m.times.created_10ms == 199 and m.times.created_date == t.created_date
    assert m.times.modified_date == m.times.accessed_date == NOW >> 16
    host.now = (date(2027, 1, 2) << 16) | time(1, 0, 0)
    out = C.create_string_buffer(3)
    assert api.read(name, 0, out, 3) == 0 and out.raw == b'abc'
    assert api.meta(name).times.accessed_date == date(2027, 1, 2)
    assert api.set_attributes(name, 0x27, 0x27) == 0
    assert api.write(name, 0, b'X', 1) != 0 and api.unlink(name) != 0
    assert api.set_attributes(name, 0x20, 0x27) == 0
    assert api.rename(name, b'0:/Renamed timestamp.txt') == 0
    assert api.meta(b'0:/Renamed timestamp.txt').times.created_10ms == 199
    assert api.mkdir(b'0:/DATES') == 0
    clear = Times(C.sizeof(Times), 0, 0, 0, 0, 0, 0, 0)
    assert api.set_times(b'0:/DATES', C.byref(clear), 5) == 0
    m = api.meta(b'0:/DATES')
    assert not m.times.created_date and not m.times.accessed_date
    assert m.attributes & 0x10
    assert api.unlink(b'0:/DATES') == 0
    unicode_name = '0:/' + '😀' * 90 + '中' * 75
    encoded_name = unicode_name.encode()
    assert api.create(encoded_name) == 0
    assert api.meta(encoded_name).name.decode() == unicode_name[3:]
    assert api.create((unicode_name + 'X').encode()) != 0
    assert api.create(b'0:/BAD\xffUTF8') != 0
    assert api.unlink(encoded_name) == 0
    assert api.set_label(b'fat16 ready') == 0
    assert api.label()[0] == b'FAT16 READY'
    assert p.read_bytes()[43:54] == b'FAT16 READY'
    for invalid_label in (b'TOOLONG-LABEL', b'BAD:LABEL', b'BAD/LABEL', b'BAD\\LABEL', b'BAD\nLABEL', b'BAD?LABEL'):
        assert api.set_label(invalid_label) != 0
        assert api.label()[0] == b'FAT16 READY'
    assert api.get_label(C.create_string_buffer(2), 2, None) != 0
    assert api.set_label(b'') == 0 and api.label()[0] == b''
    assert p.read_bytes()[43:54] == b'NO NAME    '
    assert api.set_label(b'FINISHED') == 0
    host.fail_flush = True
    assert api.flush() != 0
    host.fail_flush = False
    assert api.flush() == 0 and api.unmount() == 0
    assert api.mount(C.byref(host.io)) == 0
    assert api.meta(b'0:/Renamed timestamp.txt').times.created_10ms == 199
    assert api.label()[0] == b'FINISHED'
    assert api.unmount() == 0
    host.close()
    subprocess.run(['fsck.fat', '-n', str(p)], check=True)
    subprocess.run(['mdir', '-i', str(p), '::'], check=True, stdout=subprocess.DEVNULL)


def geometry_test(api, work):
    for count in (4084, 4085, 4086, 4087, 65518, 65524, 65525):
        p = work / f'count-{count}.img'
        g = fixture(p, count)
        h = Host(p, 512)
        r = api.mount(C.byref(h.io))
        assert (r == 0) == (4085 <= count < 65525), count
        if r == 0:
            assert api.create(b'0:/BOUND.TXT') == 0
            assert api.write(b'0:/BOUND.TXT', 0, b'boundary', 8) == 0
            assert api.unmount() == 0
        else:
            assert h.writes == 0
        h.close()
        p.unlink()
    for bps in (512, 1024, 2048, 4096):
        for spc in (1, 2, 64, 128):
            for fats in (1, 2):
                p = work / 'geometry.img'
                g = fixture(p, 4087, bps, spc, fats, bps // 32)
                h = Host(p, bps)
                assert api.mount(C.byref(h.io)) == 0, (bps, spc, fats)
                assert api.create(b'0:/FILE.BIN') == 0
                data = bytes((i * 37 + 9) & 255 for i in range(bps * 2 + 17))
                assert api.write(b'0:/FILE.BIN', 0, data, len(data)) == 0
                out = C.create_string_buffer(len(data))
                assert api.read(b'0:/FILE.BIN', 0, out, len(data)) == 0 and out.raw == data
                assert api.unmount() == 0
                with p.open('rb') as f:
                    copies = []
                    for n in range(fats):
                        f.seek((1 + n * g['fat_sectors']) * bps)
                        copies.append(f.read(g['fat_sectors'] * bps))
                assert all(x == copies[0] for x in copies)
                h.close()
                p.unlink()
    # The fixed root must fail cleanly when every slot is occupied.
    p = work / 'root-full.img'
    fixture(p, roots=16)
    h = Host(p, 512)
    assert api.mount(C.byref(h.io)) == 0
    for i in range(16):
        assert api.create(f'0:/F{i:07d}'.encode()) == 0
    assert api.create(b'0:/EXTRA') != 0
    assert api.unlink(b'0:/F0000000') == 0 and api.create(b'0:/REUSED') == 0
    assert api.unmount() == 0
    h.close()

    # A bad cluster is not free space; normal writes preserve FAT status bits.
    for status in (0x3fff, 0x7fff, 0xbfff, 0xffff):
        p = work / 'bad-status.img'
        g = fixture(p)
        with p.open('r+b') as f:
            for copy in range(2):
                f.seek((1 + copy * g['fat_sectors']) * 512 + 2)
                f.write(struct.pack('<HH', status, 0xfff7))
        h = Host(p, 512)
        assert api.mount(C.byref(h.io)) == 0
        assert api.create(b'0:/SAFE.BIN') == 0
        assert api.write(b'0:/SAFE.BIN', 0, b'S' * 1024, 1024) == 0
        e = entries(p, g)[0]
        assert struct.unpack_from('<H', e, 26)[0] > 2
        assert api.unlink(b'0:/SAFE.BIN') == 0
        assert api.unmount() == 0
        with p.open('rb') as f:
            for copy in range(2):
                f.seek((1 + copy * g['fat_sectors']) * 512 + 2)
                assert struct.unpack('<HH', f.read(4)) == (status, 0xfff7)
        h.close()

    # Failed media writes are propagated, without substituting success.
    p = work / 'failed-write.img'
    fixture(p)
    h = Host(p, 512)
    assert api.mount(C.byref(h.io)) == 0
    h.fail_write = True
    assert api.create(b'0:/FAIL.TXT') != 0
    h.fail_write = False
    assert api.unmount() == 0
    h.close()


def codepage_test(api, work):
    for cp, codec, leaf in ((437, 'cp437', 'Ü.TXT'), (850, 'cp850', 'Ø.TXT'),
                            (932, 'cp932', '日本.TXT'), (936, 'gbk', '中文.TXT'),
                            (949, 'cp949', '한글.TXT'), (950, 'cp950', '中文.TXT')):
        assert api.set_codepage(cp) == 0
        p = work / f'cp{cp}.img'
        g = fixture(p)
        # Supply a foreign OEM short name directly. FatFs may deliberately
        # transliterate its own generated aliases, which is also valid FAT.
        stem, ext = leaf.rsplit('.', 1)
        raw_name = stem.encode(codec).ljust(8, b' ') + ext.encode().ljust(3, b' ')
        with p.open('r+b') as f:
            f.seek(g['root'])
            f.write(raw_name + b'\x20' + bytes(20))
        h = Host(p, 512)
        assert api.mount(C.byref(h.io)) == 0
        name = ('0:/' + leaf).encode()
        assert api.meta(name).short_name.decode() == leaf, (cp, api.meta(name).short_name, leaf)
        raw = entries(p, g)[0]
        stem = raw[:8].rstrip(b' ').decode(codec)
        assert stem == leaf[:-4], (cp, stem)
        long_name = ('0:/Long ' + leaf).encode()
        assert api.create(long_name) == 0
        assert api.meta(long_name).name.decode() == 'Long ' + leaf
        assert api.unmount() == 0
        h.close()
    assert api.set_codepage(0) != 0 and api.set_codepage(1234) != 0
    assert api.set_codepage(437) == 0


def maximum_file_test(api, work):
    p = work / 'max-file.img'
    g = fixture(p, clusters=40000, bps=4096, spc=32)
    cluster_bytes = g['bps'] * g['spc']
    count = (0xffffffff + cluster_bytes - 1) // cluster_bytes
    with p.open('r+b') as f:
        table = bytearray(g['fat_sectors'] * g['bps'])
        table[:4] = b'\xf8\xff\xff\xff'
        for c in range(2, count + 2):
            struct.pack_into('<H', table, c * 2, c + 1 if c < count + 1 else 0xffff)
        for n in range(2):
            f.seek((1 + n * g['fat_sectors']) * g['bps'])
            f.write(table)
        e = bytearray(32)
        e[:11], e[11] = b'MAXIMUM BIN', 0x20
        struct.pack_into('<HI', e, 26, 2, 0xffffffff)
        f.seek(g['root'])
        f.write(e)
    h = Host(p, 4096)
    assert api.mount(C.byref(h.io)) == 0
    assert api.meta(b'0:/MAXIMUM.BIN').bytes == 0xffffffff
    assert api.write(b'0:/MAXIMUM.BIN', 0xfffffffe, b'OK', 2) != 0
    assert h.writes == 0
    assert api.write(b'0:/MAXIMUM.BIN', 0xfffffffe, b'Z', 1) == 0
    out = C.create_string_buffer(1)
    assert api.read(b'0:/MAXIMUM.BIN', 0xfffffffe, out, 1) == 0 and out.raw == b'Z'
    assert api.read(b'0:/MAXIMUM.BIN', 0xffffffff, out, 1) != 0
    assert api.read(b'0:/MAXIMUM.BIN', 0xffffffff, out, 0) == 0
    assert api.unmount() == 0
    h.close()


def boot_geometry_test(api, work):
    api.lib.infiltrator_filesystem_boot_v1.restype = C.POINTER(BootV1)
    b = api.lib.infiltrator_filesystem_boot_v1().contents
    assert b.version == 1 and b.size == C.sizeof(BootV1)
    mount = C.CFUNCTYPE(C.c_int, C.POINTER(BootIo))(b.mount)
    unmount = C.CFUNCTYPE(C.c_int)(b.unmount)
    open_file = C.CFUNCTYPE(C.c_int, C.c_char_p, C.c_void_p, C.POINTER(BootInfo))(b.open)
    close_file = C.CFUNCTYPE(C.c_int, C.c_void_p)(b.close)
    read_file = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_uint64, C.c_void_p, C.c_uint32, C.POINTER(C.c_uint32))(b.read)
    for sector in (512, 1024, 2048, 4096):
        p = work / 'boot-sector.img'
        fixture(p, clusters=4087, bps=sector)
        h = Host(p, sector)
        assert api.mount(C.byref(h.io)) == 0
        assert api.create(b'0:/KERNEL.BIN') == 0
        assert api.write(b'0:/KERNEL.BIN', 0, b'boot geometry', 13) == 0
        assert api.unmount() == 0
        writes = h.writes
        before = hashlib.sha256(p.read_bytes()).digest()
        for block in (512, 4096):
            io = BootIo(None, h.io.partition_bytes, block, C.sizeof(BootIo), h.callbacks[0])
            assert mount(C.byref(io)) == 0, (sector, block)
            context = (C.c_uint64 * ((b.context_bytes + 7) // 8))()
            info, got, out = BootInfo(), C.c_uint32(), C.create_string_buffer(13)
            assert open_file(b'/KERNEL.BIN', context, C.byref(info)) == 0
            assert info.bytes == 13
            assert read_file(context, 0, out, 13, C.byref(got)) == 0
            assert got.value == 13 and out.raw == b'boot geometry'
            assert close_file(context) == 0 and unmount() == 0
        assert h.writes == writes and hashlib.sha256(p.read_bytes()).digest() == before
        h.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', type=Path, required=True)
    args = parser.parse_args()
    api = Api(args.module.resolve())
    with tempfile.TemporaryDirectory(prefix='fat16-complete-') as tmp:
        work = Path(tmp)
        metadata_test(api, work)
        geometry_test(api, work)
        codepage_test(api, work)
        maximum_file_test(api, work)
        boot_geometry_test(api, work)
    print('FAT16-V5-METADATA-LABEL-CODEPAGE-GEOMETRY-MAXFILE-PASS')


if __name__ == '__main__':
    main()
