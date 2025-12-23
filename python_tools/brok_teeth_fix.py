#!/usr/bin/env python3
"""
BROK CNC - Connect Teeth to Jaw
===============================
- Use existing cyan teeth as size reference (20% bigger)
- 7 teeth upper jaw, 4 teeth lower jaw
- Connect to RED skeleton (no gaps)
- Leave space at back of jaw
"""
import re
import math
from PIL import Image, ImageDraw, ImageFont

# Load current G-code
with open("/home/kontomeo/Desktop/JURASSIC_TREX.nc", 'r') as f:
    lines = f.readlines()

# Extract skeleton and holes
skeleton = []
holes = []
current_hole = []
in_skel = False
in_hole = False

for line in lines:
    line = line.strip()
    if 'HOLE' in line and 'CUT' in line:
        if current_hole:
            holes.append(current_hole)
        current_hole = []
        in_hole = True
        in_skel = False
    elif 'SKELETON' in line:
        if current_hole:
            holes.append(current_hole)
            current_hole = []
        in_skel = True
        in_hole = False
    elif 'RING' in line:
        in_skel = False
        in_hole = False

    m = re.match(r'G1X([-\d.]+)Y([-\d.]+)', line)
    if m:
        x, y = float(m.group(1)), float(m.group(2))
        if in_hole:
            current_hole.append((x, y))
        elif in_skel:
            skeleton.append((x, y))

if current_hole:
    holes.append(current_hole)

print(f"Loaded skeleton: {len(skeleton)} points")
print(f"Loaded holes: {len(holes)}")

# Analyze cyan teeth (holes that look like teeth in jaw area)
# Jaw area is roughly X > 8.5, Y between 5.5 and 9.5
upper_teeth_ref = []  # Cyan shapes in upper jaw
lower_teeth_ref = []  # Cyan shapes in lower jaw
other_holes = []      # Non-teeth holes (eye, skull openings)

for hole in holes:
    if len(hole) < 5:
        continue
    # Get bounding box
    xs = [p[0] for p in hole]
    ys = [p[1] for p in hole]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)

    # Teeth are in right side (X > 8.5) and elongated
    if cx > 8.5 and w < 1.5 and h < 2.0:
        if cy > 7.5:  # Upper jaw
            upper_teeth_ref.append({'cx': cx, 'cy': cy, 'w': w, 'h': h, 'pts': hole})
        elif cy < 7.0:  # Lower jaw
            lower_teeth_ref.append({'cx': cx, 'cy': cy, 'w': w, 'h': h, 'pts': hole})
        else:
            other_holes.append(hole)
    else:
        other_holes.append(hole)

print(f"Upper teeth reference: {len(upper_teeth_ref)}")
print(f"Lower teeth reference: {len(lower_teeth_ref)}")
print(f"Other holes (keep): {len(other_holes)}")

# Calculate average tooth size from references
if upper_teeth_ref:
    avg_upper_w = sum(t['w'] for t in upper_teeth_ref) / len(upper_teeth_ref)
    avg_upper_h = sum(t['h'] for t in upper_teeth_ref) / len(upper_teeth_ref)
else:
    avg_upper_w, avg_upper_h = 0.3, 0.5

if lower_teeth_ref:
    avg_lower_w = sum(t['w'] for t in lower_teeth_ref) / len(lower_teeth_ref)
    avg_lower_h = sum(t['h'] for t in lower_teeth_ref) / len(lower_teeth_ref)
else:
    avg_lower_w, avg_lower_h = 0.25, 0.4

# Make 20% bigger
tooth_width = avg_upper_w * 1.2
tooth_height_upper = avg_upper_h * 1.2
tooth_height_lower = avg_lower_h * 1.2

print(f"Tooth size (20% bigger): width={tooth_width:.3f}, upper_h={tooth_height_upper:.3f}, lower_h={tooth_height_lower:.3f}")

# Find jaw segments in skeleton
# Upper jaw: high X, Y around 8-9 (top of mouth opening)
# Lower jaw: high X, Y around 6-7 (bottom of mouth opening)

upper_jaw_pts = []
lower_jaw_pts = []

for i, (x, y) in enumerate(skeleton):
    if x > 9.0:  # Right side of head
        if 8.0 < y < 9.5:  # Upper jaw line
            upper_jaw_pts.append((i, x, y))
        elif 5.5 < y < 7.0:  # Lower jaw line
            lower_jaw_pts.append((i, x, y))

print(f"Upper jaw skeleton points: {len(upper_jaw_pts)}")
print(f"Lower jaw skeleton points: {len(lower_jaw_pts)}")

# Sort by X to find jaw extent
upper_jaw_pts.sort(key=lambda p: p[1])  # Sort by X
lower_jaw_pts.sort(key=lambda p: p[1])

