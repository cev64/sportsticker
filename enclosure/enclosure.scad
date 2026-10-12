// =============================================================================
//  enclosure.scad : 3D-printable enclosure for the sportsticker
//  Adafruit 64x32 P3 LED matrix (#2279) + Raspberry Pi 4 + RGB Matrix Bonnet
// =============================================================================
//
//  Coordinates (all mm):
//    X = right, as seen from the FRONT of the ticker. X = 0 is the panel centre.
//    Y = depth. Y = 0 is the bezel's front face; +Y points toward the back.
//    Z = up. Z = 0 is the panel centre.
//
//  Every dimension that comes from a part is a named parameter below. Values
//  marked UNVERIFIED could not be read from an official drawing; measure them
//  with calipers when the parts arrive (enclosure/README.md says how) and edit
//  them here before printing.
//
//  Command line: openscad -o out.stl -D 'part="shell"' enclosure.scad
//  Printable parts (already in print orientation): bezel shell stand spacers
//  snap_pins coupon pins, and bezel_left/_right, shell_left/_right, stand_left/_right
//  for the 2-panel build. Views: assembly (on the stand), exploded, case (no
//  stand), stand_slide, section, section2, hardware. Collision checks: check_* at the end.
//  Scripts: export.sh (STLs), render.sh (PNGs), check.sh (collisions).

/* [What to render] */
part = "assembly";

// Show the LED panel, Pi, bonnet, plugs and cables in the views.
show_hardware = true;
// Distance the parts move apart in the "exploded" view.
explode = 45;
// Draw every LED in the views (turned off for the collision checks).
show_leds = true;

/* [Build options] */
// Number of 64x32 panels side by side: 1, or 2 for a future 128x32 ticker.
panels = 1;
// Pocket in the bezel for a tinted acrylic diffuser sheet.
use_diffuser = false;
// Diffuser sheet thickness (2 or 3 mm acrylic).
diffuser_t = 3.0;
// How far the sheet extends under the bezel border on each side.
diffuser_overlap = 2.0;
// Desk stand part. The stand is a separate part that screws to the shell.
desk_stand = true;
// Back tilt of the desk stand, degrees from vertical.
stand_tilt = 6;
// Keyhole slots in the back wall for hanging on two screws.
wall_mount = false;

/* [Fastening] */
// "printed": no screws or nuts at all. Printed snap pins hold the panel and
// the Pi, and the stand slides onto dovetails. "screws": the M3 / M2.5 build.
fasteners = "printed";

/* [Printer and fit] */
// Usable bed. Bambu P1/X1/A1 = 256 x 256; Prusa MK4 = 250 x 210.
bed_x = 250;
bed_y = 210;
// Clearance around the panel and the boards (per side).
fit_clear = 0.3;
// Clearance for pins, pegs and sliding joints (per side).
pin_clear = 0.2;
// Minimum wall thickness for anything structural.
min_wall = 1.6;

/* [Enclosure walls] */
// Side, top and bottom walls of the bezel and shell.
wall = 2.0;
// Bezel front plate thickness.
front_t = 2.0;
// Shell back wall thickness.
back_t = 2.0;
// Requested overlap of the bezel over the panel edge. See bezel_hides_leds.
bezel_lip = 1.5;
// false: the opening is never smaller than the LED area (no pixel hidden);
// the lip is clamped to what the panel allows. true: use bezel_lip as given.
bezel_hides_leds = false;
// Gap between the bezel front plate and the LED face (absorbs panel_t error).
front_gap = 0.3;
// How far the bezel walls continue past the panel's back face. The last part
// is a ~51 degree ledge that joins the walls to the tongue (prints unsupported).
joint_overlap = 2.6;
// Tongue on the bezel that slides inside the shell walls.
tongue_len = 8.0;
tongue_t = 1.6;
// Snap-fit bump height, length along the wall, and flexing finger width.
snap_h = 0.6;
snap_len = 8.0;
snap_finger_w = 12.0;
snap_slit = 1.2;
// Snap positions along the top and bottom walls, from each panel's centre.
snap_x = [-55, 55];

/* [LED panel: Adafruit #2279, 64x32, 3 mm pitch] */
// Outline width. Adafruit page 191, CAD 191.8, datasheet 192. UNVERIFIED.
panel_w = 192.0;
// Outline height. CAD 95.8, Adafruit and datasheet 96. UNVERIFIED.
panel_h = 96.0;
// LED front face to the flat back mounting face. Adafruit lists 15; the CAD
// side view shows a 10 mm body (+2.7 mm pins). UNVERIFIED: measure.
panel_t = 15.0;
// Pixel pitch and grid (product page and datasheet).
pitch = 3.0;
cols = 64;
rows = 32;
// SMD2121 LED body size, used to keep every pixel visible.
led_size = 2.1;
// M3 mounting points used, [X, Z] from the panel centre, seen from the front.
// CAD magenta holes "30" / "87" (the pattern is symmetric). UNVERIFIED: the
// vendor photo of another batch shows inserts at about [+-78, +-38].
panel_mounts = [[87, 30], [-87, 30], [87, -30], [-87, -30]];
// Depth of thread in the panel's M3 inserts. UNVERIFIED.
panel_insert_depth = 5.0;
// Locating pins on the panel back (CAD "15"/"88", 2.7 tall). Diameter UNVERIFIED.
panel_pins = [[88, 15], [-88, -15]];
panel_pin_h = 2.7;
panel_pin_d = 2.0;
// 16-pin IDC connectors, centred at X = +-panel_idc_x (vendor photo). UNVERIFIED.
panel_idc_x = 74;
panel_idc_size = [9, 26];
// How far the IDC plug + ribbon stands proud of the back face. UNVERIFIED.
panel_idc_proud = 9.0;
// Which side the INPUT connector is on, seen from the FRONT: +1 right, -1 left.
// UNVERIFIED. If yours is on the other side, rotate the panel 180 degrees and
// set pixel_mapper_config: "Rotate:180" in config.yaml (no reprint needed).
panel_input_side = 1;
// Power connector at the panel centre (vendor photo) and how far its plug
// and wires stand proud of the back face. UNVERIFIED.
panel_pwr_size = [15, 7];
panel_pwr_proud = 12.0;

/* [Raspberry Pi 4 Model B: official mechanical drawing] */
pi_w = 85;
pi_h = 56;
pi_corner_r = 3.0;
// PCB thickness: not on the drawing; 1.4 is often quoted. UNVERIFIED.
pi_pcb_t = 1.6;
// Mounting holes [x, y] from the board's bottom-left corner (top view).
pi_holes = [[3.5, 3.5], [61.5, 3.5], [3.5, 52.5], [61.5, 52.5]];
pi_hole_d = 2.7;
pi_pad_d = 6.0;
// USB-C power: bottom edge, centre x, body width/height, overhang past edge.
pi_usbc_x = 11.2;
pi_usbc_size = [9.0, 3.2];
pi_usbc_overhang = 1.2;
// micro-HDMI centres (unused, modelled for collision checks).
pi_hdmi_x = [26.0, 39.5];
// Audio jack centre x, width, height, overhang.
pi_audio = [54.0, 7.0, 6.0, 2.5];
// USB-A and Ethernet on the right edge: [centre y, width, height].
pi_usba = [[9.0, 13.2, 16.0], [27.0, 13.2, 16.0], [45.75, 15.5, 13.5]];
pi_right_overhang = 3.0;
pi_right_depth = 21.0;
// 40-pin GPIO header: centre and height. Plastic base height of the header.
pi_gpio_c = [32.5, 52.5];
pi_gpio_h = 8.5;
pi_gpio_base_h = 2.5;
// microSD slot: left edge, underside, centre y. Not on the drawing. UNVERIFIED.
pi_sd_y = 28.0;
// How far a seated card sticks out past the board edge. UNVERIFIED.
pi_sd_proud = 2.5;
pi_sd_w = 11.0;
// Space under the Pi for the SD socket and through-hole pins (standoff height).
pi_underside = 3.0;

/* [RGB Matrix Bonnet #3211: Eagle board file + fab print] */
bonnet_w = 65.0;
bonnet_h = 30.66;
bonnet_chamfer = 3.0;
// The bonnet's y = 0 sits at Pi y = 26 (its header lines up with the Pi's).
bonnet_y0 = 26.0;
// Bonnet underside above the Pi PCB top: 2.5 male header plastic + 8.5 female
// header. UNVERIFIED (depends on how far the header seats).
bonnet_gap = 11.0;
bonnet_pcb_t = 1.6;
// Barrel jack body box in bonnet coords [x0, x1, y0, y1], height, and the
// barrel's axis height above the bonnet PCB. Height and axis UNVERIFIED.
bonnet_jack = [-1.27, 12.93, 7.95, 16.95];
bonnet_jack_h = 11.0;
bonnet_jack_axis = 6.5;
// 2-pin 5.08 mm screw terminal box and height (product page: 11.5 mm on the
// Sept 2025 revision; Jan 2023 to Sept 2025 boards may have a taller block). UNVERIFIED.
bonnet_term = [15.24, 27.94, 0.51, 9.40];
bonnet_term_h = 11.5;
// HUB75 2x8 shrouded socket box and height (height UNVERIFIED).
bonnet_hub = [30.07, 58.07, 0.58, 9.58];
bonnet_hub_h = 9.0;
// The ribbon's IDC plug stands above the shroud by this much, plus ribbon. UNVERIFIED.
idc_plug_proud = 3.0;
ribbon_t = 1.0;
ribbon_w = 20.3;
// Length of your 16-pin ribbon between the two plugs. UNVERIFIED: measure.
ribbon_len = 150;
// Bend radius of the soft U-turn that takes up spare ribbon (never creased).
ribbon_bend_r = 5.0;
// "auto" picks "direct" for short ribbons and "u" (U-turn below the Pi) for long ones.
ribbon_route = "auto";

/* [Cables and plugs: UNVERIFIED, measure yours] */
// 5.5/2.1 barrel plug: body diameter, length from the jack face to the end
// of the strain relief, cable diameter.
barrel_plug_d = 10.5;
barrel_plug_len = 32;
barrel_cable_d = 3.5;
// USB-C plug overmould [width, thickness], length including the boot, cable diameter.
usbc_plug_size = [12.5, 6.8];
usbc_plug_len = 28;
usbc_cable_d = 4.0;
// Panel power lead (red/black): single wire outer diameter.
pwr_wire_d = 2.2;

