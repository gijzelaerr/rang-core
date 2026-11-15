"""Patch a TiledColumnStMan header (twin) to NROWS rows and a data file
LENGTH bytes long. Located by diffing twins of 41, 300 and 1000 rows:
nrrow BE u32 at 0x60, cube last axis BE u32 at 0xF7, file length LE u64 at
0x94 (0x90..0x93 is LE u32 1; a BE u64 at 0x91 fits small lengths too but
puts the high bytes on that field)."""
import sys, struct
src, dst, nrows, length = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
b = bytearray(open(src, "rb").read())
assert b[0x90:0x94] == b"\x01\x00\x00\x00"
b[0x60:0x64] = struct.pack(">I", nrows)
b[0xF7:0xFB] = struct.pack(">I", nrows)
b[0x94:0x9C] = struct.pack("<Q", length)
open(dst, "wb").write(b)
