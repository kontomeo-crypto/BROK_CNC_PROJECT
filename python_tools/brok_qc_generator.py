#!/usr/bin/env python3
"""
BROK CNC - QC Sample Generator
==============================
Creates QC (Quality Control) image for approval.
- Shows clean T-Rex skeleton
- DRAWS proposed teeth (7 upper, 4 lower)
- User reviews and approves QC
- Then BROK CNC traces QC to generate G-code

This is the DESIGN PHASE - no G-code changes yet.
"""
import re
import math
from PIL import Image, ImageDraw, ImageFont

print("="*60)
print("BROK CNC - QC SAMPLE GENERATOR")
print("="*60)

# Load clean skeleton
with open("/home/kontomeo/Desktop/JURASSIC_TREX.nc", 'r') as f:
    lines = f.readlines()

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

# Find jaw points for teeth placement
upper_jaw = []  # (index, x, y)
lower_jaw = []

for i, (x, y) in enumerate(skeleton):
    if x > 9.0 and x < 11.8:
        if 8.2 < y < 9.8:
            upper_jaw.append((i, x, y))
        elif 6.8 < y < 7.9:
            lower_jaw.append((i, x, y))

print(f"[JAW] Upper jaw candidates: {len(upper_jaw)}")
print(f"[JAW] Lower jaw candidates: {len(lower_jaw)}")

# Select teeth positions (evenly spaced, leave back empty)
def select_teeth_pos(jaw_pts, count):
    if len(jaw_pts) < count:
        return jaw_pts

    sorted_pts = sorted(jaw_pts, key=lambda p: p[1])  # Sort by X

    # Skip first 15% (back of jaw)
    start = int(len(sorted_pts) * 0.15)
    end = len(sorted_pts) - 1

    positions = []
    step = (end - start) / (count - 1) if count > 1 else 0

    for i in range(count):
        idx = int(start + i * step)
        positions.append(sorted_pts[idx])

    return positions

upper_teeth_pos = select_teeth_pos(upper_jaw, 7)
lower_teeth_pos = select_teeth_pos(lower_jaw, 4)

print(f"[TEETH] Upper: {len(upper_teeth_pos)} positions selected")
print(f"[TEETH] Lower: {len(lower_teeth_pos)} positions selected")

# Tooth dimensions (15% bigger)
tooth_w = 0.40
tooth_h = 0.52

# Generate QC Image
size = 1800
margin = 60
scale = (size - 2*margin) / 14.0

img = Image.new('RGB', (size, size), '#0a0a0a')
draw = ImageDraw.Draw(img)

def px(x, y):
    return (margin + int(x * scale), size - margin - int(y * scale))

# Grid with labels
for i in range(29):
    val = i * 0.5
    p = margin + int(val * scale)
    color = '#2a2a2a' if i % 2 == 0 else '#1a1a1a'
    draw.line([(p, margin), (p, size-margin)], fill=color)
    draw.line([(margin, p), (size-margin, p)], fill=color)

# Draw T-Rex skeleton in RED (workpiece)
pts = [px(x,y) for x,y in skeleton]
if len(pts) > 2:
    draw.polygon(pts, outline='#ff6b6b', fill='#2a0a0a', width=3)

# Draw holes in CYAN (removed)
for hole in holes:
    if len(hole) > 2:
        hpts = [px(x,y) for x,y in hole]
        draw.polygon(hpts, outline='#4ecdc4', fill='#0a2020', width=2)

# Draw PROPOSED TEETH in GREEN (for QC review)
print("\n[QC] Drawing proposed teeth:")

for i, (idx, x, y) in enumerate(upper_teeth_pos):
    # Upper jaw - tooth points DOWN
    half_w = tooth_w / 2
    tooth = [
        px(x - half_w, y),
        px(x, y - tooth_h),
        px(x + half_w, y)
    ]
    draw.polygon(tooth, outline='#00ff00', fill='#0a3a0a', width=2)
    print(f"  Upper tooth {i+1}: ({x:.2f}, {y:.2f}) -> DOWN")

for i, (idx, x, y) in enumerate(lower_teeth_pos):
    # Lower jaw - tooth points UP
    half_w = tooth_w / 2
    tooth = [
        px(x - half_w, y),
        px(x, y + tooth_h),
        px(x + half_w, y)
    ]
    draw.polygon(tooth, outline='#00ff00', fill='#0a3a0a', width=2)
    print(f"  Lower tooth {i+1}: ({x:.2f}, {y:.2f}) -> UP")

# Draw ring in YELLOW
cx, cy = px(6.75, 6.75)
r = int(6.0 * scale)
draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline='#ffe66d', width=3)

# Title and info
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    med = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)
except:
    font = med = small = ImageFont.load_default()

draw.text((size//2, 30), "BROK CNC - QC SAMPLE", fill='#00ff00', font=font, anchor='mm')
draw.text((size//2, 60), "Review teeth placement before tracing", fill='#ffff00', font=med, anchor='mm')
draw.text((size//2, 90), f"Upper: 7 teeth | Lower: 4 teeth | 15% bigger | GREEN = proposed",
          fill='#888', font=small, anchor='mm')

# Legend
draw.rectangle([10, size-140, 420, size-10], fill='#111', outline='#444')
draw.rectangle([20, size-130, 45, size-110], fill='#2a0a0a', outline='#ff6b6b', width=2)
draw.text((55, size-120), "RED = T-Rex skeleton (workpiece STAYS)", fill='#ff6b6b', font=small, anchor='lm')

draw.rectangle([20, size-100, 45, size-80], fill='#0a2020', outline='#4ecdc4', width=2)
draw.text((55, size-90), "CYAN = Holes (cut out, REMOVED)", fill='#4ecdc4', font=small, anchor='lm')

draw.polygon([(20, size-70), (32, size-50), (45, size-70)], fill='#0a3a0a', outline='#00ff00', width=2)
draw.text((55, size-60), "GREEN = PROPOSED TEETH (review this!)", fill='#00ff00', font=small, anchor='lm')

draw.rectangle([20, size-40, 45, size-20], outline='#ffe66d', width=2)
draw.text((55, size-30), "YELLOW = Ring (CW cut)", fill='#ffe66d', font=small, anchor='lm')

# Status
draw.rectangle([size-250, 10, size-10, 80], fill='#111', outline='#00ff00')
draw.text((size-130, 30), "QC SAMPLE", fill='#00ff00', font=med, anchor='mm')
draw.text((size-130, 55), "Awaiting approval", fill='#ffff00', font=small, anchor='mm')

img.save('/home/kontomeo/Desktop/BROK_QC_SAMPLE.png')
print(f"\n[SAVED] BROK_QC_SAMPLE.png")
print("\n" + "="*60)
print("QC SAMPLE READY FOR REVIEW")
print("="*60)
print("GREEN triangles = proposed teeth locations")
print("If approved, BROK CNC will trace this design")
print("="*60)