/* [Layout inside the shell] */
// Pi bottom-left corner in the enclosure, [X, Z], relative to panel 1's centre.
// The Pi sits with its components facing the panel.
pi_pos = [-24, -11.5];
// Clearance between the tallest part of the Pi stack and the panel back.
stack_clear = 2.0;
// Left edge of the rear access bay (window in the back wall), relative to panel 1.
bay_left = -80;
// Bottom edge of the bay window, and its right edge below the Pi.
bay_bottom = -44;
bay_low_right = -3.5;
// Snap-in clip for the panel power lead [X, Z] relative to panel 1's centre.
pwr_clip_pos = [3, -20];

/* [Hardware] */
// Panel: M3 pan head, through the post floor into the panel insert.
post_floor = 3.0;
post_d = 10.4;
post_top_d = 8.0;
m3_clear_d = 3.4;
m3_head_well_d = 7.0;
m3_nut_af = 5.5;
m3_nut_t = 2.4;
// Pi: M2.5 thread-forming (self-tapping) screws into printed holes.
m25_tap_d = 2.2;
m25_clear_d = 2.9;
pi_standoff_d = 6.0;
// Spacer between Pi and bonnet on the two shared holes.
spacer_od = 5.5;

/* [Printed snap pins (fasteners = "printed")] */
// Every pin prints lying on a flat (thickness = pin_flat x shank), split in
// the bed plane so its two prongs flex sideways along the layers.
pin_flat = 0.75;
// Heads are [diameter, thickness, bar]: a disc with a flat, plus a bar of
// that length across the split, so the head covers the hole on every side.
// Pi + bonnet pins, pushed in from the front: shank, barb, slit, head.
// The barb squeezes through the Pi's 2.7 mm hole (the bonnet's are 2.8) and
// snaps into a pocket in the back of the shell, catching on a step 0.4 mm
// up the standoff bore. Print these in PETG: the short pin's prongs bend ~2%.
pi_pin_d = 2.4;
pi_pin_barb = 3.2;
pi_pin_slit = 0.9;
pi_pin_head = [4.5, 1.6, 6.0];  // the bar fits the Pi's 6 mm pad
pi_pin_bore = 2.75;             // standoff bore
pi_pin_pocket = 5.6;            // barb pocket in the back wall (tweezers fit here)
// Panel pins, pushed down the screwdriver wells. A thin neck makes the split
// end a long, soft spring; its bulge springs into the panel's M3 insert
// (thread minor diameter 2.46 to 2.60) and sits in the thread. A stem up the
// well lets you push the pin in and pull it back out.
insert_pin_d = 2.3;             // neck
insert_pin_bulge = 2.8;
insert_pin_slit = 1.0;
insert_pin_grip = 4.0;          // length inside the insert (keep < panel_insert_depth)
insert_pin_head = [6.0, 1.6, 6.6];
// Joint pin for the split shell (2-panel build): barb snaps into the nut trap
// with a square catch, so the joint stays shut when you carry the ticker.
joint_pin_d = 3.0;
joint_pin_barb = 4.2;
joint_pin_slit = 1.0;
joint_pin_head = [6.0, 2.0, 6.0];
// Stand dovetails: a tongue on each stand pad slides into a groove in the
// shell's bottom from the back. Neck width at the case's bottom face, height,
// flank angle from vertical, groove length from the back face.
dt_w = 8.0;
dt_h = 4.5;
dt_angle = 25;
dt_len = 18;
// The last few mm of each tongue are this much wider per side than the
// groove: a friction wedge that keeps the stand on when you carry the ticker.
dt_lock = 0.1;

/* [Desk stand] */
stand_w = panels == 1 ? 170 : 330;
stand_d = 100;
stand_base_t = 4.0;
// Gap under the lowest (back) edge of the case, room for the USB-C cable bend.
stand_clear = 12.0;
// Stand pads and screw positions, X from the case centre.
stand_pad_x = panels == 1 ? 50 : 140;
stand_pad_w = 36;
// Stand screw position, measured forward from the shell's back face.
stand_screw_from_back = 14;
// Material left under the case at each screw (counterbore from below).
stand_screw_floor = 4.0;
// Rear notch for the cables, [X centre, width, depth].
stand_cable_notch = [-45, 40, 10];

/* [Hidden] */
$fa = 6;
$fs = 0.4;
eps = 0.01;

// =============================================================================
//  Derived dimensions
// =============================================================================

total_panel_w = panels * panel_w;
// Panel module centres along X.
module_x = [for (i = [0 : panels - 1]) (i - (panels - 1) / 2) * panel_w];
mx0 = module_x[0];

sheet_w = total_panel_w + 2 * diffuser_overlap;
sheet_h = panel_h + 2 * diffuser_overlap;
cav_w = max(total_panel_w, use_diffuser ? sheet_w : 0) + 2 * fit_clear;
cav_h = max(panel_h, use_diffuser ? sheet_h : 0) + 2 * fit_clear;
cav_r = 0.8;
out_w = cav_w + 2 * wall;
out_h = cav_h + 2 * wall;
out_r = cav_r + wall;

// LED area and the bezel opening.
led_ext_w = (cols * panels - 1) * pitch + led_size;
led_ext_h = (rows - 1) * pitch + led_size;
open_w = bezel_hides_leds ? total_panel_w - 2 * bezel_lip : led_ext_w + 2 * fit_clear;
open_h = bezel_hides_leds ? panel_h - 2 * bezel_lip : led_ext_h + 2 * fit_clear;
lip_eff = (total_panel_w - open_w) / 2;
open_chamfer = front_t - 0.6;

// Pi stack heights above the Pi PCB top surface.
bonnet_top_h = bonnet_gap + bonnet_pcb_t;
plug_top_h = bonnet_top_h + bonnet_hub_h + idc_plug_proud + ribbon_t;
stack_h = max(bonnet_top_h + max(bonnet_jack_h, bonnet_term_h), plug_top_h,
              max([for (u = pi_usba) u[2]]));

// Depth stations along Y.
y_sheet = front_t;
y_panel_front = front_t + (use_diffuser ? diffuser_t + 0.2 : 0) + front_gap;
y_panel_back = y_panel_front + panel_t;
y_joint = y_panel_back + joint_overlap;
y_stack_top = y_panel_back + stack_clear;
y_pi_top = y_stack_top + stack_h;
y_pi_bot = y_pi_top + pi_pcb_t;
y_back_in = y_pi_bot + pi_underside;
depth = y_back_in + back_t;
y_bonnet_top = y_pi_top - bonnet_top_h;
y_tongue_end = y_joint + tongue_len;
y_snap_catch = y_tongue_end - 3.0;

// Pi and bonnet board coordinates -> enclosure [X, Z].
function P(p) = [mx0 + pi_pos[0] + p[0], pi_pos[1] + p[1]];
function B(p) = P([p[0], p[1] + bonnet_y0]);

usbc_xz = P([pi_usbc_x, 0]);
usbc_y = y_pi_top - pi_usbc_size[1] / 2;
jack_face_x = B([bonnet_jack[0], 0])[0];
jack_z = B([0, (bonnet_jack[2] + bonnet_jack[3]) / 2])[1];
jack_y = y_bonnet_top - bonnet_jack_axis;
sd_z = P([0, pi_sd_y])[1];
barrel_clip_xz = [mx0 + bay_left + 3.0, jack_z];

// Screws.
panel_screw_len = post_floor + panel_insert_depth;
pi_screw_short = pi_pcb_t + pi_underside + back_t;
pi_screw_long = bonnet_pcb_t + bonnet_gap + pi_pcb_t + pi_underside + back_t;
stand_screw_len = stand_screw_floor + wall + 6;

// Printed snap pins: length from the head's underside to the ledge the barb
// catches on. The Pi pins catch on the end of the standoff, in a pocket in
// the back wall; the panel pins grip inside the insert past the post floor.
screwless = fasteners == "printed";
pi_pin_short = pi_pcb_t + pi_underside - 0.4;
pi_pin_long = bonnet_top_h + pi_pcb_t + pi_underside - 0.4;
// The Pi pin's catch face slopes over [S - 0.5, S + 0.2]. It meets the bore
// edge about 0.2 mm before S, so it clamps any stack from S - 0.2 to S + 0.2:
// a 1.4 or a 1.6 mm Pi PCB, or a header that seats 0.2 mm off.
pi_pin_catch = [-0.5, 0.2];
// Panel pin stem: from the head up the well to 4 mm below the back face.
insert_pin_stem = depth - (y_panel_back + post_floor) - insert_pin_head[1] - 4;
joint_pin_len = 14;   // split block: head recess floor to nut trap floor

// Stand dovetail: groove top (Z) and how far each flank leans out.
dt_top = -out_h / 2 + dt_h;
dt_spread = dt_h * tan(dt_angle);

needs_split = out_w > bed_x - 5 || out_h > bed_y - 5;

echo(str("REPORT outer W x H x D = ", out_w, " x ", out_h, " x ", depth, " mm"));
echo(str("REPORT Pi stack above Pi PCB = ", stack_h, "; full stack incl. PCB and standoff = ",
         stack_h + pi_pcb_t + pi_underside));
echo(str("REPORT depth stations: panel front ", y_panel_front, ", panel back ", y_panel_back,
         ", stack top ", y_stack_top, ", Pi PCB top ", y_pi_top, ", back inner ", y_back_in));
echo(str("REPORT bezel opening ", open_w, " x ", open_h, "; effective lip ", lip_eff,
         " mm (requested ", bezel_lip, ")"));
echo(str("REPORT screws: panel M3 x ", panel_screw_len, "; Pi M2.5 short space ", pi_screw_short,
         "; long space ", pi_screw_long, "; stand M3 x ", stand_screw_len));
echo(str("REPORT split needed for bed: ", needs_split));
if (screwless)
    echo(str("REPORT printed pins: Pi short grip ", pi_pin_short, ", Pi long grip ", pi_pin_long,
             ", panel pin ", post_floor, " + ", insert_pin_grip, " into the insert"));
