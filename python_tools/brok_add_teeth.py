#!/usr/bin/env python3
"""
BROK CNC - Add Teeth to Clean Skeleton
=======================================
- Load clean skeleton from backup
- Add 7 upper teeth, 4 lower teeth as triangles
- 15% bigger than original reference
- Connected to jaw (part of skeleton contour)
"""
import re
import math
from PIL import Image, ImageDraw, ImageFont
import shutil

# Load CLEAN skeleton from backup
with open("/home/kontomeo/Desktop/BROK_BACKUPS/v0_CLEAN.nc", 'r') as f:
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

print(f"[LOAD] Clean skeleton: {len(skeleton)} points")
print(f"[LOAD] Holes: {len(holes)}")

# Find upper jaw and lower jaw segments
# Upper jaw: right side (X > 9), Y around 8.5-9.5
# Lower jaw: right side (X > 9), Y around 6.8-7.8

upper_jaw_indices = []
lower_jaw_indices = []

for i, (x, y) in enumerate(skeleton):
    if x > 9.0 and x < 11.5:
        if 8.3 < y < 9.8:
            upper_jaw_indices.append(i)
        elif 6.8 < y < 7.8:
            lower_jaw_indices.append(i)

print(f"[JAW] Upper jaw points: {len(upper_jaw_indices)}")
print(f"[JAW] Lower jaw points: {len(lower_jaw_indices)}")

# Select evenly spaced positions for teeth
def select_positions(indices, skeleton, count):
    if len(indices) < count:
        return [(i, skeleton[i][0], skeleton[i][1]) for i in indices]

    # Sort by X to get jaw from back to front
    sorted_idx = sorted(indices, key=lambda i: skeleton[i][0])

    # Skip first 15% (back of jaw - no teeth)
    start = int(len(sorted_idx) * 0.15)
    end = len(sorted_idx) - 1

    positions = []
    step = (end - start) / (count - 1) if count > 1 else 0

    for i in range(count):
        idx = sorted_idx[int(start + i * step)]
        x, y = skeleton[idx]
        positions.append((idx, x, y))

    return positions

upper_positions = select_positions(upper_jaw_indices, skeleton, 7)
lower_positions = select_positions(lower_jaw_indices, skeleton, 4)

print(f"[TEETH] Upper positions: {len(upper_positions)}")
print(f"[TEETH] Lower positions: {len(lower_positions)}")

# Tooth dimensions (15% bigger than typical 0.3x0.4)
tooth_w = 0.35 * 1.15  # ~0.40
tooth_h = 0.45 * 1.15  # ~0.52

print(f"[SIZE] Tooth: {tooth_w:.2f}\" wide x {tooth_h:.2f}\" tall (15% bigger)")

# Insert teeth into skeleton
# Work backwards (high index first) so insertions don't shift later indices

def insert_teeth(skel, positions, direction):
    """
    Insert tooth triangles into skeleton contour.
    direction: 'down' for upper jaw, 'up' for lower jaw
    """
    new_skel = list(skel)

    # Sort by index descending
    sorted_pos = sorted(positions, key=lambda p: p[0], reverse=True)

    for idx, x, y in sorted_pos:
        half_w = tooth_w / 2

        if direction == 'down':
            # Upper jaw - tooth points DOWN into mouth
            tooth = [
                (x - half_w, y),      # Left base
                (x, y - tooth_h),     # Tip (down)
                (x + half_w, y)       # Right base
            ]
        else:
            # Lower jaw - tooth points UP into mouth
            tooth = [
                (x - half_w, y),      # Left base
                (x, y + tooth_h),     # Tip (up)
                (x + half_w, y)       # Right base
            ]

        # Replace single point with 3-point tooth
        new_skel = new_skel[:idx] + tooth + new_skel[idx+1:]
        print(f"[INSERT] Tooth at ({x:.2f}, {y:.2f}) -> {direction}")

    return new_skel

# Add teeth to skeleton
skeleton_teeth = insert_teeth(skeleton, upper_positions, 'down')
skeleton_teeth = insert_teeth(skeleton_teeth, lower_positions, 'up')

