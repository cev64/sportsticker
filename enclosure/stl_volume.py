"""Print the enclosed volume of an STL (ASCII or binary). Used by check.sh."""

import struct
import sys


def triangles(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:5] == b"solid" and b"facet" in data[:400]:
        verts = []
        for line in data.decode(errors="ignore").splitlines():
            parts = line.split()
            if parts and parts[0] == "vertex":
                verts.append(tuple(float(v) for v in parts[1:4]))
        return [verts[i : i + 3] for i in range(0, len(verts) - 2, 3)]
    n = struct.unpack("<I", data[80:84])[0]
    tris = []
    for i in range(n):
        off = 84 + i * 50 + 12
        v = struct.unpack("<9f", data[off : off + 36])
        tris.append([v[0:3], v[3:6], v[6:9]])
    return tris


vol = 0.0
for a, b, c in triangles(sys.argv[1]):
    vol += (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    ) / 6.0
print(f"{abs(vol):.2f}")