if (screwless && insert_pin_grip > panel_insert_depth - 0.5)
    echo(str("WARNING: insert_pin_grip ", insert_pin_grip, " would bottom out in a ",
             panel_insert_depth, " mm insert; shorten it."));
if (!bezel_hides_leds && bezel_lip > lip_eff + 0.01)
    echo(str("WARNING: bezel_lip ", bezel_lip, " would hide part of the outer LEDs; clamped to ",
             lip_eff, ". Set bezel_hides_leds = true to force it."));

// =============================================================================
//  Helpers
// =============================================================================

// Extrude a 2D shape drawn in the XZ plane (2D x -> X, 2D y -> Z) from y0 to y1.
module xz_extrude(y0, y1) {
    translate([0, y1, 0]) rotate([90, 0, 0]) linear_extrude(y1 - y0, convexity = 10) children();
}

module rrect(w, h, r) {
    rr = max(min(r, w / 2 - eps, h / 2 - eps), eps);
    offset(r = rr) square([w - 2 * rr, h - 2 * rr], center = true);
}

module rect2(x0, x1, z0, z1) {
    translate([x0, z0]) square([x1 - x0, z1 - z0]);
}

// Cylinder along +Y from y0 to y1 at [x, z].
module ycyl(d, y0, y1, xz) {
    translate([xz[0], y0, xz[1]]) rotate([-90, 0, 0]) cylinder(d = d, h = y1 - y0);
}

// Vertical hole whose cross-section points toward -Y (the front). The shell
// prints back-down, so -Y is "up" there and the point removes the overhang.
module teardrop_z(d, h) {
    linear_extrude(h) hull() { circle(d = d); translate([0, -d / 2 * 1.75]) square(0.01, center = true); }
}

module wbox(x0, x1, y0, y1, z0, z1) {
    translate([x0, y0, z0]) cube([x1 - x0, y1 - y0, z1 - z0]);
}

// Two 0.2 mm "bridge trick" layers above a counterbore of diameter `big`
// that narrows to `small` (shell prints back-down, so -Y is up): a slot,
// then a square, so the step prints as plain bridges.
module bridge_layers(xz, y_ceiling, small, big) {
    translate([xz[0], y_ceiling - 0.2, xz[1]]) wbox(-small / 2, small / 2, 0, 0.2 + eps, -big / 2, big / 2);
    translate([xz[0], y_ceiling - 0.4, xz[1]]) wbox(-small / 2, small / 2, 0, 0.2 + eps, -small / 2, small / 2);
}

// Printed snap pin, axis +Z, head underside at z = 0. S is the grip length
// (head underside to the ledge the barb catches on); the catch face slopes
// from S + catch[0] to S + catch[1]. With bulge > 0 the pin has no barb: it
// is a spring that grips a threaded hole from S to S + grip. The pin is cut to
// a flat on -Y (it prints lying on it) and split in the YZ plane, so the
// prongs flex along X, in the bed plane. The slit's root is round.
module snap_pin(S, d, barb, slit, head, catch = [0, 0.1], grip = 0, bulge = 0, stem = 0) {
    t = pin_flat * d;
    tip = 1.6;
    z_tip = bulge > 0 ? S + grip : S + catch[1] + tip;
    hd = head[0] / 2;
    prof = bulge > 0
        ? [[0, -head[1]], [hd, -head[1]], [hd, -0.3], [hd - 0.3, 0], [d / 2, 0],
           [d / 2, z_tip - 2.7], [bulge / 2, z_tip - 2.2], [bulge / 2, z_tip - 1.0],
           [d / 2 - 0.3, z_tip], [0, z_tip]]
        : [[0, -head[1]], [hd, -head[1]], [hd, -0.3], [hd - 0.3, 0], [d / 2, 0],
           [d / 2, S + catch[0]], [barb / 2, S + catch[1]], [d / 2 - 0.2, z_tip], [0, z_tip]];
    slit0 = bulge > 0 ? 0.3 : max(0.3, S - 7);
    difference() {
        union() {
            intersection() {
                rotate_extrude($fn = 40) polygon(prof);
                union() {
                    translate([-20, -t / 2, -eps]) cube([40, t, z_tip + 1]);
                    translate([-20, -t / 2, -head[1] - 1]) cube([40, 20, head[1] + 1]);
                }
            }
            // Bar across the head, and the stem behind it.
            intersection() {
                translate([0, 0, -head[1]]) cylinder(d = head[2], h = head[1] - 0.3, $fn = 40);
                translate([-20, -t / 2, -head[1]]) cube([40, t, head[1]]);
            }
            if (stem > 0) translate([-1.5, -t / 2, -head[1] - stem]) cube([3, t, stem + eps]);
        }
        translate([-slit / 2, -20, slit0]) cube([slit, 40, z_tip]);
        translate([0, 0, slit0]) rotate([90, 0, 0]) cylinder(d = slit, h = 40, center = true, $fn = 16);
    }
}
module pi_pin(long) {
    snap_pin(long ? pi_pin_long : pi_pin_short, pi_pin_d, pi_pin_barb, pi_pin_slit, pi_pin_head, pi_pin_catch);
}
module insert_pin() {
    snap_pin(post_floor, insert_pin_d, 0, insert_pin_slit, insert_pin_head,
             grip = insert_pin_grip, bulge = insert_pin_bulge, stem = insert_pin_stem);
}
module joint_pin() { snap_pin(joint_pin_len, joint_pin_d, joint_pin_barb, joint_pin_slit, joint_pin_head); }

// Stand dovetail profile in the XZ plane at X = 0: neck at the case's bottom
// face, widening upward. `grow` widens it per side (negative = clearance),
// `drop` lowers its top, `below` extends the neck down past the face.
// The profile is not convex, so hull() works on its two convex pieces
// (piece 0: the neck below the face, 1: the flaring part above it).
module dt_profile(grow, drop = 0, below = 1, piece = -1) {
    if (piece != 1)
        translate([-dt_w / 2 - grow, -out_h / 2 - below]) square([dt_w + 2 * grow, below + eps]);
    if (piece != 0)
        polygon([[-dt_w / 2 - grow, -out_h / 2], [dt_w / 2 + grow, -out_h / 2],
                 [dt_w / 2 + dt_spread + grow, dt_top - drop], [-dt_w / 2 - dt_spread - grow, dt_top - drop]]);
}

// =============================================================================
//  Bezel
// =============================================================================

module bezel_front_plate() {
    difference() {
        // Outer plate with a 0.5 mm chamfer on the front edge.
        hull() {
            xz_extrude(0, eps) rrect(out_w - 1, out_h - 1, out_r - 0.5);
            xz_extrude(0.5, front_t) rrect(out_w, out_h, out_r);
        }
        // Opening sized to the LED area, chamfered 45 degrees toward the front
        // so the outer pixels are not shadowed at an angle.
        hull() {
            xz_extrude(front_t - 0.6, front_t + eps) rrect(open_w, open_h, 0.5);
            xz_extrude(-eps, 0) rrect(open_w + 2 * open_chamfer, open_h + 2 * open_chamfer,
                                      0.5 + open_chamfer);
        }
    }
}

// Positions of the snap fingers: [axis, coordinate along the wall, side].
// axis "x": finger on the top (side +1) or bottom (-1) wall at X = coord.
// axis "z": finger on the right (+1) or left (-1) end wall at Z = coord.
function snap_list() = concat(
    [for (m = module_x, s = snap_x, side = [-1, 1]) ["x", m + s, side]],
    [for (side = [-1, 1]) ["z", 0, side]]);

module tongue_ring() {
    tw = cav_w - 2 * (pin_clear / 2);
    th = cav_h - 2 * (pin_clear / 2);
    xz_extrude(y_joint - eps, y_tongue_end)
        difference() {
            rrect(tw, th, cav_r);
            rrect(tw - 2 * tongue_t, th - 2 * tongue_t, eps);
        }
    // Sloped ledge (steeper than 45 degrees) from the wall's inner face to the
    // tongue's inner face, behind the panel's back face.
    step = (cav_w - (tw - 2 * tongue_t)) / 2;
    step_h = 1.25 * step;
    difference() {
        xz_extrude(y_joint - step_h - eps, y_joint) rrect(out_w - 0.1, out_h - 0.1, out_r);
        hull() {
            xz_extrude(y_joint - step_h - 2 * eps, y_joint - step_h - eps) rrect(cav_w, cav_h, cav_r);
            xz_extrude(y_joint, y_joint + eps) rrect(tw - 2 * tongue_t, th - 2 * tongue_t, eps);
        }
    }
}

// Slits that free a flexing finger, and the bump on its outer face.
module snap_slits(s) {
    len_y = tongue_len - 1.5;
    for (k = [-1, 1]) {
        c = s[1] + k * (snap_finger_w / 2 + snap_slit / 2);
        if (s[0] == "x")
            wbox(c - snap_slit / 2, c + snap_slit / 2, y_tongue_end - len_y, y_tongue_end + 1,
                 s[2] * cav_h / 2 - 5, s[2] * cav_h / 2 + 5);
        else
            wbox(s[2] * cav_w / 2 - 5, s[2] * cav_w / 2 + 5, y_tongue_end - len_y, y_tongue_end + 1,
                 c - snap_slit / 2, c + snap_slit / 2);
    }
}

// Bump profile: vertical catch face at y_snap_catch, ramp toward the tongue tip.
module snap_bump(s) {
    tw = cav_w - pin_clear;
    th = cav_h - pin_clear;
    // Catch face sloped ~51 degrees so it prints without support; ramp behind it.
    prof = [[0, -0.4], [0, 0], [0.75, snap_h], [3.2, 0], [3.2, -0.4]];  // [along +Y, outward]
    if (s[0] == "x") {
        zw = s[2] * th / 2;
        translate([s[1] - snap_len / 2, y_snap_catch, zw])
            rotate([90, 0, 90]) linear_extrude(snap_len)
                polygon([for (p = prof) [p[0], s[2] * p[1]]]);
    } else {
        xw = s[2] * tw / 2;
        translate([xw, y_snap_catch, s[1] - snap_len / 2])
            linear_extrude(snap_len)
                polygon([for (p = prof) [s[2] * p[1], p[0]]]);
    }
}

