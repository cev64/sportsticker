#!/usr/bin/env bash
# Collision checks: renders the overlap of each pair with CGAL.
# "empty" means the two never touch. Usage: ./check.sh [extra -D args]
cd "$(dirname "$0")"
OUT=$(mktemp -d)
checks="shell_pi shell_panel bezel_panel pi_panel shell_plugs plugs_rest shell_ribbon ribbon_panel ribbon_pi bezel_shell shell_lead clips_hw lead_ribbon stand_case"
for c in $checks; do
  ( log=$(openscad -o "$OUT/$c.stl" -D "part=\"check_$c\"" -D show_leds=false "$@" enclosure.scad 2>&1)
    if echo "$log" | grep -q "top level object is empty"; then r="empty (no collision)";
    elif echo "$log" | grep -qi "error"; then r="ERROR: $(echo "$log" | grep -i error | head -2)";
    else vol=$(python3 -I "$(pwd)/stl_volume.py" "$OUT/$c.stl"); r="OVERLAP volume ${vol} mm3"; fi
    echo "check_$c: $r" ) &
done
wait
rm -rf "$OUT"
