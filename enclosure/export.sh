#!/usr/bin/env bash
# Exports one STL per part into stl/, already in print orientation.
# Usage: ./export.sh [extra -D args], e.g. ./export.sh -D panels=2
set -euo pipefail
cd "$(dirname "$0")"
OUT=${OUT:-stl}
mkdir -p "$OUT"
parts="bezel shell stand spacers coupon"
if [[ " $* " == *"panels=2"* ]]; then parts="bezel_left bezel_right shell_left shell_right stand_left stand_right spacers pins"; fi
# The printed snap pins replace every screw unless you build with fasteners="screws".
if [[ " $* " != *'fasteners="screws"'* ]]; then parts="$parts snap_pins"; fi
for p in $parts; do
  ( log=$(openscad -o "$OUT/$p.stl" -D "part=\"$p\"" "$@" enclosure.scad 2>&1)
    vols=$(echo "$log" | grep -oE "Volumes: +[0-9]+" | grep -oE "[0-9]+$" || true)
    python3 -I "$(pwd)/stl_binary.py" "$OUT/$p.stl"
    echo "$OUT/$p.stl  solids: $((${vols:-2} - 1))" ) &
done
wait