module bezel() {
    difference() {
        union() {
            bezel_front_plate();
            // Walls around the panel.
            xz_extrude(front_t - eps, y_joint)
                difference() { rrect(out_w, out_h, out_r); rrect(cav_w, cav_h, cav_r); }
            tongue_ring();
        }
        for (s = snap_list()) snap_slits(s);
    }
    for (s = snap_list()) snap_bump(s);
}

// =============================================================================
//  Shell (rear housing)
// =============================================================================

// Rear access bay: barrel plug, USB-C plug, microSD and the panel OUTPUT.
module bay_window_2d() {
    offset(r = 2.5) offset(delta = -2.5) union() {
        // Left of the Pi, full height of the jack and SD area.
        rect2(mx0 + bay_left, P([0, 0])[0] - 2.0, bay_bottom, out_h / 2 - wall - 4.5);
        // Below the Pi, for the USB-C plug.
        rect2(mx0 + bay_left, mx0 + bay_low_right, bay_bottom, P([0, 0])[1] - 2.0);
    }
    // Finger notch reaching the microSD card edge.
    rect2(P([0, 0])[0] - 3, P([0, 0])[0] + 0.5, sd_z - 7, sd_z + 7);
}

// Back wall kept solid under the stand bosses (they print standing on it).
module bay_window_keep_2d() {
    if (desk_stand) for (x = [-stand_pad_x, stand_pad_x])
        rect2(x - stand_boss[0] / 2 - 2, x + stand_boss[0] / 2 + 2, -out_h, -cav_h / 2 + stand_boss[2] + 2);
}

function vent_ok(x, keep) = len([for (k = keep) if (abs(x - k[0]) < k[1]) 1]) == 0;

module top_bottom_vents() {
    vy0 = y_tongue_end + 2;
    vy1 = y_back_in - 2.5;
    snaps = [for (m = module_x, s = snap_x) [m + s, snap_finger_w / 2 + 5]];
    // Top: along the whole top edge (the panel's heat rises here).
    for (x = [-out_w / 2 + 12 : 5 : out_w / 2 - 12])
        if (vent_ok(x, snaps))
            translate([x - 1.1, vy0, out_h / 2 - wall - 1]) cube([2.2, vy1 - vy0, wall + 2]);
    // Bottom: intake, clear of the stand pads, bosses and the USB-C clip.
    keep = concat(snaps, [[stand_pad_x, stand_pad_w / 2 + 3], [-stand_pad_x, stand_pad_w / 2 + 3],
                          [usbc_xz[0], 11]]);
    for (x = [-out_w / 2 + 12 : 5 : out_w / 2 - 12])
        if (vent_ok(x, keep))
            translate([x - 1.1, vy0, -out_h / 2 - 1]) cube([2.2, vy1 - vy0, wall + 2]);
}

module back_vents_2d() {
    // Behind the Pi (clear of the standoffs).
    for (x = [P([28, 0])[0] : 5 : P([80, 0])[0]])
        rect2(x - 1.25, x + 1.25, P([0, 10])[1], P([0, 47])[1]);
    // Behind the right part of the panel, next to the ribbon loop zone.
    for (x = [mx0 + 58 : 5 : mx0 + 80]) rect2(x - 1.25, x + 1.25, -22, 22);
    // Extra panels in a 2-panel build.
    if (panels > 1) for (i = [1 : panels - 1])
        for (x = [module_x[i] - 60 : 5 : module_x[i] + 60])
            rect2(x - 1.25, x + 1.25, -20, 20);
}

module panel_post(xz) {
    // Column from the back wall to the panel's back face, tapered at the top.
    hull() {
        ycyl(post_top_d, y_panel_back, y_panel_back + eps, xz);
        ycyl(post_d, y_panel_back + 1.2, y_panel_back + 1.2 + eps, xz);
    }
    ycyl(post_d, y_panel_back + 1.2, y_back_in + eps, xz);
}

module panel_post_holes(xz) {
    // Screwdriver well from the back, M3 clearance through the floor.
    yf = y_panel_back + post_floor;
    ycyl(m3_head_well_d, yf, depth + 1, xz);
    ycyl(m3_clear_d, y_panel_back - 1, depth + 1, xz);
    // Two 0.2 mm "bridge trick" layers so the well's ceiling prints as plain
    // bridges (slot, then square) instead of an unsupported round overhang.
    translate([xz[0], yf - 0.2, xz[1]]) wbox(-m3_clear_d / 2, m3_clear_d / 2, 0, 0.2 + eps, -m3_head_well_d / 2, m3_head_well_d / 2);
    translate([xz[0], yf - 0.4, xz[1]]) wbox(-m3_clear_d / 2, m3_clear_d / 2, 0, 0.2 + eps, -m3_clear_d / 2, m3_clear_d / 2);
}

module pi_standoffs() {
    for (h = pi_holes) {
        ycyl(pi_standoff_d, y_pi_bot, y_back_in + eps, P(h));
        // Flared foot: the barb pocket is nearly as wide as the standoff, so
        // the foot carries it onto the back wall (prints as a fillet).
        if (screwless) hull() {
            ycyl(pi_standoff_d, y_back_in - 1.8, y_back_in - 1.8 + eps, P(h));
            ycyl(pi_pin_pocket + 2 * min_wall, y_back_in - 0.3, y_back_in + eps, P(h));
        }
    }
}

module pi_standoff_holes() {
    for (h = pi_holes) {
        if (screwless) {
            // Bore for the snap pin, and a pocket in the back wall where its
            // barb catches on the end of the standoff.
            ycyl(pi_pin_bore, y_pi_bot - 1, depth + 1, P(h));
            ycyl(pi_pin_pocket, y_back_in, depth + 1, P(h));
            // The barb catches on the step at the top of these layers.
            bridge_layers(P(h), y_back_in, pi_pin_barb + 0.4, pi_pin_pocket);
        } else
            ycyl(m25_tap_d, y_pi_bot - 1, depth + 1, P(h));
    }
}

// Bosses for the desk stand. Screws: an M3 nut slides in from the front.
// Printed: a dovetail groove, open at the back face, takes the stand's tongue.
stand_boss = screwless ? [dt_w + 2 * dt_spread + 5, 2 * (dt_len + 2 - stand_screw_from_back), dt_h - wall + 2]
                       : [10, 12, 9];  // X, Y, Z
function stand_screw_y() = depth - stand_screw_from_back;
module stand_bosses() {
    for (x = [-stand_pad_x, stand_pad_x])
        // Runs back to the back wall so it prints as a column (no overhang).
        wbox(x - stand_boss[0] / 2, x + stand_boss[0] / 2,
             stand_screw_y() - stand_boss[1] / 2, y_back_in + eps,
             -cav_h / 2 - eps, -cav_h / 2 + stand_boss[2]);
}
module stand_boss_holes() {
    if (screwless) for (x = [-stand_pad_x, stand_pad_x])
        translate([x, 0, 0]) {
            xz_extrude(depth - dt_len, depth + 1) dt_profile(0);
            // 0.6 mm chamfer at the mouth: it prints on the bed, where
            // elephant foot would otherwise pinch the groove.
            for (k = [0, 1]) hull() {
                xz_extrude(depth - 0.6, depth - 0.6 + eps) dt_profile(0, 0, 1, k);
                xz_extrude(depth, depth + 1) dt_profile(0.6, -0.6, 1, k);
            }
        }
    else for (x = [-stand_pad_x, stand_pad_x]) {
        translate([x, stand_screw_y(), -out_h / 2 - 1]) teardrop_z(m3_clear_d, wall + stand_boss[2] + 2);
        // Nut slot, open toward the front of the case.
        nz = -cav_h / 2 + 2.2;
        wbox(x - (m3_nut_af + 0.3) / 2, x + (m3_nut_af + 0.3) / 2,
             stand_screw_y() - stand_boss[1] / 2 - 1, stand_screw_y() + (m3_nut_af + 0.3) / 2 / cos(30),
             nz, nz + m3_nut_t + 0.3);
    }
}

// Snap-in C clip, axis along Y, opening toward `open_dir` (angle in the XZ plane).
module c_clip(xz, cable_d, y0, y1, open_dir) {
    id = cable_d - 0.2;
    gap = cable_d * 0.72;
    translate([xz[0], 0, xz[1]])
        xz_extrude(y0, y1) difference() {
            circle(d = id + 2 * min_wall);
            circle(d = id);
            rotate(open_dir) translate([0, -gap / 2]) square([id, gap]);
        }
}

// Barrel cable clip on the left edge of the bay window, with a web to the wall.
module barrel_clip() {
    y0 = y_back_in - 10;
    c_clip(barrel_clip_xz, barrel_cable_d, y0, depth, 0);
    r_out = (barrel_cable_d - 0.2) / 2 + min_wall;
    wbox(mx0 + bay_left - 2, barrel_clip_xz[0] - r_out + 0.8, y0, depth,
         barrel_clip_xz[1] - 3, barrel_clip_xz[1] + 3);
}

// USB-C cable grip in the bottom wall: a keyhole slot open to the back.
usbc_grip = [14, 13, 3];  // X, Y length, Z height of the thickening block
module usbc_grip_block() {
    wbox(usbc_xz[0] - usbc_grip[0] / 2, usbc_xz[0] + usbc_grip[0] / 2,
         y_back_in - usbc_grip[1], y_back_in + eps, -cav_h / 2 - eps, -cav_h / 2 + usbc_grip[2]);
}
module usbc_grip_cut() {
    zc0 = -out_h / 2 - 1;
    zc1 = -cav_h / 2 + usbc_grip[2] + 1;
    translate([usbc_xz[0], usbc_y, zc0]) teardrop_z(usbc_cable_d, zc1 - zc0);
    wbox(usbc_xz[0] - (usbc_cable_d - 0.6) / 2, usbc_xz[0] + (usbc_cable_d - 0.6) / 2,
         usbc_y, depth + 1, zc0, zc1);
}

