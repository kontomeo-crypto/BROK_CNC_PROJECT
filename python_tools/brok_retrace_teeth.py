#!/usr/bin/env python3
"""
BROK CNC - Re-trace with Teeth Preserved
========================================
- Trace original JP logo with HIGH detail
- Keep 7 teeth top, 4 teeth bottom
- Make 15% bigger
- Connected to jaw (no gaps)
"""
import cv2
import numpy as np
import math
from PIL import Image, ImageDraw, ImageFont
import shutil

# BACKUP
shutil.copy("/home/kontomeo/Desktop/JURASSIC_TREX.nc",
            "/home/kontomeo/Desktop/BROK_BACKUPS/v3_before_retrace.nc")
print("[BACKUP] v3_before_retrace.nc saved")

# Load original JP logo
img_path = "/home/kontomeo/Desktop/jp_logo__tyrannosaurus_rex_by_titanuspixel55_derr4aw-pre.png"
img = cv2.imread(img_path)
h, w = img.shape[:2]
print(f"[LOAD] Original image: {w}x{h}")

# Convert to grayscale and threshold for BLACK regions
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
_, black_mask = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY_INV)

# Find contours with HIGH detail (no approximation)
contours, hierarchy = cv2.findContours(black_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
print(f"[TRACE] Found {len(contours)} contours")

# Find T-Rex silhouette (large, non-circular)
best_contour = None
best_score = 0

for cnt in contours:
    area = cv2.contourArea(cnt)
    if area < 10000:
        continue
    perim = cv2.arcLength(cnt, True)
    circ = 4 * math.pi * area / (perim * perim) if perim > 0 else 0

    # T-Rex has low circularity (not a circle) and many points
    if circ < 0.5 and len(cnt) > 1000:
        score = len(cnt)  # Prefer most detailed contour
        if score > best_score:
            best_score = score
            best_contour = cnt

print(f"[TRACE] Selected contour: {len(best_contour)} points, detail preserved")

# Scale to workspace (10.5" fits in 12" ring)
scale = 10.5 / max(h, w)
offset_x = 6.75 - (w * scale / 2)
offset_y = 6.75 - (h * scale / 2)

# Convert to inches
skeleton_raw = []
for pt in best_contour:
    px, py = pt[0]
    x = px * scale + offset_x
    y = (h - py) * scale + offset_y  # Flip Y
    skeleton_raw.append((x, y))

print(f"[CONVERT] Raw skeleton: {len(skeleton_raw)} points")

# Find teeth regions by analyzing the contour
# Teeth are sharp inward points along the jaw edges
# Upper jaw: right side, Y > 7.5 (mouth area)
# Lower jaw: right side, Y around 6.5-7.5

def find_teeth_in_contour(pts):
    """Find teeth by detecting sharp angle changes (convex peaks into mouth)"""
    teeth = []
    n = len(pts)

    for i in range(n):
        p_prev = pts[(i - 3) % n]
        p_curr = pts[i]
        p_next = pts[(i + 3) % n]

        # Vector analysis
        v1 = (p_curr[0] - p_prev[0], p_curr[1] - p_prev[1])
        v2 = (p_next[0] - p_curr[0], p_next[1] - p_curr[1])

        # Cross product for turn direction
        cross = v1[0] * v2[1] - v1[1] * v2[0]

        # Magnitude
        mag1 = math.sqrt(v1[0]**2 + v1[1]**2)
        mag2 = math.sqrt(v2[0]**2 + v2[1]**2)

        if mag1 < 0.01 or mag2 < 0.01:
            continue

        # Dot product for angle
        dot = v1[0]*v2[0] + v1[1]*v2[1]
        cos_angle = dot / (mag1 * mag2)
        cos_angle = max(-1, min(1, cos_angle))
        angle = math.degrees(math.acos(cos_angle))

        x, y = p_curr

        # Upper jaw teeth: right side, upper mouth area, sharp angle, pointing down
        if x > 9.0 and 7.8 < y < 9.5 and angle < 100 and cross < 0:
            teeth.append({'idx': i, 'x': x, 'y': y, 'type': 'upper', 'angle': angle})

        # Lower jaw teeth: right side, lower mouth area, sharp angle, pointing up
        elif x > 9.0 and 6.5 < y < 7.8 and angle < 100 and cross > 0:
            teeth.append({'idx': i, 'x': x, 'y': y, 'type': 'lower', 'angle': angle})

    return teeth

all_teeth = find_teeth_in_contour(skeleton_raw)
upper_teeth = [t for t in all_teeth if t['type'] == 'upper']
lower_teeth = [t for t in all_teeth if t['type'] == 'lower']

print(f"[TEETH] Found {len(upper_teeth)} upper, {len(lower_teeth)} lower")

# Sort and select: 7 upper, 4 lower (evenly spaced)
def select_teeth(teeth_list, count):
    if len(teeth_list) <= count:
        return teeth_list

    # Sort by X position
    sorted_teeth = sorted(teeth_list, key=lambda t: t['x'])

    # Select evenly spaced
    step = len(sorted_teeth) / count
    selected = []
    for i in range(count):
        idx = int(i * step)
        if idx < len(sorted_teeth):
            selected.append(sorted_teeth[idx])

    return selected

selected_upper = select_teeth(upper_teeth, 7)
selected_lower = select_teeth(lower_teeth, 4)

print(f"[SELECT] Keeping {len(selected_upper)} upper, {len(selected_lower)} lower")

# Get indices of teeth to keep
keep_indices = set()
for t in selected_upper + selected_lower:
    # Keep a range around each tooth (tooth shape is ~5-10 points)
    for j in range(-8, 9):
        keep_indices.add((t['idx'] + j) % len(skeleton_raw))

# Build new skeleton: smooth jaw except at kept teeth
# Also scale kept teeth 15% bigger

def scale_tooth(pts, center_idx, scale_factor=1.15):
    """Scale a tooth by moving points away from center"""
    center = pts[center_idx]
    result = list(pts)

    # Scale points within range of center
    for j in range(-6, 7):
        idx = (center_idx + j) % len(pts)
        if idx == center_idx:
            continue
        px, py = pts[idx]
        cx, cy = center

        # Direction from center
        dx = px - cx
        dy = py - cy

        # Scale
        result[idx] = (cx + dx * scale_factor, cy + dy * scale_factor)

    return result

# Apply 15% scaling to selected teeth
skeleton_scaled = list(skeleton_raw)
for t in selected_upper + selected_lower:
    skeleton_scaled = scale_tooth(skeleton_scaled, t['idx'], 1.15)
    print(f"[SCALE] Tooth at ({t['x']:.2f}, {t['y']:.2f}) scaled 15%")

# Simplify non-teeth areas while preserving teeth
def simplify_preserving_teeth(pts, keep_set, target_points=400):
    """Simplify contour but preserve points near teeth"""
    n = len(pts)

    # Calculate how many points to skip
    non_teeth_count = n - len(keep_set)
    target_non_teeth = target_points - len(keep_set)

    if target_non_teeth <= 0 or non_teeth_count <= target_non_teeth:
        return pts

    skip_rate = non_teeth_count / target_non_teeth

    result = []
    skip_counter = 0

    for i in range(n):
        if i in keep_set:
            result.append(pts[i])
            skip_counter = 0
        else:
            skip_counter += 1
            if skip_counter >= skip_rate:
                result.append(pts[i])
                skip_counter = 0

    return result

skeleton_final = simplify_preserving_teeth(skeleton_scaled, keep_indices, 450)
print(f"[SIMPLIFY] Final skeleton: {len(skeleton_final)} points (teeth preserved)")

# Find holes (interior contours)
holes = []
if hierarchy is not None:
    for i, (cnt, hier) in enumerate(zip(contours, hierarchy[0])):
        parent = hier[3]
        if parent >= 0:  # Has parent = interior
            area = cv2.contourArea(cnt)
            if 500 < area < 50000:
                hole_pts = []
                for pt in cnt[::3]:  # Simplify holes
                    px, py = pt[0]
                    x = px * scale + offset_x
                    y = (h - py) * scale + offset_y
                    hole_pts.append((x, y))

                # Check if in workspace
                xs = [p[0] for p in hole_pts]
                ys = [p[1] for p in hole_pts]
                if 1 < min(xs) and max(xs) < 13 and 1 < min(ys) and max(ys) < 13:
                    # Skip small teeth-like holes in jaw area
                    cx = sum(xs) / len(xs)
                    cy = sum(ys) / len(ys)
                    hw = max(xs) - min(xs)
                    hh = max(ys) - min(ys)

                    is_tooth_hole = (cx > 8.5 and hw < 0.6 and hh < 0.8)
                    if not is_tooth_hole:
                        holes.append(hole_pts)

print(f"[HOLES] Kept {len(holes)} interior holes")

# Generate QC image
size = 1500
margin = 50
img_scale = (size - 2*margin) / 14.0

qc = Image.new('RGB', (size, size), '#0a0a0a')
draw = ImageDraw.Draw(qc)

def px(x, y):
    return (margin + int(x * img_scale), size - margin - int(y * img_scale))

# Grid
for i in range(29):
    p = margin + int(i * 0.5 * img_scale)
    draw.line([(p, margin), (p, size-margin)], fill='#1a1a1a')
    draw.line([(margin, p), (size-margin, p)], fill='#1a1a1a')

# T-Rex Skeleton in RED (workpiece - STAYS)
pts = [px(x,y) for x,y in skeleton_final]
if len(pts) > 2:
    draw.polygon(pts, outline='#ff6b6b', fill='#2a0a0a', width=2)

# Holes in CYAN (cut out - REMOVED)
for hole in holes:
    if len(hole) > 2:
        hpts = [px(x,y) for x,y in hole]
        draw.polygon(hpts, outline='#4ecdc4', fill='#0a2020', width=2)

# Ring
cx, cy = px(6.75, 6.75)
r = int(6.0 * img_scale)
draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline='#ffe66d', width=3)

