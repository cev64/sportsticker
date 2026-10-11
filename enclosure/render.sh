#!/usr/bin/env bash
# Renders the preview PNGs into renders/. Usage: ./render.sh [extra -D args]
# Needs openscad (and xvfb-run on a headless Linux box).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p renders
RUN=""
if [ -z "${DISPLAY:-}" ] && command -v xvfb-run >/dev/null; then RUN="xvfb-run -a"; fi
png() { # name part camera [size]
  $RUN openscad -o "renders/$1.png" -D "part=\"$2\"" "${@:5}" --camera="$3" \
    --imgsize="${4:-1600,1000}" --colorscheme=Tomorrow --projection="${PROJ:-p}" enclosure.scad >/dev/null 2>&1
  echo "renders/$1.png"
}
EXTRA=("$@")
png front     assembly "0,-620,190,0,25,70"        1600,1000 "${EXTRA[@]}"
png front_3q  assembly "-330,-430,300,0,25,60"     1600,1000 "${EXTRA[@]}"
png back      assembly "260,520,260,0,25,60"       1600,1000 "${EXTRA[@]}"
png back_case case     "0,420,0,0,25,0"            1600,1000 -D show_hardware=false "${EXTRA[@]}"
png back_open case     "0,420,0,0,25,0"            1600,1000 "${EXTRA[@]}"
png exploded  exploded "-520,-430,330,0,40,70"     1600,1000 "${EXTRA[@]}"
PROJ=o png section   section  "400,26,4,0,26,4"           1400,1100 -D show_leds=false "${EXTRA[@]}"
PROJ=o png section2  section2 "400,26,4,0,26,4"           1400,1100 -D show_leds=false "${EXTRA[@]}"
png side      assembly "620,40,90,0,40,60"         1600,1000 "${EXTRA[@]}"
png front_diffuser assembly "-330,-430,300,0,25,60" 1600,1000 -D use_diffuser=true "${EXTRA[@]}"
png two_panel assembly "-420,-620,380,0,25,60"     1600,1000 -D panels=2 "${EXTRA[@]}"
png coupon    coupon   "10,-70,110,20,26,0"        1200,900  "${EXTRA[@]}"
# Both cross-sections side by side.
convert renders/section.png -crop 700x1000+400+60 +repage renders/_s1.png
convert renders/section2.png -crop 700x1000+400+60 +repage renders/_s2.png
convert renders/_s1.png renders/_s2.png +append renders/sections.png
rm -f renders/_s1.png renders/_s2.png
echo renders/sections.png