// Column with a snap-in gutter that holds the panel power lead (red + black
// side by side), so a tug on the lead never reaches the screw terminal.
pwr_clip_xz = [mx0 + pwr_clip_pos[0], pwr_clip_pos[1]];
pwr_clip_tip_y = y_panel_back + 6;
module pwr_clip() {
    gw = 2 * pwr_wire_d - 0.2;         // channel width (two wires, snug)
    gd = pwr_wire_d + 0.6;             // channel depth
    bw = gw + 2 * min_wall;
    blen = 8;                           // along Z (within the column)
    difference() {
        // Square column, same footprint as the gutter (prints with no overhang).
        wbox(pwr_clip_xz[0] - bw / 2, pwr_clip_xz[0] + bw / 2, pwr_clip_tip_y, y_back_in + eps,
             pwr_clip_xz[1] - blen / 2, pwr_clip_xz[1] + blen / 2);
        // Channel along Z, opening toward the panel. Its 0.4 mm snap lips have
        // sloped undersides so they print without support.
        y0 = pwr_clip_tip_y;
        translate([pwr_clip_xz[0], 0, pwr_clip_xz[1] - blen])
            linear_extrude(2 * blen) polygon([
                [-gw / 2 + 0.4, y0 - 1], [gw / 2 - 0.4, y0 - 1], [gw / 2 - 0.4, y0 + 0.8],
                [gw / 2, y0 + 1.4], [gw / 2, y0 + 0.8 + gd], [-gw / 2, y0 + 0.8 + gd],
                [-gw / 2, y0 + 1.4], [-gw / 2 + 0.4, y0 + 0.8]]);
    }
}

// Shell snap windows that catch the bezel's tongue bumps.
module snap_windows() {
    for (s = snap_list()) {
        if (s[0] == "x")
            wbox(s[1] - snap_len / 2 - 0.5, s[1] + snap_len / 2 + 0.5,
                 y_snap_catch - 0.1, y_snap_catch + 3.4,
                 s[2] > 0 ? cav_h / 2 - 1 : -out_h / 2 - 1, s[2] > 0 ? out_h / 2 + 1 : -cav_h / 2 + 1);
        else
            wbox(s[2] > 0 ? cav_w / 2 - 1 : -out_w / 2 - 1, s[2] > 0 ? out_w / 2 + 1 : -cav_w / 2 + 1,
                 y_snap_catch - 0.1, y_snap_catch + 3.4,
                 s[1] - snap_len / 2 - 0.5, s[1] + snap_len / 2 + 0.5);
    }
}

// Keyhole slots with a closed pocket behind them (wall_mount option).
keyholes = [[-88, 0], [88, 0]];
module keyhole_pockets() {
    for (k = keyholes) translate([mx0 - module_x[0], 0, 0])
        wbox(k[0] - 7, k[0] + 7, y_back_in - 5, y_back_in + eps, k[1] - 8, k[1] + 14);
}
module keyhole_cuts() {
    for (k = keyholes) {
        // Head hole and slot through the back wall.
        ycyl(8.5, y_back_in - 3.5, depth + 1, k);
        hull() { ycyl(4.2, y_back_in - eps, depth + 1, k); ycyl(4.2, y_back_in - eps, depth + 1, [k[0], k[1] + 9]); }
        // Room for the screw head behind the slot.
        hull() { ycyl(8.5, y_back_in - 3.5, y_back_in - 0.8, k); ycyl(8.5, y_back_in - 3.5, y_back_in - 0.8, [k[0], k[1] + 9]); }
    }
}

// Joint blocks for a split shell (2-panel build): pins + M3 bolt across the cut.
split_block = [20, 8];  // X width, Z height
module split_blocks() {
    for (side = [-1, 1])
        wbox(-split_block[0] / 2, split_block[0] / 2, y_tongue_end + 1, y_back_in + eps,
             side > 0 ? cav_h / 2 - split_block[1] : -cav_h / 2,
             side > 0 ? cav_h / 2 + eps : -cav_h / 2 + split_block[1]);
}
split_pin_d = 3.0;
module split_block_holes() {
    for (side = [-1, 1]) {
        zc = side * (cav_h / 2 - split_block[1] / 2);
        // Alignment pin holes.
        for (yy = [y_tongue_end + 5, y_back_in - 4])
            translate([-6, yy, zc]) rotate([0, 90, 0]) cylinder(d = split_pin_d + 2 * pin_clear, h = 12);
        // M3 bolt: head recess on the left, nut trap on the right.
        yb = (y_tongue_end + y_back_in) / 2;
        translate([-split_block[0] / 2 - 1, yb, zc]) rotate([0, 90, 0]) cylinder(d = m3_clear_d, h = split_block[0] + 2);
        translate([-split_block[0] / 2 - 1, yb, zc]) rotate([0, 90, 0]) cylinder(d = 6.2, h = 4);
        translate([split_block[0] / 2 - 3, yb, zc]) rotate([0, 90, 0]) cylinder(d = (m3_nut_af + 0.3) / cos(30), h = 4, $fn = 6);
    }
}

module shell_body() {
    difference() {
        union() {
            // Side, top and bottom walls.
            xz_extrude(y_joint, depth - 0.5)
                difference() { rrect(out_w, out_h, out_r); rrect(cav_w, cav_h, cav_r); }
            // Back wall with a 0.5 mm chamfer on the outer edge (it prints face down).
            hull() {
                xz_extrude(y_back_in, depth - 0.5) rrect(out_w, out_h, out_r);
                xz_extrude(depth - eps, depth) rrect(out_w - 1, out_h - 1, out_r - 0.5);
            }
            for (m = module_x, h = panel_mounts) panel_post([m + h[0], h[1]]);
            pi_standoffs();
            if (desk_stand) stand_bosses();
            usbc_grip_block();
            if (wall_mount) keyhole_pockets();
            if (panels > 1) split_blocks();
        }
        for (m = module_x, h = panel_mounts) panel_post_holes([m + h[0], h[1]]);
        pi_standoff_holes();
        xz_extrude(y_back_in - 1, depth + 1) difference() { bay_window_2d(); bay_window_keep_2d(); }
        xz_extrude(y_back_in - 1, depth + 1) back_vents_2d();
        top_bottom_vents();
        snap_windows();
        if (desk_stand) stand_boss_holes();
        usbc_grip_cut();
        if (wall_mount) keyhole_cuts();
        if (panels > 1) split_block_holes();
    }
}

// Snap-in clips: press-fits on the cables by design (checked separately).
module shell_clips() {
    barrel_clip();
    pwr_clip();
}

module shell() { shell_body(); shell_clips(); }

// =============================================================================
//  Desk stand
// =============================================================================

// Places the case (local frame) on the stand: tilted back by stand_tilt.
stand_lift = stand_base_t + stand_clear + depth * sin(stand_tilt);
stand_y0 = -(stand_d - depth * cos(stand_tilt) - out_h * sin(stand_tilt)) / 2;
module on_stand() {
    translate([0, 0, stand_lift]) rotate([-stand_tilt, 0, 0]) translate([0, 0, out_h / 2]) children();
}

// Dovetail tongue on a stand pad, in the case's frame. It slides into the
// shell's groove from the back and stops against the groove's front end.
// Its last few mm widen into a friction wedge (`lock` = false drops the
// wedge, for the collision check).
module stand_tongue(x, lock = true) {
    y0 = depth - dt_len;
    yw = depth - 4.5;
    translate([x, 0, 0]) {
        xz_extrude(y0, yw) dt_profile(-pin_clear, pin_clear, 2);
        for (k = [0, 1]) hull() {
            xz_extrude(yw - eps, yw) dt_profile(-pin_clear, pin_clear, 2, k);
            xz_extrude(depth - 2.5, depth - 0.6) dt_profile(lock ? dt_lock : -pin_clear, pin_clear, 2, k);
        }
    }
}

module stand(lock = true) {
    difference() {
        union() {
            // Base plate.
            translate([0, stand_y0 + stand_d / 2, 0])
                linear_extrude(stand_base_t) rrect(stand_w, stand_d, 8);
            // Two pads whose tops follow the tilted case bottom.
            for (x = [-stand_pad_x, stand_pad_x])
                intersection() {
                    wbox(x - stand_pad_w / 2, x + stand_pad_w / 2, -2, depth * cos(stand_tilt) + 2,
                         stand_base_t - eps, stand_lift + out_h);
                    on_stand() wbox(-out_w, out_w, -20, depth + 20, -out_h / 2 - 80, -out_h / 2 - 0.05);
                }
            if (screwless) for (x = [-stand_pad_x, stand_pad_x]) on_stand() stand_tongue(x, lock);
        }
        // Counterbored screw holes, square to the case bottom.
        if (!screwless) for (x = [-stand_pad_x, stand_pad_x])
            on_stand() translate([x, stand_screw_y(), -out_h / 2]) {
                translate([0, 0, -30]) cylinder(d = m3_clear_d, h = 31);
                translate([0, 0, -80]) cylinder(d = 6.6, h = 80 - stand_screw_floor);
            }
        // Cable notch at the back.
        translate([stand_cable_notch[0] - stand_cable_notch[1] / 2,
                   stand_y0 + stand_d - stand_cable_notch[2], -1])
            cube([stand_cable_notch[1], stand_cable_notch[2] + 1, stand_base_t + 2]);
        // Groove for the USB-C cable from the case bottom to the notch.
        translate([usbc_xz[0] - 3.5, 0, stand_base_t - 1.5]) cube([7, stand_y0 + stand_d, 2]);
    }
}

// =============================================================================
//  Small parts
// =============================================================================

// Spacer between Pi and bonnet on the two shared holes (print 2).
// The bore lets a snap pin's barb slide through with a light drag.
spacer_bore = screwless ? pi_pin_barb - 0.1 : m25_clear_d;
module spacer() {
    difference() {
        cylinder(d = spacer_od, h = bonnet_gap - 0.2);
        translate([0, 0, -1]) cylinder(d = spacer_bore, h = bonnet_gap + 2);
    }
}
module spacers() { for (i = [0, 1]) translate([i * 9, 0, 0]) spacer(); }

// A snap pin in print orientation: lying on its flat, axis along -Y.
module pin_flat_down(d) { translate([0, 0, pin_flat * d / 2]) rotate([90, 0, 0]) children(); }

// Every snap pin for the build, plus one spare of each kind (print 100% infill).
module snap_pins() {
    n_ins = 4 * panels + 1;
    for (i = [0 : n_ins - 1]) translate([i * 8, 0, 0]) pin_flat_down(insert_pin_d) insert_pin();
    for (i = [0 : 2]) translate([i * 8, -16, 0]) pin_flat_down(pi_pin_d) pi_pin(false);
    for (i = [0 : 2]) translate([26 + i * 8, -16, 0]) pin_flat_down(pi_pin_d) pi_pin(true);
    if (panels > 1)
        for (i = [0 : 2]) translate([52 + i * 8, -16, 0]) pin_flat_down(joint_pin_d) joint_pin();
}