# Mark teeth locations
for t in selected_upper:
    tp = px(t['x'], t['y'])
    draw.ellipse([tp[0]-5, tp[1]-5, tp[0]+5, tp[1]+5], fill='#00ff00')

for t in selected_lower:
    tp = px(t['x'], t['y'])
    draw.ellipse([tp[0]-5, tp[1]-5, tp[0]+5, tp[1]+5], fill='#00ffff')

# Title
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12)
except:
    font = small = ImageFont.load_default()

draw.text((size//2, 25), "BROK - RE-TRACED WITH TEETH", fill='#00ff00', font=font, anchor='mm')
draw.text((size//2, 50), f"Upper: 7 teeth (green) | Lower: 4 teeth (cyan) | 15% bigger | CONNECTED",
          fill='#888', font=small, anchor='mm')

# Legend
draw.rectangle([10, size-110, 380, size-10], fill='#111', outline='#333')
draw.rectangle([20, size-100, 40, size-85], fill='#2a0a0a', outline='#ff6b6b')
draw.text((50, size-92), "RED = T-Rex + Ring (workpiece STAYS)", fill='#ff6b6b', font=small, anchor='lm')
draw.rectangle([20, size-75, 40, size-60], fill='#0a2020', outline='#4ecdc4')
draw.text((50, size-67), "CYAN = Holes (cut out, REMOVED)", fill='#4ecdc4', font=small, anchor='lm')
draw.ellipse([20, size-50, 35, size-35], fill='#00ff00')
draw.text((50, size-42), "Green dots = Upper teeth locations", fill='#00ff00', font=small, anchor='lm')
draw.ellipse([20, size-25, 35, size-10], fill='#00ffff')
draw.text((50, size-17), "Cyan dots = Lower teeth locations", fill='#00ffff', font=small, anchor='lm')

qc.save('/home/kontomeo/Desktop/BROK_RETRACE_TEETH.png')
print(f"[SAVED] BROK_RETRACE_TEETH.png")

# Generate G-code
gcode = []
gcode.append("(BROK CNC - RE-TRACED WITH TEETH)")
gcode.append("(7 upper, 4 lower, 15% bigger, connected)")
gcode.append("(BEVEL LAW ENFORCED)")
gcode.append("(Feed:47 Pierce:0.148 Cut:0.059)")
gcode.append("(v1.6-af)")
gcode.append("G20G90")
gcode.append("G0X0.Y0.")
gcode.append("H0")
gcode.append("")

cut_num = 0

# Holes - CCW
for hole in holes:
    if len(hole) < 10:
        continue
    cut_num += 1
    gcode.append(f"(=== CUT {cut_num}: HOLE - CCW ===)")
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

# Skeleton - CCW
cut_num += 1
gcode.append(f"(=== CUT {cut_num}: SKELETON WITH TEETH - CCW ===)")
sx, sy = skeleton_final[0]
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
for x, y in skeleton_final:
    gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
gcode.append(f"G1X{skeleton_final[0][0]:.4f}Y{skeleton_final[0][1]:.4f}F47")
gcode.append("H0")
gcode.append("M5")
gcode.append("G0Z1")
gcode.append("")

# Ring - CW
cut_num += 1
gcode.append(f"(=== CUT {cut_num}: 12\" RING - CW ===)")
gcode.append(f"G0X{6.75+6.2:.4f}Y6.7500")
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
    x = 6.75 + 6.0 * math.cos(angle)
    y = 6.75 + 6.0 * math.sin(angle)
    gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
gcode.append("H0")
gcode.append("M5")
gcode.append("G0Z1")
gcode.append("")

gcode.append("G0X0Y0")
gcode.append("M30")

with open("/home/kontomeo/Desktop/JURASSIC_TREX.nc", 'w') as f:
    f.write("\n".join(gcode))

# Backup
shutil.copy("/home/kontomeo/Desktop/JURASSIC_TREX.nc",
            "/home/kontomeo/Desktop/BROK_BACKUPS/v4_retrace_teeth.nc")
shutil.copy("/home/kontomeo/Desktop/BROK_RETRACE_TEETH.png",
            "/home/kontomeo/Desktop/BROK_BACKUPS/v4_retrace_teeth.png")

print(f"[SAVED] G-code: {cut_num} cuts")
print(f"[BACKUP] v4_retrace_teeth saved")
print("\n" + "="*50)
print("RE-TRACED: 7 upper + 4 lower teeth")
print("15% bigger, CONNECTED to jaw")
print("="*50)
