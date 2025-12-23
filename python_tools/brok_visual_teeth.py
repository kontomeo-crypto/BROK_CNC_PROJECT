#!/usr/bin/env python3
"""
BROK CNC - Visual Teeth Placement
=================================
Step 1: Remove cyan teeth (keep only real holes)
Step 2: Add red teeth connected to jaw
Based on visual analysis of mouth location
"""
import re
import math
from PIL import Image, ImageDraw, ImageFont
import shutil

# BACKUP FIRST
shutil.copy("/home/kontomeo/Desktop/JURASSIC_TREX.nc",
            "/home/kontomeo/Desktop/BROK_BACKUPS/v1_before_teeth.nc")
print("[BACKUP] Saved v1_before_teeth.nc")

# Load clean G-code
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

print(f"[LOAD] Skeleton: {len(skeleton)} points")
print(f"[LOAD] Total holes: {len(holes)}")

# STEP 1: Remove cyan teeth - keep only real holes
# Real holes: eye socket, skull openings (large, not in jaw area)
# Teeth shapes: small, elongated, in jaw area (X > 8.5)

real_holes = []
removed_teeth = 0

for hole in holes:
    if len(hole) < 5:
        continue

    xs = [p[0] for p in hole]
    ys = [p[1] for p in hole]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    area = w * h

    # Teeth are: small, in jaw area (right side X > 8.5)
    # Real holes are: larger, not specifically in narrow jaw zone

    is_tooth = (cx > 8.5 and area < 0.8 and (w < 0.5 or h < 0.8))

    if is_tooth:
        removed_teeth += 1
        print(f"[REMOVE] Cyan tooth at ({cx:.2f}, {cy:.2f}) size {w:.2f}x{h:.2f}")
    else:
        real_holes.append(hole)
        print(f"[KEEP] Hole at ({cx:.2f}, {cy:.2f}) size {w:.2f}x{h:.2f}")

print(f"[STEP 1] Removed {removed_teeth} cyan teeth, kept {len(real_holes)} real holes")

# STEP 2: Add RED teeth to skeleton
# Visual analysis shows:
# - Upper jaw: along snout, Y around 8.5-9.5, X from 9.5 to 11.5
# - Lower jaw: below mouth opening, Y around 7.0-7.8, X from 9.0 to 11.0
# - Mouth gap is between Y ~7.8 and Y ~8.5

# Find jaw points in skeleton
upper_jaw_pts = []
lower_jaw_pts = []

for i, (x, y) in enumerate(skeleton):
    # Upper jaw: top of mouth opening
    if x > 9.5 and x < 11.8 and y > 8.3 and y < 9.8:
        upper_jaw_pts.append((i, x, y))
    # Lower jaw: bottom of mouth opening (NOT tail which is Y < 6)
    elif x > 9.0 and x < 11.5 and y > 7.0 and y < 8.0:
        lower_jaw_pts.append((i, x, y))

print(f"[FIND] Upper jaw points: {len(upper_jaw_pts)}")
print(f"[FIND] Lower jaw points: {len(lower_jaw_pts)}")

# Create teeth positions - evenly spaced
def get_teeth_positions(jaw_pts, num_teeth):
    if len(jaw_pts) < num_teeth:
        return jaw_pts

    # Sort by X
    sorted_pts = sorted(jaw_pts, key=lambda p: p[1])

    # Select evenly spaced points
    step = len(sorted_pts) // num_teeth
    positions = []
    for i in range(num_teeth):
        idx = min(i * step, len(sorted_pts) - 1)
        positions.append(sorted_pts[idx])

    return positions

upper_teeth = get_teeth_positions(upper_jaw_pts, 7)
lower_teeth = get_teeth_positions(lower_jaw_pts, 4)

print(f"[TEETH] Upper: {len(upper_teeth)} positions")
print(f"[TEETH] Lower: {len(lower_teeth)} positions")

# Insert teeth into skeleton
# Tooth size: 20% bigger than reference (~0.3 wide, ~0.4 tall)
tooth_w = 0.35
tooth_h = 0.45

def add_teeth_to_skeleton(skel, teeth_pos, direction):
    """Add teeth by inserting triangle points at jaw positions"""
    new_skel = list(skel)

    # Sort by index descending to insert from end
    sorted_teeth = sorted(teeth_pos, key=lambda p: p[0], reverse=True)

    for idx, x, y in sorted_teeth:
        half_w = tooth_w / 2
        if direction == 'down':
            # Upper jaw - point into mouth (down)
            tooth = [
                (x - half_w, y),
                (x, y - tooth_h),
                (x + half_w, y)
            ]
        else:
            # Lower jaw - point into mouth (up)
            tooth = [
                (x - half_w, y),
                (x, y + tooth_h),
                (x + half_w, y)
            ]

        # Replace single point with tooth triangle
        new_skel = new_skel[:idx] + tooth + new_skel[idx+1:]
        print(f"[ADD] Tooth at ({x:.2f}, {y:.2f}) pointing {direction}")

    return new_skel

skeleton_with_teeth = add_teeth_to_skeleton(skeleton, upper_teeth, 'down')
skeleton_with_teeth = add_teeth_to_skeleton(skeleton_with_teeth, lower_teeth, 'up')

print(f"[STEP 2] Skeleton with teeth: {len(skeleton_with_teeth)} points")