// Alignment pins for a split shell (2-panel build, print 4).
module pins() {
    for (i = [0 : 3]) translate([i * 6, 0, 0])
        rotate([0, 0, 0]) cylinder(d = split_pin_d, h = 11, $fn = 24);
}

// =============================================================================
//  Test-fit coupon
// =============================================================================
//  A: panel corner gauge. Lay the panel face-UP on it: the corner must drop in
//     between the walls, and an M3 x panel_screw_len screw from below must
//     thread into the panel's corner insert. Same floor thickness as the posts.
//  B: bezel corner. Put it on the panel's front corner: no LED may be covered.
//  C: one Pi standoff on a piece of back wall. An M2.5 screw must bite.
//  D: one Pi/bonnet spacer.

module coupon_gauge() {
    h = panel_mounts[0];
    x0 = h[0] - 9;
    z0 = h[1] - 9;
    // Plate in the panel's back plane; +Z here = toward the panel.
    difference() {
        union() {
            translate([x0, z0, 0]) cube([cav_w / 2 + wall - x0, cav_h / 2 + wall - z0, post_floor]);
            // Walls along the two outer edges, 4 mm up the panel's sides.
            translate([cav_w / 2, z0, 0]) cube([wall, cav_h / 2 + wall - z0, post_floor + 4]);
            translate([x0, cav_h / 2, 0]) cube([cav_w / 2 + wall - x0, wall, post_floor + 4]);
        }
        translate([h[0], h[1], -1]) cylinder(d = m3_clear_d, h = post_floor + 2);
        // Label pocket: a small dot marks the hole corner.
        translate([x0 + 3, z0 + 3, post_floor - 0.4]) cylinder(d = 2, h = 1);
    }
}

module coupon_bezel_corner() {
    x0 = open_w / 2 - 14;
    z0 = open_h / 2 - 14;
    intersection() {
        bezel();
        wbox(x0, out_w / 2 + 1, -1, 6, z0, out_h / 2 + 1);
    }
}

module coupon_standoff() {
    difference() {
        union() {
            translate([-7, -7, 0]) cube([14, 14, back_t]);
            cylinder(d = pi_standoff_d, h = back_t + pi_underside);
            if (screwless) hull() {
                translate([0, 0, back_t - eps]) cylinder(d = pi_pin_pocket + 2 * min_wall, h = 0.3 + eps);
                translate([0, 0, back_t + 1.8]) cylinder(d = pi_standoff_d, h = eps);
            }
        }
        if (screwless) {
            // Same bore, barb pocket and bridge layers as the shell.
            translate([0, 0, -1]) cylinder(d = pi_pin_bore, h = 20);
            translate([0, 0, -1]) cylinder(d = pi_pin_pocket, h = back_t + 1);
            st = pi_pin_barb + 0.4;
            translate([-st / 2, -pi_pin_pocket / 2, back_t - eps]) cube([st, pi_pin_pocket, 0.2 + eps]);
            translate([-st / 2, -st / 2, back_t + 0.2 - eps]) cube([st, st, 0.2 + eps]);
        } else
            translate([0, 0, -1]) cylinder(d = m25_tap_d, h = 20);
    }
}

// E: dovetail test. A short groove block (standing, as the shell prints it)
// and a tongue on a plate (as the stand prints it, wedge end included).
module coupon_dovetail() {
    bw = stand_boss[0];
    // Groove block: the case's bottom wall and boss, 10 mm long.
    linear_extrude(10) translate([0, out_h / 2]) difference() {
        translate([-bw / 2, -out_h / 2]) square([bw, wall + stand_boss[2]]);
        dt_profile(0);
    }
    // Tongue: 12 mm long on a 3 mm plate, the last 4 mm widening into the wedge.
    translate([0, -6, 0]) {
        translate([-8, -12, 0]) cube([16, 12, 3]);
        translate([0, 0, 3]) rotate([90, 0, 0]) {
            linear_extrude(8) translate([0, out_h / 2]) dt_profile(-pin_clear, pin_clear, 0.5);
            for (k = [0, 1]) hull() {
                translate([0, 0, 8 - eps]) linear_extrude(eps) translate([0, out_h / 2]) dt_profile(-pin_clear, pin_clear, 0.5, k);
                translate([0, 0, 10]) linear_extrude(2) translate([0, out_h / 2]) dt_profile(dt_lock, pin_clear, 0.5, k);
            }
        }
    }
}

module coupon() {
    // A, flat, panel side up.
    translate([-(panel_mounts[0][0] - 9), -(panel_mounts[0][1] - 9), 0]) coupon_gauge();
    // B, front face down (same orientation as the real bezel).
    translate([-(open_w / 2 - 14), out_h / 2 + 36, 0]) rotate([90, 0, 0]) coupon_bezel_corner();
    // C and D.
    translate([34, 8, 0]) coupon_standoff();
    translate([34, 24, 0]) spacer();
    if (screwless) {
        // E, and one panel pin and one short Pi pin to test with.
        translate([58, 2, 0]) coupon_dovetail();
        translate([48, 40, 0]) pin_flat_down(insert_pin_d) insert_pin();
        translate([56, 40, 0]) pin_flat_down(pi_pin_d) pi_pin(false);
    }
}

// =============================================================================
//  Hardware models (for the renders and the collision checks)
// =============================================================================

module led_panel() {
    for (m = module_x) translate([m, 0, 0]) {
        color([0.08, 0.08, 0.09]) difference() {
            wbox(-panel_w / 2, panel_w / 2, y_panel_front, y_panel_back, -panel_h / 2, panel_h / 2);
            for (h = panel_mounts) ycyl(3, y_panel_back - panel_insert_depth, y_panel_back + 1, h);
        }
        // LED face: every pixel, lit amber so the renders read as a display.
        if (show_leds) color([1.0, 0.55, 0.1])
            for (c = [0 : cols - 1], r = [0 : rows - 1])
                translate([-panel_w / 2 + pitch / 2 + c * pitch - led_size / 2, y_panel_front - 0.05,
                           -panel_h / 2 + pitch / 2 + r * pitch - led_size / 2])
                    cube([led_size, 0.1, led_size]);
        color([0.6, 0.6, 0.6]) for (p = panel_pins) ycyl(panel_pin_d, y_panel_back - eps, y_panel_back + panel_pin_h, p);
        // IDC plugs + ribbon stubs at both ends, power plug at the centre.
        color([0.15, 0.15, 0.15]) for (s = [-1, 1])
            wbox(s * panel_idc_x - panel_idc_size[0] / 2, s * panel_idc_x + panel_idc_size[0] / 2,
                 y_panel_back - eps, y_panel_back + panel_idc_proud, -panel_idc_size[1] / 2, panel_idc_size[1] / 2);
        color([0.9, 0.9, 0.85])
            wbox(-panel_pwr_size[0] / 2, panel_pwr_size[0] / 2, y_panel_back - eps, y_panel_back + panel_pwr_proud,
                 -panel_pwr_size[1] / 2, panel_pwr_size[1] / 2);
    }
}

// Box on the Pi's component side: board coords x0..x1, y0..y1, height h.
module pi_part(x0, x1, y0, y1, h) {
    a = P([x0, y0]);
    b = P([x1, y1]);
    wbox(a[0], b[0], y_pi_top - h, y_pi_top + eps, a[1], b[1]);
}
module bonnet_part(r, h) {
    a = B([r[0], r[2]]);
    b = B([r[1], r[3]]);
    wbox(a[0], b[0], y_bonnet_top - h, y_bonnet_top + eps, a[1], b[1]);
}

module pi_board() {
    color([0.1, 0.45, 0.2]) difference() {
        translate([P([0, 0])[0], y_pi_top, P([0, 0])[1]])
            rotate([-90, 0, 0]) mirror([0, 1, 0])
                linear_extrude(pi_pcb_t) translate([pi_w / 2, pi_h / 2]) rrect(pi_w, pi_h, pi_corner_r);
        for (h = pi_holes) ycyl(pi_hole_d, y_pi_top - 1, y_pi_bot + 1, P(h));
    }
    color([0.75, 0.75, 0.78]) {
        pi_part(pi_usbc_x - pi_usbc_size[0] / 2, pi_usbc_x + pi_usbc_size[0] / 2, -pi_usbc_overhang, 7.4 - pi_usbc_overhang, pi_usbc_size[1]);
        for (x = pi_hdmi_x) pi_part(x - 3.6, x + 3.6, -1.4, 6.6, 3.0);
        for (u = pi_usba) pi_part(pi_w - pi_right_depth + pi_right_overhang, pi_w + pi_right_overhang, u[0] - u[1] / 2, u[0] + u[1] / 2, u[2]);
    }
    color([0.1, 0.1, 0.1]) {
        pi_part(pi_audio[0] - pi_audio[1] / 2, pi_audio[0] + pi_audio[1] / 2, -pi_audio[3], 12.5 - pi_audio[3], pi_audio[2]);
        pi_part(pi_gpio_c[0] - 25.4, pi_gpio_c[0] + 25.4, pi_gpio_c[1] - 2.54, pi_gpio_c[1] + 2.54, pi_gpio_base_h);
        pi_part(29.25 - 7.5, 29.25 + 7.5, 30.25 - 7.5, 30.25 + 7.5, 2.4);   // SoC
        pi_part(44.8, 48.2, 2.0, 24.6, 5.5);                                   // CSI
        pi_part(2.4, 5.6, 17.0, 39.0, 5.5);                                    // DSI
    }
    color([0.85, 0.7, 0.2]) pi_part(pi_gpio_c[0] - 25.4, pi_gpio_c[0] + 25.4, pi_gpio_c[1] - 2.54, pi_gpio_c[1] + 2.54, pi_gpio_h);
    // microSD socket and card on the underside, card sticking out the left edge.
    color([0.2, 0.2, 0.7]) let(a = P([-pi_sd_proud, pi_sd_y - pi_sd_w / 2]), b = P([13, pi_sd_y + pi_sd_w / 2]))
        wbox(a[0], b[0], y_pi_bot, y_pi_bot + 1.6, a[1], b[1]);
}

