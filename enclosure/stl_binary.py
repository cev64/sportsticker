"""Rewrite ASCII STL files as binary STL in place (about 5x smaller).

Usage: python3 -I stl_binary.py file.stl [...]
"""

import struct
import sys


def convert(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:5] != b"solid" or b"facet" not in data[:400]:
        return
    facets = []
    normal, verts = None, []
    for line in data.decode(errors="ignore").splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "facet":
            normal = tuple(float(v) for v in parts[2:5])
            verts = []
        elif parts[0] == "vertex":
            verts.append(tuple(float(v) for v in parts[1:4]))
        elif parts[0] == "endfacet":
            facets.append((normal, verts))
    with open(path, "wb") as f:
        f.write(b"sportsticker enclosure, binary STL".ljust(80, b" "))
        f.write(struct.pack("<I", len(facets)))
        for n, v in facets:
            f.write(struct.pack("<12fH", *n, *v[0], *v[1], *v[2], 0))


for p in sys.argv[1:]:
    convert(p)