# GENERATE IMAGE
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

# Draw REAL holes in CYAN (not teeth)
for hole in real_holes:
    if len(hole) > 2:
        pts = [px(x,y) for x,y in hole]
        draw.polygon(pts, outline='#4ecdc4', fill='#0a2020', width=2)

# Draw skeleton with RED teeth
pts = [px(x,y) for x,y in skeleton_with_teeth]
if len(pts) > 2:
    draw.polygon(pts, outline='#ff6b6b', fill='#2a0a0a', width=2)

# Ring
cx, cy = px(6.75, 6.75)
r = int(6.0 * scale)
draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline='#ffe66d', width=3)

# Title
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12)
except:
    font = small = ImageFont.load_default()

draw.text((size//2, 25), "BROK - RED TEETH (Cyan teeth removed)", fill='#00ff00', font=font, anchor='mm')
draw.text((size//2, 55), f"Upper: {len(upper_teeth)} | Lower: {len(lower_teeth)} | Connected to RED",
          fill='#888', font=small, anchor='mm')

# Legend
draw.rectangle([10, size-100, 350, size-10], fill='#111', outline='#333')
draw.rectangle([20, size-90, 40, size-75], fill='#2a0a0a', outline='#ff6b6b')
draw.text((50, size-82), "RED = Workpiece + Teeth (connected)", fill='#ff6b6b', font=small, anchor='lm')
draw.rectangle([20, size-65, 40, size-50], fill='#0a2020', outline='#4ecdc4')
draw.text((50, size-57), "CYAN = Holes only (teeth removed)", fill='#4ecdc4', font=small, anchor='lm')
draw.text((20, size-30), f"Skeleton: {len(skeleton_with_teeth)} pts | Holes: {len(real_holes)}", fill='#888', font=small)

img.save('/home/kontomeo/Desktop/BROK_RED_TEETH.png')
print(f"\n[SAVED] BROK_RED_TEETH.png")

# Save G-code
gcode = []
gcode.append("(BROK CNC - RED TEETH CONNECTED)")
gcode.append("(Cyan teeth removed, RED teeth on jaw)")
gcode.append("(BEVEL LAW ENFORCED)")
gcode.append("(Feed:47 Pierce:0.148 Cut:0.059)")
gcode.append("(v1.6-af)")
gcode.append("G20G90")
gcode.append("G0X0.Y0.")
gcode.append("H0")
gcode.append("")

cut_num = 0

# Real holes - CCW
for hole in real_holes:
    if len(hole) < 10:
        continue
    cut_num += 1
    gcode.append(f"(=== CUT {cut_num}: HOLE - CCW ===)")
    sx, sy = hole[0]
    gcode.append(f"G0X{sx-0.15:.4f}Y{sy:.4f}")
    gcode.append("G92Z0\nG38.2Z-5F50\nG38.4Z0.5F25\nG92Z0")
    gcode.append("G0Z0.148\nM3\nG4P0.70\nG0Z0.059\nH1")
    for x, y in hole:
        gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
    gcode.append("H0\nM5\nG0Z1\n")

# Skeleton with teeth - CCW
cut_num += 1
gcode.append(f"(=== CUT {cut_num}: SKELETON WITH TEETH - CCW ===)")
sx, sy = skeleton_with_teeth[0]
gcode.append(f"G0X{sx-0.15:.4f}Y{sy:.4f}")
gcode.append("G92Z0\nG38.2Z-5F50\nG38.4Z0.5F25\nG92Z0")
gcode.append("G0Z0.148\nM3\nG4P0.70\nG0Z0.059\nH1")
for x, y in skeleton_with_teeth:
    gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
gcode.append(f"G1X{skeleton_with_teeth[0][0]:.4f}Y{skeleton_with_teeth[0][1]:.4f}F47")
gcode.append("H0\nM5\nG0Z1\n")

# Ring - CW
cut_num += 1
gcode.append(f"(=== CUT {cut_num}: 12\" RING - CW ===)")
gcode.append(f"G0X{6.75+6.2:.4f}Y6.7500")
gcode.append("G92Z0\nG38.2Z-5F50\nG38.4Z0.5F25\nG92Z0")
gcode.append("G0Z0.148\nM3\nG4P0.70\nG0Z0.059\nH1")
for i in range(121):
    angle = -2 * math.pi * i / 120
    x = 6.75 + 6.0 * math.cos(angle)
    y = 6.75 + 6.0 * math.sin(angle)
    gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
gcode.append("H0\nM5\nG0Z1\n")
gcode.append("G0X0Y0\nM30")

with open("/home/kontomeo/Desktop/JURASSIC_TREX.nc", 'w') as f:
    f.write("\n".join(gcode))

# Backup this version
shutil.copy("/home/kontomeo/Desktop/JURASSIC_TREX.nc",
            "/home/kontomeo/Desktop/BROK_BACKUPS/v2_red_teeth.nc")
shutil.copy("/home/kontomeo/Desktop/BROK_RED_TEETH.png",
            "/home/kontomeo/Desktop/BROK_BACKUPS/v2_red_teeth.png")

print(f"[SAVED] G-code: {cut_num} cuts")
print(f"[BACKUP] v2_red_teeth saved")
print("\n" + "="*50)
print("CYAN TEETH REMOVED - RED TEETH ADDED")
print("="*50)