module bonnet() {
    color([0.1, 0.1, 0.12]) {
        a = B([0, 0]);
        translate([a[0], y_bonnet_top, a[1]]) rotate([-90, 0, 0]) mirror([0, 1, 0])
            linear_extrude(bonnet_pcb_t)
                offset(delta = bonnet_chamfer, chamfer = true) offset(delta = -bonnet_chamfer)
                    square([bonnet_w, bonnet_h]);
        // Female header under the bonnet.
        g = B([7.11, 22.61]);
        g2 = B([57.91, 30.48]);
        wbox(g[0], g2[0], y_pi_top - bonnet_gap, y_pi_top - pi_gpio_base_h, g[1], g2[1]);
    }
    color([0.15, 0.15, 0.15]) bonnet_part(bonnet_jack, bonnet_jack_h);
    color([0.1, 0.5, 0.25]) bonnet_part(bonnet_term, bonnet_term_h);
    color([0.12, 0.12, 0.12]) bonnet_part(bonnet_hub, bonnet_hub_h);
    // Ribbon IDC plug in the socket.
    color([0.25, 0.25, 0.25]) bonnet_part([bonnet_hub[0] + 1.5, bonnet_hub[1] - 1.5, bonnet_hub[2] + 1.2, bonnet_hub[3] - 1.2],
                                          bonnet_hub_h + idc_plug_proud);
}

module pi_screws() {
    // Printed snap pins: head on the board, barb in the back-wall pocket.
    if (screwless) color([0.35, 0.35, 0.38]) for (i = [0 : 3]) {
        long = i >= 2;
        xz = P(pi_holes[i]);
        y_head = long ? y_bonnet_top : y_pi_top;
        ycyl(pi_pin_head[0], y_head - pi_pin_head[1], y_head, xz);
        ycyl(pi_pin_d, y_head - eps, y_back_in - 0.2, xz);
        ycyl(pi_pin_barb, y_back_in - 0.2, y_back_in + 1.0, xz);
    }
    else color([0.7, 0.7, 0.72]) {
        for (i = [0, 1]) ycyl(2.0, y_pi_top - 1.8, y_pi_top - 1.8 + 6, P(pi_holes[i]));
        for (i = [2, 3]) ycyl(2.0, y_bonnet_top - 1.8, y_bonnet_top + 18 - 1.8, P(pi_holes[i]));
        for (i = [0, 1]) ycyl(4.5, y_pi_top - 1.8, y_pi_top, P(pi_holes[i]));
        for (i = [2, 3]) ycyl(4.5, y_bonnet_top - 1.8, y_bonnet_top, P(pi_holes[i]));
    }
    color([0.25, 0.25, 0.25]) for (i = [2, 3])
        ycyl(spacer_od, y_pi_top - bonnet_gap + 0.2, y_pi_top, P(pi_holes[i]));
}

module panel_screws() {
    // Printed: head on the post floor, split end gripping the insert.
    if (screwless) color([0.35, 0.35, 0.38]) for (m = module_x, h = panel_mounts) {
        xz = [m + h[0], h[1]];
        yh = y_panel_back + post_floor + insert_pin_head[1];
        ycyl(2.4, y_panel_back - insert_pin_grip, y_panel_back + eps, xz);
        ycyl(insert_pin_d, y_panel_back, y_panel_back + post_floor, xz);
        ycyl(insert_pin_head[0], y_panel_back + post_floor, yh, xz);
        translate([xz[0], 0, xz[1]]) wbox(-1.5, 1.5, yh - eps, yh + insert_pin_stem, -1, 1);
    }
    else color([0.7, 0.7, 0.72]) for (m = module_x, h = panel_mounts) {
        xz = [m + h[0], h[1]];
        ycyl(2.5, y_panel_back - panel_insert_depth, y_panel_back + post_floor, xz);
        ycyl(5.5, y_panel_back + post_floor, y_panel_back + post_floor + 2.0, xz);
    }
}

module barrel_plug() {
    color([0.12, 0.12, 0.12]) {
        translate([jack_face_x, jack_y, jack_z]) rotate([0, -90, 0]) cylinder(d = barrel_plug_d, h = barrel_plug_len);
        // Cable: bends toward the back and leaves through the clip.
        xe = jack_face_x - barrel_plug_len;
        r = barrel_clip_xz[0] - xe;
        translate([xe, jack_y + abs(r), jack_z]) rotate([0, 0, 180])
            rotate_extrude(angle = 90) translate([abs(r), 0]) circle(d = barrel_cable_d);
        ycyl(barrel_cable_d, jack_y + abs(r), depth + 25, barrel_clip_xz);
    }
}

module usbc_plug() {
    color([0.9, 0.9, 0.9]) {
        z_face = usbc_xz[1] - pi_usbc_overhang;
        wbox(usbc_xz[0] - usbc_plug_size[0] / 2, usbc_xz[0] + usbc_plug_size[0] / 2,
             usbc_y - usbc_plug_size[1] / 2, usbc_y + usbc_plug_size[1] / 2, z_face - usbc_plug_len, z_face);
        translate([usbc_xz[0], usbc_y, -out_h / 2 - 15]) cylinder(d = usbc_cable_d, h = z_face - usbc_plug_len + out_h / 2 + 15);
    }
}

// Ribbon route (keep-out volumes). The bonnet's socket and the panel's
// connector are at 90 degrees, so the ribbon makes one loose 90 degree
// twist-turn (no crease). Two routes:
//   direct: plug -> down -> twist-turn -> flat along the panel to INPUT.
//   u:      plug -> down into the empty space below the Pi -> soft U-turn
//           toward the back -> up behind itself -> twist-turn -> forward
//           -> flat to INPUT. The U's depth sets how much ribbon it takes.
rib_hx0 = B([bonnet_hub[0], 0])[0];
rib_hx1 = B([bonnet_hub[1], 0])[0];
rib_xc = (rib_hx0 + rib_hx1) / 2;
rib_zb = B([0, bonnet_hub[2]])[1];
rib_y_plug = y_bonnet_top - bonnet_hub_h - idc_plug_proud;
rib_y_flat = y_panel_back + 0.6;
rib_in_x = mx0 + panel_input_side * (panel_idc_x - panel_idc_size[0] / 2);
rib_x_run = rib_xc + ribbon_w / 2 + 1;                     // where the flat run starts
rib_tail = (rib_in_x - 9 - rib_x_run) + 12 + panel_idc_size[0] / 2;  // run + rise + plug
rib_twist = PI * 10 / 2 + 6;
// Direct route, plus an S-fold in depth just after the twist for spare length.
rib_direct_len = (rib_y_plug - rib_y_flat) + (rib_zb - ribbon_w / 2) + rib_twist + rib_tail;
rib_fold_x = [rib_x_run, P([pi_w - pi_right_depth + pi_right_overhang, 0])[0] - 1];
rib_fold_max = 2 * (rib_fold_x[1] - rib_fold_x[0]) + 2 * PI * ribbon_bend_r - 4 * ribbon_bend_r;
// U route: the U bottom can sit between these heights.
rib_z_twist = -ribbon_w / 2 - 1;
rib_u_lo = -cav_h / 2 + ribbon_bend_r + 3;
rib_u_hi = rib_z_twist - ribbon_bend_r - 1;
function rib_u_len(zu) = (rib_y_plug - rib_y_flat) + (rib_zb - zu) + PI * ribbon_bend_r
                         + (rib_z_twist - zu) + rib_twist + 2 * ribbon_bend_r + 8 + rib_tail;
rib_use_u = ribbon_route == "u" || (ribbon_route == "auto" && ribbon_len > rib_direct_len + rib_fold_max);
rib_zu = max(rib_u_lo, min(rib_u_hi, rib_u_hi - (ribbon_len - rib_u_len(rib_u_hi)) / 2));
echo(str("REPORT ribbon: direct route ", round(rib_direct_len), "-", round(rib_direct_len + rib_fold_max), " mm; U route ", round(rib_u_len(rib_u_hi)),
         "-", round(rib_u_len(rib_u_lo)), " mm; using ", rib_use_u ? str("U, bottom at Z=", rib_zu) : "direct",
         " for ribbon_len = ", ribbon_len));
if (rib_use_u && (ribbon_len > rib_u_len(rib_u_lo) + 10 || ribbon_len < rib_u_len(rib_u_hi) - 10))
    echo("WARNING: ribbon_len is outside the U route's range; see README (shorter ribbon).");

module ribbon() {
    y0 = rib_y_flat;
    t = ribbon_t;
    w2 = ribbon_w / 2;
    yb = y0 + 2 * ribbon_bend_r;          // rising leg of the U, behind the falling leg
    color([0.75, 0.75, 0.8, 0.85]) {
        // Over the plug top.
        wbox(rib_xc - w2, rib_xc + w2, rib_y_plug - t, rib_y_plug, rib_zb - 2, rib_zb + 9);
        if (!rib_use_u) {
            hull() {
                wbox(rib_xc - w2, rib_xc + w2, y0, rib_y_plug, rib_zb - 3, rib_zb - 2);
                wbox(rib_xc + 4, rib_xc + 8, y0, y0 + ribbon_w - 2, -w2, w2);
                wbox(rib_x_run, rib_x_run + 1, y0, y0 + t, -w2, w2);
            }
            // S-fold pocket for spare length.
            wbox(rib_fold_x[0], rib_fold_x[1], y0, y0 + 4 * ribbon_bend_r, -w2, w2);
        } else {
            // Falling leg (front layer) and the U-turn.
            hull() {
                wbox(rib_xc - w2, rib_xc + w2, y0, rib_y_plug, rib_zb - 3, rib_zb - 2);
                wbox(rib_xc - w2, rib_xc + w2, y0, y0 + t, rib_zu, rib_zu + 1);
            }
            hull() {
                wbox(rib_xc - w2, rib_xc + w2, y0, yb + t, rib_zu - ribbon_bend_r - t, rib_zu - ribbon_bend_r);
                wbox(rib_xc - w2, rib_xc + w2, y0, yb + t, rib_zu, rib_zu + 1);
            }
            // Rising leg, behind the falling one.
            wbox(rib_xc - w2, rib_xc + w2, yb, yb + t, rib_zu, rib_z_twist);
            // Twist-turn (edge-on, needs depth), then forward to the front layer.
            hull() {
                wbox(rib_xc - w2, rib_xc + w2, yb, yb + t, rib_z_twist - 1, rib_z_twist);
                wbox(rib_xc + w2 - 4, rib_xc + w2, yb - 3, yb + ribbon_w - 6, -w2, w2);
            }
            hull() {
                wbox(rib_xc + w2 - 1, rib_xc + w2, yb - 3, yb + t, -w2, w2);
                wbox(rib_x_run + 8, rib_x_run + 9, y0, y0 + t, -w2, w2);
            }
        }
        // Flat run, then a gentle rise onto the INPUT plug top.
        wbox(rib_x_run, rib_in_x - 9, y0, y0 + t, -w2, w2);
        hull() {
            wbox(rib_in_x - 10, rib_in_x - 9, y0, y0 + t, -w2, w2);
            wbox(rib_in_x - 1, rib_in_x - eps, y0 + panel_idc_proud - 1.6, y0 + panel_idc_proud - 0.6, -w2, w2);
        }
    }
}

