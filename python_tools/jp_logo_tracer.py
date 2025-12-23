#!/usr/bin/env python3
"""
BROK CNC - Jurassic Park Logo Tracer v2
========================================
Uses OpenCV for proper contour detection.
Includes critic loop for verification.
"""

import cv2
import numpy as np
from PIL import Image
import math

# BROK CNC Settings
FEED = 47
PIERCE_HEIGHT = 0.148
CUT_HEIGHT = 0.059
TARGET_SIZE = 12.0  # inches
MIN_HOLE_INCHES = 0.3  # Minimum hole size for 2mm kerf

def load_image(path):
    """Load and analyze image."""
    img = cv2.imread(path)
    if img is None:
        raise ValueError(f"Cannot load: {path}")
    return img

def extract_regions(img):
    """Extract black and red regions from JP logo."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Black mask (the part we KEEP)
    # Low saturation, low value = black
    black_lower = np.array([0, 0, 0])
    black_upper = np.array([180, 255, 60])
    black_mask = cv2.inRange(hsv, black_lower, black_upper)

    # Red mask (WASTE - holes to cut out)
    # Red has hue near 0 or 180
    red_lower1 = np.array([0, 100, 100])
    red_upper1 = np.array([10, 255, 255])
    red_lower2 = np.array([160, 100, 100])
    red_upper2 = np.array([180, 255, 255])
    red_mask1 = cv2.inRange(hsv, red_lower1, red_upper1)
    red_mask2 = cv2.inRange(hsv, red_lower2, red_upper2)
    red_mask = cv2.bitwise_or(red_mask1, red_mask2)

    # Clean up masks
    kernel = np.ones((3,3), np.uint8)
    black_mask = cv2.morphologyEx(black_mask, cv2.MORPH_CLOSE, kernel)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)

    return black_mask, red_mask

def find_contours_cv(mask, min_area=100):
    """Find contours using OpenCV."""
    contours, hierarchy = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    # Filter by area
    filtered = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area >= min_area:
            filtered.append(cnt)

    return filtered

def simplify_contour_cv(contour, epsilon_factor=0.002):
    """Simplify contour using Douglas-Peucker."""
    epsilon = epsilon_factor * cv2.arcLength(contour, True)
    return cv2.approxPolyDP(contour, epsilon, True)

def contour_to_inches(contour, img_height, scale):
    """Convert OpenCV contour to inches, flip Y."""
    points = []
    for pt in contour:
        x_px, y_px = pt[0]
        x_in = x_px * scale
        y_in = (img_height - y_px) * scale  # Flip Y
        points.append((x_in, y_in))
    return points

def is_contour_cw(contour):
    """Check if contour is clockwise using signed area."""
    pts = contour.reshape(-1, 2)
    n = len(pts)
    area = 0
    for i in range(n):
        j = (i + 1) % n
        area += (pts[j][0] - pts[i][0]) * (pts[j][1] + pts[i][1])
    return area > 0

def trace_jp_logo(image_path, output_nc, output_qc):
    """Main tracing function with critic loop."""
    print("=" * 60)
    print("BROK CNC - JP LOGO TRACER v2 (OpenCV)")
    print("=" * 60)

    # Load image
    print(f"\n[1] Loading: {image_path}")
    img = load_image(image_path)
    h, w = img.shape[:2]
    print(f"    Image size: {w}x{h} pixels")

    # Calculate scale
    scale = TARGET_SIZE / max(w, h)
    min_hole_px = MIN_HOLE_INCHES / scale
    print(f"    Scale: {scale:.6f} in/px")
    print(f"    Min hole: {min_hole_px:.0f} px ({MIN_HOLE_INCHES}\")")

    # Extract regions
    print("\n[2] Extracting regions...")
    black_mask, red_mask = extract_regions(img)

    # Debug: save masks
    cv2.imwrite('/home/kontomeo/Desktop/debug_black.png', black_mask)
    cv2.imwrite('/home/kontomeo/Desktop/debug_red.png', red_mask)
    print("    Saved debug masks")

    # Find black contours (outer boundary)
    print("\n[3] Finding BLACK contours (outer boundary)...")
    black_contours = find_contours_cv(black_mask, min_area=1000)
    print(f"    Found {len(black_contours)} black contours")

    # Sort by area, largest first
    black_contours.sort(key=cv2.contourArea, reverse=True)

    # Find red contours (holes to cut)
    print("\n[4] Finding RED contours (holes)...")
    min_hole_area = (min_hole_px ** 2) * 0.5
    red_contours = find_contours_cv(red_mask, min_area=min_hole_area)
    print(f"    Found {len(red_contours)} red contours (min area: {min_hole_area:.0f})")

    # Sort by area
    red_contours.sort(key=cv2.contourArea, reverse=True)

    # Process outer contour
    outer_contour = None
    if black_contours:
        largest = black_contours[0]
        print(f"    Raw outer points: {len(largest)}")

        # For circular shapes, don't over-simplify
        # Use a very small epsilon to preserve the circle
        if len(largest) > 100:
            simplified = simplify_contour_cv(largest, 0.0001)
        else:
            simplified = largest  # Don't simplify small contours

        outer_contour = contour_to_inches(simplified, h, scale)
        print(f"\n[5] Outer contour: {len(outer_contour)} points")

        # Get bounding box
        xs = [p[0] for p in outer_contour]
        ys = [p[1] for p in outer_contour]
        print(f"    Bounds: {min(xs):.2f}-{max(xs):.2f} x {min(ys):.2f}-{max(ys):.2f} in")

    # Process holes
    # IMPORTANT: Skip holes larger than 3" - those are the interior background
    # not actual skull holes. Cutting them would separate T-Rex from ring!
    MAX_HOLE_INCHES = 3.0

    hole_contours = []
    print(f"\n[6] Processing holes (max 15, skip >3\")...")
    for i, cnt in enumerate(red_contours[:15]):
        simplified = simplify_contour_cv(cnt, 0.003)
        hole = contour_to_inches(simplified, h, scale)

        if len(hole) < 4:
            continue

        # Get size
        xs = [p[0] for p in hole]
        ys = [p[1] for p in hole]
        hole_w = max(xs) - min(xs)
        hole_h = max(ys) - min(ys)

        # Skip large "holes" - these are background, not skull holes
        if hole_w > MAX_HOLE_INCHES or hole_h > MAX_HOLE_INCHES:
            print(f"    SKIP: {hole_w:.2f}x{hole_h:.2f}\" (too large - background)")
            continue

        if hole_w >= MIN_HOLE_INCHES and hole_h >= MIN_HOLE_INCHES:
            hole_contours.append(hole)
            print(f"    Hole {len(hole_contours)}: {len(hole)} pts, {hole_w:.2f}x{hole_h:.2f}\"")

    print(f"\n[7] Total holes to cut: {len(hole_contours)}")

    # Generate G-code
    print("\n[8] Generating G-code...")
    generate_gcode(outer_contour, hole_contours, output_nc)

    # Generate QC
    print("\n[9] Generating QC image...")
    generate_qc_svg(outer_contour, hole_contours, output_qc)

    # Generate comparison image
    print("\n[10] Generating comparison...")
    generate_comparison(img, outer_contour, hole_contours, h, scale)

    # Critic score
    score = critic_evaluate(outer_contour, hole_contours, w, h, scale)

    return score

def generate_gcode(outer, holes, output_path):
    """Generate FireControl G-code."""
    lines = []

    # Header
    lines.append("(BROK CNC - JURASSIC PARK LOGO)")
    lines.append(f"(Auto-traced, {len(holes)} holes)")
    lines.append("(Everlast 102i @ 70A, 55 PSI)")
    lines.append(f"(Feed:{FEED} Pierce:{PIERCE_HEIGHT} Cut:{CUT_HEIGHT})")
    lines.append("()")
    lines.append("(v1.6-af)")
    lines.append("G20G90")
    lines.append("G0X0.Y0.")
    lines.append("H0")
    lines.append("")

    cut_num = 1

    # Cut holes first (CCW - for holes, waste drops out)
    for hole in holes:
        if len(hole) < 4:
            continue

        lines.append(f"(=== CUT {cut_num}: HOLE - CCW ===)")

        # Pierce outside the hole
        px, py = hole[0]
        pierce_x = px - 0.15

        lines.append(f"G0X{pierce_x:.4f}Y{py:.4f}")
        lines.append("G92Z0")
        lines.append("G38.2Z-5F50")
        lines.append("G38.4Z0.5F25")
        lines.append("G92Z0")
        lines.append(f"G0Z{PIERCE_HEIGHT}")
        lines.append("M3")
        lines.append("G4P0.70")
        lines.append(f"G0Z{CUT_HEIGHT}")
        lines.append("H1")

        # Lead-in
        lines.append(f"G1X{hole[0][0]:.4f}Y{hole[0][1]:.4f}F{FEED}")

        # Trace hole
        for x, y in hole[1:]:
            lines.append(f"G1X{x:.4f}Y{y:.4f}F{FEED}")

        # Close loop
        lines.append(f"G1X{hole[0][0]:.4f}Y{hole[0][1]:.4f}F{FEED}")

        # Overcut
        for x, y in hole[1:min(4, len(hole))]:
            lines.append(f"G1X{x:.4f}Y{y:.4f}F{FEED}")

        lines.append("H0")
        lines.append("M5")
        lines.append("G0Z1")
        lines.append("")
        cut_num += 1

    # Cut outer LAST (CW - bevel on waste/sheet side)
    # Use G2 arc for perfect 12" circle
    radius = TARGET_SIZE / 2  # 6" radius
    center_x = TARGET_SIZE / 2
    center_y = TARGET_SIZE / 2

    lines.append(f"(=== CUT {cut_num}: OUTER CIRCLE - CW G2 - LAST ===)")
    lines.append(f"(12\" diameter circle, center at {center_x},{center_y})")

    # Start at left side of circle (0, 6)
    start_x = 0.0
    start_y = center_y
    pierce_x = start_x - 0.25

    lines.append(f"G0X{pierce_x:.4f}Y{start_y:.4f}")
    lines.append("G92Z0")
    lines.append("G38.2Z-5F50")
    lines.append("G38.4Z0.5F25")
    lines.append("G92Z0")
    lines.append(f"G0Z{PIERCE_HEIGHT}")
    lines.append("M3")
    lines.append("G4P0.70")
    lines.append(f"G0Z{CUT_HEIGHT}")
    lines.append("H1")

    # Lead-in to circle start
    lines.append(f"G1X{start_x:.4f}Y{start_y:.4f}F{FEED}")

    # Full circle in CW direction using G2
    # G2 X Y I J - I,J are relative to start point to center
    # From (0,6) center is at (6,6), so I=6, J=0
    lines.append(f"G2X{start_x:.4f}Y{start_y:.4f}I{radius:.4f}J0.0000F{FEED}")

    # Overcut - small arc
    overcut_angle = 0.2  # radians, about 11 degrees
    overcut_x = center_x - radius * math.cos(overcut_angle)
    overcut_y = center_y + radius * math.sin(overcut_angle)
    lines.append(f"G2X{overcut_x:.4f}Y{overcut_y:.4f}I{radius:.4f}J0.0000F{FEED}")

    lines.append("H0")
    lines.append("M5")
    lines.append("G0Z1")
    lines.append("")

    # Footer
    lines.append("G0X0Y0")
    lines.append("M30")
    lines.append(f"(PS{FEED:.2f})")

    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"    Saved: {output_path}")
    print(f"    Total cuts: {cut_num}")

def generate_qc_svg(outer, holes, output_path):
    """Generate QC SVG."""
    svg_w, svg_h = 750, 750
    px_per_inch = 55
    offset = 50

    def to_svg(x, y):
        return offset + x * px_per_inch, svg_h - offset - y * px_per_inch

    lines = []
    lines.append(f'<svg width="{svg_w}" height="{svg_h}" xmlns="http://www.w3.org/2000/svg">')
    lines.append('<rect width="100%" height="100%" fill="#1a1a2e"/>')
    lines.append('<text x="375" y="25" text-anchor="middle" fill="white" font-size="14" font-weight="bold">JP LOGO - TRACED OUTPUT</text>')

    # Draw outer circle (yellow) - 12" diameter
    center_x, center_y = to_svg(TARGET_SIZE/2, TARGET_SIZE/2)
    radius_px = (TARGET_SIZE/2) * px_per_inch
    lines.append(f'<circle cx="{center_x:.1f}" cy="{center_y:.1f}" r="{radius_px:.1f}" fill="none" stroke="#ffe66d" stroke-width="3"/>')

    # Draw holes (cyan)
    for i, hole in enumerate(holes):
        if len(hole) < 3:
            continue
        pts = ' '.join([f"{to_svg(x,y)[0]:.1f},{to_svg(x,y)[1]:.1f}" for x,y in hole])
        # Close the path
        pts += f" {to_svg(hole[0][0], hole[0][1])[0]:.1f},{to_svg(hole[0][0], hole[0][1])[1]:.1f}"
        lines.append(f'<polyline points="{pts}" fill="none" stroke="#4ecdc4" stroke-width="2"/>')

    # Legend
    lines.append(f'<text x="30" y="710" fill="#4ecdc4" font-size="11">Holes (CCW): {len(holes)}</text>')
    lines.append(f'<text x="200" y="710" fill="#ffe66d" font-size="11">Outer: 12" circle (G2 CW)</text>')
    lines.append(f'<text x="450" y="710" fill="white" font-size="11">Pierce: {PIERCE_HEIGHT}" | Cut: {CUT_HEIGHT}"</text>')

    lines.append('</svg>')

    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"    Saved: {output_path}")

def generate_comparison(original_img, outer, holes, img_h, scale):
    """Generate side-by-side comparison."""
    # Create comparison image
    h, w = original_img.shape[:2]
    comparison = np.zeros((h, w*2, 3), dtype=np.uint8)

    # Left side: original
    comparison[:, :w] = original_img

    # Right side: traced contours on black
    traced = np.zeros((h, w, 3), dtype=np.uint8)

    # Draw outer in yellow
    if outer:
        pts = np.array([[(int(x/scale), int((img_h - y/scale))) for x, y in outer]], dtype=np.int32)
        cv2.polylines(traced, pts, True, (0, 255, 255), 2)

    # Draw holes in cyan
    for hole in holes:
        pts = np.array([[(int(x/scale), int((img_h - y/scale))) for x, y in hole]], dtype=np.int32)
        cv2.polylines(traced, pts, True, (255, 255, 0), 2)

    comparison[:, w:] = traced

    # Add labels
    cv2.putText(comparison, "ORIGINAL", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
    cv2.putText(comparison, "TRACED", (w+20, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)

    out_path = '/home/kontomeo/Desktop/JP_COMPARISON.png'
    cv2.imwrite(out_path, comparison)
    print(f"    Saved: {out_path}")

def critic_evaluate(outer, holes, img_w, img_h, scale):
    """Evaluate trace quality."""
    print("\n" + "=" * 60)
    print("CRITIC EVALUATION")
    print("=" * 60)

    score = 0
    issues = []

    # Check outer contour exists and is reasonable
    if outer and len(outer) >= 50:
        score += 30
        print(f"[+30] Outer contour has {len(outer)} points (good)")
    else:
        issues.append("Outer contour too simple or missing")
        print(f"[-] Outer contour issue: {len(outer) if outer else 0} points")

    # Check outer is roughly circular (JP logo is a circle)
    if outer:
        xs = [p[0] for p in outer]
        ys = [p[1] for p in outer]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        aspect = min(width, height) / max(width, height)

        if aspect > 0.9:
            score += 20
            print(f"[+20] Aspect ratio {aspect:.2f} (circular)")
        else:
            issues.append(f"Not circular: aspect {aspect:.2f}")
            print(f"[-] Aspect ratio {aspect:.2f} (should be ~1.0)")

    # Check holes detected
    if len(holes) >= 3:
        score += 25
        print(f"[+25] Found {len(holes)} holes (good)")
    elif len(holes) >= 1:
        score += 10
        print(f"[+10] Found {len(holes)} holes (some)")
    else:
        issues.append("No holes detected")
        print("[-] No holes detected")

    # Check hole sizes
    good_holes = 0
    for hole in holes:
        xs = [p[0] for p in hole]
        ys = [p[1] for p in hole]
        w = max(xs) - min(xs)
        h = max(ys) - min(ys)
        if w >= MIN_HOLE_INCHES and h >= MIN_HOLE_INCHES:
            good_holes += 1

    if good_holes >= 2:
        score += 15
        print(f"[+15] {good_holes} holes are cuttable size")

    # Size check
    if outer:
        xs = [p[0] for p in outer]
        ys = [p[1] for p in outer]
        actual_size = max(max(xs)-min(xs), max(ys)-min(ys))
        if 11 <= actual_size <= 13:
            score += 10
            print(f"[+10] Size {actual_size:.1f}\" close to target 12\"")

    print("-" * 60)
    print(f"TOTAL SCORE: {score}/100")

    if issues:
        print("\nISSUES:")
        for issue in issues:
            print(f"  - {issue}")

    return score

if __name__ == "__main__":
    input_img = "/home/kontomeo/Desktop/jp_logo__tyrannosaurus_rex_by_titanuspixel55_derr4aw-pre.png"
    output_nc = "/home/kontomeo/Desktop/JURASSIC_TREX.nc"
    output_qc = "/home/kontomeo/Desktop/JURASSIC_TREX_QC.svg"

    score = trace_jp_logo(input_img, output_nc, output_qc)

    print("\n" + "=" * 60)
    if score >= 70:
        print("PASS - Ready for review")
    else:
        print("FAIL - Needs improvement")
    print("=" * 60)