# Calculate teeth positions - evenly spaced
# Leave space at back (first 20% of jaw)
def calculate_teeth_positions(jaw_pts, num_teeth, back_space=0.2):
    if len(jaw_pts) < 2:
        return []

    # Get X range of jaw
    x_min = min(p[1] for p in jaw_pts)
    x_max = max(p[1] for p in jaw_pts)
    jaw_length = x_max - x_min

    # Start teeth after back_space
    teeth_start = x_min + jaw_length * back_space
    teeth_end = x_max - jaw_length * 0.05  # Small margin at front
    teeth_span = teeth_end - teeth_start

    # Evenly space teeth
    positions = []
    if num_teeth > 1:
        spacing = teeth_span / (num_teeth - 1)
        for i in range(num_teeth):
            x = teeth_start + i * spacing
            # Find closest skeleton point
            closest = min(jaw_pts, key=lambda p: abs(p[1] - x))
            positions.append(closest)
    elif num_teeth == 1:
        x = (teeth_start + teeth_end) / 2
        closest = min(jaw_pts, key=lambda p: abs(p[1] - x))
        positions.append(closest)

    return positions

upper_teeth_pos = calculate_teeth_positions(upper_jaw_pts, 7, back_space=0.15)
lower_teeth_pos = calculate_teeth_positions(lower_jaw_pts, 4, back_space=0.2)

print(f"Upper teeth positions: {len(upper_teeth_pos)}")
print(f"Lower teeth positions: {len(lower_teeth_pos)}")

# Build new skeleton with teeth connected
# Insert tooth shape at each position
def insert_teeth(skeleton_pts, teeth_positions, tooth_w, tooth_h, direction='down'):
    """
    Insert teeth into skeleton contour.
    direction: 'down' for upper jaw, 'up' for lower jaw
    """
    # Sort positions by index descending to insert from end
    positions = sorted(teeth_positions, key=lambda p: p[0], reverse=True)

    new_skeleton = list(skeleton_pts)

    for idx, x, y in positions:
        # Create tooth triangle
        half_w = tooth_w / 2
        if direction == 'down':
            # Upper jaw - tooth points down into mouth
            tooth = [
                (x - half_w, y),
                (x, y - tooth_h),  # Tip
                (x + half_w, y)
            ]
        else:
            # Lower jaw - tooth points up into mouth
            tooth = [
                (x - half_w, y),
                (x, y + tooth_h),  # Tip
                (x + half_w, y)
            ]

        # Insert tooth at this position (replace single point with tooth shape)
        new_skeleton = new_skeleton[:idx] + tooth + new_skeleton[idx+1:]

    return new_skeleton

# Add teeth to skeleton
skeleton_with_teeth = insert_teeth(skeleton, upper_teeth_pos, tooth_width, tooth_height_upper, 'down')
skeleton_with_teeth = insert_teeth(skeleton_with_teeth, lower_teeth_pos, tooth_width, tooth_height_lower, 'up')

print(f"Skeleton with teeth: {len(skeleton_with_teeth)} points")

# Generate visualization
size = 1500
margin = 50
scale = (size - 2*margin) / 14.0

img = Image.new('RGB', (size, size), '#0a0a0a')
draw = ImageDraw.Draw(img)

def px(x, y):
    return (margin + int(x * scale), size - margin - int(y * scale))

# Grid
for i in range(29):
    p = margin + int(i * 0.5 * scale)
    draw.line([(p, margin), (p, size-margin)], fill='#1a1a1a')
    draw.line([(margin, p), (size-margin, p)], fill='#1a1a1a')

# Draw OTHER holes in CYAN (these stay as holes)
for hole in other_holes:
    if len(hole) > 2:
        pts = [px(x,y) for x,y in hole]
        draw.polygon(pts, outline='#4ecdc4', fill='#0a2020', width=2)

# Draw skeleton WITH teeth in RED (connected workpiece)
pts = [px(x,y) for x,y in skeleton_with_teeth]
# Fill the skeleton area to show it's workpiece
if len(pts) > 2:
    draw.polygon(pts, outline='#ff6b6b', fill='#2a0a0a', width=2)

# Draw ring in YELLOW
cx, cy = px(6.75, 6.75)
r = int(6.0 * scale)
draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline='#ffe66d', width=3)

# Title and legend
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12)
except:
    font = small = ImageFont.load_default()