// Panel power lead: centre connector -> gutter clip -> screw terminal.
module power_lead() {
    t = B([(bonnet_term[0] + bonnet_term[1]) / 2, bonnet_term[2]]);
    yt = y_bonnet_top - 4.5;
    yc = pwr_clip_tip_y + 0.8 + pwr_wire_d / 2;
    pts = [[mx0, y_panel_back + panel_pwr_proud - 2, -panel_pwr_size[1] / 2],
           [pwr_clip_xz[0], yc, pwr_clip_xz[1] + 6],
           [pwr_clip_xz[0], yc, pwr_clip_xz[1] - 4],
           [pwr_clip_xz[0] - 6, yc + 4, pwr_clip_xz[1] - 10],
           [t[0], yt + 6, pwr_clip_xz[1] + 2],
           [t[0], yt, t[1] - 6],
           [t[0], yt, t[1] + 2]];
    for (w = [-1, 1]) color(w < 0 ? [0.85, 0.1, 0.1] : [0.1, 0.1, 0.1])
        for (i = [0 : len(pts) - 2])
            hull() {
                translate(pts[i] + [w * pwr_wire_d / 2, 0, 0]) sphere(d = pwr_wire_d, $fn = 12);
                translate(pts[i + 1] + [w * pwr_wire_d / 2, 0, 0]) sphere(d = pwr_wire_d, $fn = 12);
            }
}

module hardware() {
    led_panel();
    panel_screws();
    pi_board();
    bonnet();
    pi_screws();
    barrel_plug();
    usbc_plug();
    ribbon();
    power_lead();
}

// The Pi stack alone (boards, parts, screws) for collision checks.
module pi_stack() { pi_board(); bonnet(); pi_screws(); }

// =============================================================================
//  Views
// =============================================================================

col_print = [0.22, 0.22, 0.24];
col_print2 = [0.30, 0.30, 0.33];
col_stand = [0.26, 0.26, 0.28];

module assembly(ex = 0) {
    translate([0, -ex, 0]) color(col_print) render(convexity = 10) bezel();
    if (use_diffuser) translate([0, -ex * 0.75, 0]) color([0.2, 0.2, 0.25, 0.6])
        wbox(-sheet_w / 2, sheet_w / 2, y_sheet, y_sheet + diffuser_t, -sheet_h / 2, sheet_h / 2);
    if (show_hardware) {
        translate([0, -ex * 0.5, 0]) { led_panel(); }
        translate([0, ex * 0.5, 0]) { pi_board(); bonnet(); pi_screws(); }
        translate([0, ex * 1.0, 0]) { panel_screws(); }
        if (ex == 0) { barrel_plug(); usbc_plug(); ribbon(); power_lead(); }
    }
    translate([0, ex, 0]) color(col_print2) render(convexity = 10) shell();
}

module on_desk(ex = 0) {
    on_stand() assembly(ex);
    if (desk_stand) translate([0, 0, -ex]) color(col_stand) render(convexity = 6) stand();
}

// Cross-section: keeps X < cut. Each item is cut separately so the cut face
// keeps the item's colour. Dimension labels sit just in front of the cut.
section_items = [
    [[0.55, 0.60, 0.72], true], [[0.62, 0.62, 0.64], true], [[0.28, 0.28, 0.32], false],
    [[0.20, 0.70, 0.30], false], [[0.20, 0.30, 0.65], false], [[0.85, 0.85, 0.88], false],
    [[0.85, 0.85, 0.88], false], [[0.10, 0.10, 0.10], false], [[0.95, 0.95, 0.95], false],
    [[0.70, 0.70, 0.95], false], [[0.85, 0.15, 0.15], false]];
module section_item(i) {
    if (i == 0) bezel();
    else if (i == 1) shell();
    else if (show_hardware) {
        if (i == 2) led_panel();
        else if (i == 3) pi_board();
        else if (i == 4) bonnet();
        else if (i == 5) pi_screws();
        else if (i == 6) panel_screws();
        else if (i == 7) barrel_plug();
        else if (i == 8) usbc_plug();
        else if (i == 9) ribbon();
        else if (i == 10) power_lead();
    }
}
section_slab = 22;
module section_view(cut) {
    for (i = [0 : len(section_items) - 1])
        color(section_items[i][0]) render(convexity = 6) intersection() {
            section_item(i);
            translate([cut - section_slab, -200, -200]) cube([section_slab, 400, 400]);
        }
    section_dims(cut + 0.5);
}
module dim_text(t, y, z, sz = 3.2) {
    translate([0, y, z]) rotate([90, 0, 90]) linear_extrude(0.2) text(t, size = sz, halign = "center", valign = "center");
}
module section_dims(x) {
    zt = out_h / 2 + 6;
    stations = [[0, "0"], [y_panel_front, ""], [y_panel_back, str(y_panel_back)], [y_pi_top, str(y_pi_top)],
                [y_back_in, ""], [depth, str(depth)]];
    color([0.85, 0.2, 0.1]) translate([x, 0, 0]) {
        translate([0, 0, zt]) cube([0.2, depth, 0.4]);
        for (s = stations) translate([0, s[0], zt - 2]) cube([0.2, 0.3, 4]);
        dim_text(str("total depth ", depth, " mm"), depth / 2, zt + 7, 3.6);
        dim_text("panel", (y_panel_front + y_panel_back) / 2, zt + 2.8, 2.6);
        dim_text("Pi + bonnet stack", (y_stack_top + y_back_in) / 2, zt + 2.8, 2.6);
        dim_text(str("panel ", panel_t), (y_panel_front + y_panel_back) / 2, -out_h / 2 - 5, 2.8);
        dim_text(str("stack ", stack_h + pi_pcb_t + pi_underside), (y_stack_top + y_back_in) / 2, -out_h / 2 - 5, 2.8);
        dim_text(str("gap ", stack_clear), y_panel_back + stack_clear / 2, -out_h / 2 - 10, 2.4);
    }
}

// Halves for parts wider than the bed (2-panel build).
module half(side) {
    intersection() {
        children();
        translate([side < 0 ? -1000 : 0, -500, -500]) cube([1000, 1000, 1000]);
    }
}

// Print orientation for each STL.
module print_bezel() { rotate([90, 0, 0]) bezel(); }                       // front face down
module print_shell() { translate([0, 0, depth]) rotate([-90, 0, 0]) shell(); } // back face down
module print_stand() { stand(); }

// The case slid forward off the stand's dovetails, to show how they attach.
module stand_slide() {
    on_stand() translate([0, -(dt_len + 6), 0]) assembly(0);
    if (desk_stand) color(col_stand) render(convexity = 6) stand();
}

if (part == "assembly") on_desk(0);
else if (part == "stand_slide") stand_slide();
else if (part == "exploded") on_desk(explode);
else if (part == "case") assembly(0);
else if (part == "section") section_view(P(pi_holes[0])[0]);
else if (part == "section2") section_view(B([(bonnet_hub[0] + bonnet_hub[1]) / 2, 0])[0]);
else if (part == "bezel") print_bezel();
else if (part == "bezel_left") half(-1) print_bezel();
else if (part == "bezel_right") half(1) print_bezel();
else if (part == "shell") print_shell();
else if (part == "shell_left") half(-1) print_shell();
else if (part == "shell_right") half(1) print_shell();
else if (part == "stand") print_stand();
// A 2-panel stand is wider than the bed: print it as two independent feet.
else if (part == "stand_left") half(-1) print_stand();
else if (part == "stand_right") half(1) print_stand();
else if (part == "spacers") spacers();
else if (part == "pins") pins();
else if (part == "snap_pins") snap_pins();
else if (part == "coupon") coupon();
else if (part == "hardware") hardware();
// ---- Collision checks: each renders the overlap volume; empty = no collision.
else if (part == "check_shell_pi") intersection() { shell(); pi_stack(); }
else if (part == "check_shell_panel") intersection() { shell(); led_panel(); }
else if (part == "check_bezel_panel") intersection() { bezel(); led_panel(); }
else if (part == "check_pi_panel") intersection() { pi_stack(); led_panel(); }
else if (part == "check_shell_plugs") intersection() { shell_body(); union() { barrel_plug(); usbc_plug(); } }
else if (part == "check_plugs_rest") intersection() { union() { barrel_plug(); usbc_plug(); } union() { pi_stack(); led_panel(); } }
else if (part == "check_shell_ribbon") intersection() { shell(); ribbon(); }
else if (part == "check_ribbon_panel") intersection() { ribbon(); led_panel(); }
else if (part == "check_ribbon_pi") intersection() { ribbon(); pi_board(); pi_screws(); }
else if (part == "check_bezel_shell") intersection() { bezel(); shell(); }
else if (part == "check_shell_lead") intersection() { shell_body(); power_lead(); }
else if (part == "check_clips_hw") intersection() { shell_clips(); union() { pi_stack(); led_panel(); ribbon(); usbc_plug(); } }
else if (part == "check_lead_ribbon") intersection() { power_lead(); ribbon(); }
else if (part == "check_stand_case") intersection() { stand(false); on_stand() union() { shell(); bezel(); } }
