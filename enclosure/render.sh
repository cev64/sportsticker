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
png coupon    coupon   "28,-95,140,34,20,0"        1200,900  "${EXTRA[@]}"
# Gallery views in renders/views/.
mkdir -p renders/views
png views/01_eye_level_front assembly "0,-520,95,0,30,70"     1600,1100 "${EXTRA[@]}"
png views/02_front_left_3q   assembly "-380,-420,200,0,30,60" 1600,1100 "${EXTRA[@]}"
png views/03_front_right_3q  assembly "380,-420,200,0,30,60"  1600,1100 "${EXTRA[@]}"
PROJ=o png views/04_side_left_ortho assembly "-500,40,60,0,40,60" 1600,1100 "${EXTRA[@]}"
png views/05_top_down        assembly "0,-60,520,0,40,0"      1600,1100 "${EXTRA[@]}"
png views/06_back_left_3q    assembly "-360,480,220,0,30,60"  1600,1100 "${EXTRA[@]}"
png views/07_back_right_3q   assembly "360,480,220,0,30,60"   1600,1100 "${EXTRA[@]}"
png views/08_low_angle       assembly "-260,-380,30,0,30,70"  1600,1100 "${EXTRA[@]}"
png views/09_exploded_side   exploded "-560,-200,260,0,40,60" 1600,1100 "${EXTRA[@]}"
# Both cross-sections side by side.
convert renders/section.png -crop 700x1000+400+60 +repage renders/_s1.png
convert renders/section2.png -crop 700x1000+400+60 +repage renders/_s2.png
convert renders/_s1.png renders/_s2.png +append renders/sections.png
rm -f renders/_s1.png renders/_s2.png
echo renders/sections.png