print(f"[RESULT] Skeleton with teeth: {len(skeleton_teeth)} points")

# Generate QC image
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

# T-Rex skeleton in RED (workpiece STAYS)
pts = [px(x,y) for x,y in skeleton_teeth]
if len(pts) > 2:
    draw.polygon(pts, outline='#ff6b6b', fill='#2a0a0a', width=2)

# Holes in CYAN (cut out REMOVED)
for hole in holes:
    if len(hole) > 2:
        hpts = [px(x,y) for x,y in hole]
        draw.polygon(hpts, outline='#4ecdc4', fill='#0a2020', width=2)

# Ring in YELLOW
cx, cy = px(6.75, 6.75)
r = int(6.0 * scale)
draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline='#ffe66d', width=3)

# Title
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12)
except:
    font = small = ImageFont.load_default()

draw.text((size//2, 25), "BROK - TEETH ADDED TO JAW", fill='#00ff00', font=font, anchor='mm')
draw.text((size//2, 55), f"Upper: 7 | Lower: 4 | 15% bigger | CONNECTED to jaw",
          fill='#888', font=small, anchor='mm')

# Legend
draw.rectangle([10, size-100, 380, size-10], fill='#111', outline='#333')
draw.rectangle([20, size-90, 40, size-75], fill='#2a0a0a', outline='#ff6b6b')
draw.text((50, size-82), "RED = T-Rex + Teeth (workpiece STAYS)", fill='#ff6b6b', font=small, anchor='lm')
draw.rectangle([20, size-65, 40, size-50], fill='#0a2020', outline='#4ecdc4')
draw.text((50, size-57), "CYAN = Holes (cut out, REMOVED)", fill='#4ecdc4', font=small, anchor='lm')
draw.rectangle([20, size-40, 40, size-25], outline='#ffe66d', width=2)
draw.text((50, size-32), "YELLOW = Ring (CW cut)", fill='#ffe66d', font=small, anchor='lm')

img.save('/home/kontomeo/Desktop/BROK_TEETH_ADDED.png')
print(f"\n[SAVED] BROK_TEETH_ADDED.png")

# Generate G-code
gcode = []
gcode.append("(BROK CNC - TEETH CONNECTED TO JAW)")
gcode.append("(7 upper, 4 lower, 15% bigger)")
gcode.append("(BEVEL LAW ENFORCED)")
gcode.append("(Feed:47 Pierce:0.148 Cut:0.059)")
gcode.append("(v1.6-af)")
gcode.append("G20G90")
gcode.append("G0X0.Y0.")
gcode.append("H0")
gcode.append("")

cut_num = 0

# Holes first - CCW (inside cuts)
for hole in holes:
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
sx, sy = skeleton_teeth[0]
gcode.append(f"G0X{sx-0.15:.4f}Y{sy:.4f}")
gcode.append("G92Z0\nG38.2Z-5F50\nG38.4Z0.5F25\nG92Z0")
gcode.append("G0Z0.148\nM3\nG4P0.70\nG0Z0.059\nH1")
for x, y in skeleton_teeth:
    gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
gcode.append(f"G1X{skeleton_teeth[0][0]:.4f}Y{skeleton_teeth[0][1]:.4f}F47")
gcode.append("H0\nM5\nG0Z1\n")

# Ring - CW (outside cut)
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

# Backup
shutil.copy("/home/kontomeo/Desktop/JURASSIC_TREX.nc",
            "/home/kontomeo/Desktop/BROK_BACKUPS/v5_teeth_added.nc")
shutil.copy("/home/kontomeo/Desktop/BROK_TEETH_ADDED.png",
            "/home/kontomeo/Desktop/BROK_BACKUPS/v5_teeth_added.png")

print(f"[SAVED] G-code: {cut_num} cuts")
print(f"[BACKUP] v5_teeth_added saved")
print("\n" + "="*50)
print("TEETH ADDED: 7 upper + 4 lower")
print("15% bigger, CONNECTED to RED skeleton")
print("="*50)