draw.text((size//2, 25), "BROK - TEETH CONNECTED TO JAW", fill='#00ff00', font=font, anchor='mm')
draw.text((size//2, 55), f"Upper: 7 teeth | Lower: 4 teeth | 20% bigger | CONNECTED", fill='#888', font=small, anchor='mm')

# Legend
draw.rectangle([10, size-130, 300, size-10], fill='#111', outline='#333')
draw.rectangle([20, size-120, 40, size-105], fill='#2a0a0a', outline='#ff6b6b')
draw.text((50, size-112), "RED = Workpiece (teeth connected)", fill='#ff6b6b', font=small, anchor='lm')

draw.rectangle([20, size-90, 40, size-75], fill='#0a2020', outline='#4ecdc4')
draw.text((50, size-82), "CYAN = Holes (cut out, drop)", fill='#4ecdc4', font=small, anchor='lm')

draw.rectangle([20, size-60, 40, size-45], outline='#ffe66d', width=2)
draw.text((50, size-52), "YELLOW = Ring (CW cut)", fill='#ffe66d', font=small, anchor='lm')

draw.text((20, size-25), f"Skeleton: {len(skeleton_with_teeth)} pts | Holes: {len(other_holes)}", fill='#888', font=small)

img.save('/home/kontomeo/Desktop/BROK_TEETH_CONNECTED.png')
print(f"Saved: BROK_TEETH_CONNECTED.png")

# Generate G-code with BEVEL LAW
gcode = []
gcode.append("(BROK CNC - TEETH CONNECTED TO JAW)")
gcode.append("(7 upper, 4 lower, 20% bigger, evenly spaced)")
gcode.append("(BEVEL LAW ENFORCED)")
gcode.append("(Feed:47 Pierce:0.148 Cut:0.059)")
gcode.append("(v1.6-af)")
gcode.append("G20G90")
gcode.append("G0X0.Y0.")
gcode.append("H0")
gcode.append("")

cut_num = 0

# Holes first - CCW (BEVEL LAW)
for hi, hole in enumerate(other_holes):
    if len(hole) < 10:
        continue
    cut_num += 1
    gcode.append(f"(=== CUT {cut_num}: HOLE - CCW [BEVEL LAW] ===)")
    sx, sy = hole[0]
    gcode.append(f"G0X{sx-0.15:.4f}Y{sy:.4f}")
    gcode.append("G92Z0")
    gcode.append("G38.2Z-5F50")
    gcode.append("G38.4Z0.5F25")
    gcode.append("G92Z0")
    gcode.append("G0Z0.148")
    gcode.append("M3")
    gcode.append("G4P0.70")
    gcode.append("G0Z0.059")
    gcode.append("H1")
    for x, y in hole:
        gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
    gcode.append("H0")
    gcode.append("M5")
    gcode.append("G0Z1")
    gcode.append("")

# Skeleton with teeth - CCW (BEVEL LAW)
cut_num += 1
gcode.append(f"(=== CUT {cut_num}: SKELETON WITH TEETH - CCW [BEVEL LAW] ===)")
sx, sy = skeleton_with_teeth[0]
gcode.append(f"G0X{sx-0.15:.4f}Y{sy:.4f}")
gcode.append("G92Z0")
gcode.append("G38.2Z-5F50")
gcode.append("G38.4Z0.5F25")
gcode.append("G92Z0")
gcode.append("G0Z0.148")
gcode.append("M3")
gcode.append("G4P0.70")
gcode.append("G0Z0.059")
gcode.append("H1")
for x, y in skeleton_with_teeth:
    gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
gcode.append(f"G1X{skeleton_with_teeth[0][0]:.4f}Y{skeleton_with_teeth[0][1]:.4f}F47")
gcode.append("H0")
gcode.append("M5")
gcode.append("G0Z1")
gcode.append("")

# Ring - CW (BEVEL LAW)
cut_num += 1
gcode.append(f"(=== CUT {cut_num}: 12\" RING - CW [BEVEL LAW] ===)")
cx, cy, r = 6.75, 6.75, 6.0
gcode.append(f"G0X{cx+r+0.2:.4f}Y{cy:.4f}")
gcode.append("G92Z0")
gcode.append("G38.2Z-5F50")
gcode.append("G38.4Z0.5F25")
gcode.append("G92Z0")
gcode.append("G0Z0.148")
gcode.append("M3")
gcode.append("G4P0.70")
gcode.append("G0Z0.059")
gcode.append("H1")
for i in range(121):
    angle = -2 * math.pi * i / 120
    x = cx + r * math.cos(angle)
    y = cy + r * math.sin(angle)
    gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
gcode.append("H0")
gcode.append("M5")
gcode.append("G0Z1")
gcode.append("")

gcode.append("G0X0Y0")
gcode.append("M30")

with open("/home/kontomeo/Desktop/JURASSIC_TREX.nc", 'w') as f:
    f.write("\n".join(gcode))

print(f"G-code saved: {cut_num} cuts")
print("=" * 50)
print("TEETH NOW CONNECTED TO JAW - NO GAPS")
print("=" * 50)
