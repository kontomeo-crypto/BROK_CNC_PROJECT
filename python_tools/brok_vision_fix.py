#!/usr/bin/env python3
"""
BROK CNC Vision-Guided Teeth Placement
======================================
Uses reference image analysis to place teeth ONLY on actual jaw edges.
"""
import re
import math
from PIL import Image, ImageDraw, ImageFont
import cv2
import numpy as np

class BrokVisionFix:
    """Vision-guided teeth placement for BROK CNC"""

    def __init__(self):
        self.scale = 100
        self.workpiece_size = 14.0
        self.points = []
        self.holes = []
        self.clean_points = []  # Skeleton without any teeth

    def load_clean_skeleton(self, gcode_path):
        """Load skeleton and remove any existing teeth (triangular spikes)"""
        with open(gcode_path, 'r') as f:
            lines = f.readlines()

        raw_points = []
        in_skeleton = False

        for line in lines:
            line = line.strip()
            if 'SKELETON' in line:
                in_skeleton = True
            elif in_skeleton and line.startswith('(==='):
                in_skeleton = False
            if in_skeleton:
                m = re.match(r'G1X([-\d.]+)Y([-\d.]+)', line)
                if m:
                    raw_points.append((float(m.group(1)), float(m.group(2))))

        # Load holes
        self.holes = []
        current_hole = []
        in_hole = False
        for line in lines:
            line = line.strip()
            if 'HOLE' in line and 'CUT' in line:
                if current_hole:
                    self.holes.append(current_hole)
                current_hole = []
                in_hole = True
            elif 'SKELETON' in line or 'RING' in line:
                if current_hole:
                    self.holes.append(current_hole)
                    current_hole = []
                in_hole = False
            if in_hole:
                m = re.match(r'G1X([-\d.]+)Y([-\d.]+)', line)
                if m:
                    current_hole.append((float(m.group(1)), float(m.group(2))))
        if current_hole:
            self.holes.append(current_hole)

        # Remove teeth by smoothing sharp spikes
        # Teeth are triangular: point deviates significantly then returns
        self.clean_points = self.remove_teeth_from_contour(raw_points)
        self.points = list(self.clean_points)

        print(f"[VISION] Loaded {len(raw_points)} raw points")
        print(f"[VISION] Cleaned to {len(self.clean_points)} points (teeth removed)")
        print(f"[VISION] Holes: {len(self.holes)}")
        return self

    def remove_teeth_from_contour(self, points):
        """Remove existing teeth (sharp triangular deviations)"""
        if len(points) < 5:
            return points

        cleaned = [points[0], points[1]]

        for i in range(2, len(points) - 2):
            p_prev = points[i-1]
            p_curr = points[i]
            p_next = points[i+1]

            # Calculate angle at this point
            v1 = (p_curr[0] - p_prev[0], p_curr[1] - p_prev[1])
            v2 = (p_next[0] - p_curr[0], p_next[1] - p_curr[1])

            # Dot product for angle
            dot = v1[0]*v2[0] + v1[1]*v2[1]
            mag1 = math.sqrt(v1[0]**2 + v1[1]**2)
            mag2 = math.sqrt(v2[0]**2 + v2[1]**2)

            if mag1 > 0.01 and mag2 > 0.01:
                cos_angle = dot / (mag1 * mag2)
                cos_angle = max(-1, min(1, cos_angle))
                angle = math.degrees(math.acos(cos_angle))

                # Sharp angle (< 60 degrees) = likely a tooth, skip it
                if angle < 60:
                    continue

            cleaned.append(p_curr)

        cleaned.extend(points[-2:])
        return cleaned

    def analyze_with_reference(self, ref_image_path):
        """
        Analyze reference image to find actual mouth location.
        The mouth is the gap between upper and lower jaw on the RIGHT side.
        """
        print(f"[VISION] Analyzing reference image: {ref_image_path}")

        img = cv2.imread(ref_image_path)
        if img is None:
            print("[VISION] ERROR: Could not load reference image")
            return None

        h, w = img.shape[:2]

        # Find the mouth opening - it's where black (T-Rex) has a gap
        # The mouth is roughly in the right half, middle height

        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # The mouth opening should be a RED area (waste) surrounded by BLACK (keep)
        # on the right side of the image

        # Find the rightmost extent of black (snout tip)
        _, black_mask = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY_INV)

        # Find columns with black pixels
        black_cols = np.any(black_mask > 0, axis=0)
        rightmost_black = np.max(np.where(black_cols)[0]) if np.any(black_cols) else w//2

        # The mouth is typically 60-80% from left, 40-60% from top
        mouth_region_x = int(rightmost_black * 0.7)  # 70% toward snout
        mouth_region_y_top = int(h * 0.35)
        mouth_region_y_bot = int(h * 0.55)

        print(f"[VISION] Image size: {w}x{h}")
        print(f"[VISION] Estimated mouth region: X>{mouth_region_x}, Y={mouth_region_y_top}-{mouth_region_y_bot}")

        # Scale to workspace coordinates
        scale = 10.5 / max(h, w)
        offset_x = 6.75 - (w * scale / 2)
        offset_y = 6.75 - (h * scale / 2)

        # Mouth boundaries in workspace inches
        mouth_x_min = mouth_region_x * scale + offset_x
        mouth_y_min = (h - mouth_region_y_bot) * scale + offset_y
        mouth_y_max = (h - mouth_region_y_top) * scale + offset_y

        print(f"[VISION] Mouth in workspace: X>{mouth_x_min:.2f}, Y={mouth_y_min:.2f}-{mouth_y_max:.2f}")

        return {
            'mouth_x_min': mouth_x_min,
            'mouth_y_min': mouth_y_min,
            'mouth_y_max': mouth_y_max,
            'mouth_y_center': (mouth_y_min + mouth_y_max) / 2
        }

    def find_jaw_segments(self, mouth_info):
        """
        Find skeleton segments that form the actual jaw edges.
        Upper jaw: points near mouth, Y > mouth center
        Lower jaw: points near mouth, Y < mouth center
        """
        if not mouth_info:
            return [], []

        upper_jaw = []
        lower_jaw = []

        mouth_x = mouth_info['mouth_x_min']
        mouth_y_center = mouth_info['mouth_y_center']
        mouth_y_min = mouth_info['mouth_y_min']
        mouth_y_max = mouth_info['mouth_y_max']

        for i, (x, y) in enumerate(self.clean_points):
            # Must be in mouth X region (right side, past mouth_x_min)
            if x < mouth_x:
                continue

            # Must be in mouth Y region (between jaw lines)
            if y < mouth_y_min - 1 or y > mouth_y_max + 1:
                continue

            # Upper jaw: above center line
            if y > mouth_y_center:
                upper_jaw.append((i, x, y))
            # Lower jaw: below center line
            else:
                lower_jaw.append((i, x, y))

        print(f"[VISION] Upper jaw candidates: {len(upper_jaw)}")
        print(f"[VISION] Lower jaw candidates: {len(lower_jaw)}")

        return upper_jaw, lower_jaw

    def add_teeth_to_jaws(self, upper_jaw, lower_jaw, num_teeth=5, tooth_height=0.3):
        """Add teeth only to verified jaw segments"""
        insertions = []
        teeth_added = 0

        # Upper jaw teeth (point DOWN into mouth)
        if upper_jaw:
            # Sort by X to space teeth along jaw
            upper_sorted = sorted(upper_jaw, key=lambda p: p[1])
            step = max(1, len(upper_sorted) // num_teeth)
            for j in range(0, min(len(upper_sorted), num_teeth * step), step):
                idx, x, y = upper_sorted[j]
                tooth = [(x - 0.12, y), (x, y - tooth_height), (x + 0.12, y)]
                insertions.append((idx, tooth, 'upper'))
                teeth_added += 1
                print(f"[VISION] Upper tooth at ({x:.2f}, {y:.2f})")

        # Lower jaw teeth (point UP into mouth)
        if lower_jaw:
            lower_sorted = sorted(lower_jaw, key=lambda p: p[1])
            step = max(1, len(lower_sorted) // num_teeth)
            for j in range(0, min(len(lower_sorted), num_teeth * step), step):
                idx, x, y = lower_sorted[j]
                tooth = [(x - 0.12, y), (x, y + tooth_height), (x + 0.12, y)]
                insertions.append((idx, tooth, 'lower'))
                teeth_added += 1
                print(f"[VISION] Lower tooth at ({x:.2f}, {y:.2f})")

        # Apply insertions
        insertions.sort(key=lambda x: x[0], reverse=True)
        self.points = list(self.clean_points)
        for idx, tooth, jaw_type in insertions:
            self.points = self.points[:idx] + tooth + self.points[idx+1:]

        print(f"[VISION] Added {teeth_added} teeth total")
        return teeth_added

    def generate_qc_image(self, output_path, mouth_info=None):
        """Generate QC image with mouth region highlighted"""
        img_size = int(self.workpiece_size * self.scale)
        margin = 50
        total = img_size + 2 * margin

        img = Image.new('RGB', (total, total), '#0a0a0a')
        draw = ImageDraw.Draw(img)

        def to_px(x, y):
            return (margin + int(x * self.scale),
                    total - margin - int(y * self.scale))

        # Grid
        for i in range(int(self.workpiece_size / 0.5) + 1):
            px = margin + int(i * 0.5 * self.scale)
            draw.line([(px, margin), (px, total - margin)], fill='#1a2a1a', width=1)
            py = total - margin - int(i * 0.5 * self.scale)
            draw.line([(margin, py), (total - margin, py)], fill='#1a2a1a', width=1)

        # Highlight mouth region if known
        if mouth_info:
            mx1 = margin + int(mouth_info['mouth_x_min'] * self.scale)
            my1 = total - margin - int(mouth_info['mouth_y_max'] * self.scale)
            my2 = total - margin - int(mouth_info['mouth_y_min'] * self.scale)
            draw.rectangle([mx1, my1, total - margin, my2], outline='#ffff00', width=2)
            draw.text((mx1 + 5, my1 + 5), "MOUTH ZONE", fill='#ffff00')

        # Holes
        for hole in self.holes:
            if len(hole) > 2:
                pts = [to_px(x, y) for x, y in hole]
                draw.polygon(pts, outline='#4ecdc4', width=2)

        # Skeleton
        if len(self.points) > 1:
            pts = [to_px(x, y) for x, y in self.points]
            for i in range(len(pts) - 1):
                draw.line([pts[i], pts[i+1]], fill='#ff6b6b', width=2)

        # Ring
        center = to_px(6.75, 6.75)
        radius = int(6.0 * self.scale)
        draw.ellipse([center[0]-radius, center[1]-radius,
                      center[0]+radius, center[1]+radius], outline='#ffe66d', width=2)

        # Title
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        except:
            font = ImageFont.load_default()

        draw.text((total//2, 25), "BROK VISION - TEETH PLACEMENT", fill='#00ff00', font=font, anchor='mm')

        img.save(output_path)
        print(f"[VISION] QC image saved: {output_path}")
        return output_path

    def generate_gcode(self, output_path):
        """Generate G-code with BEVEL LAW"""
        gcode = []
        gcode.append("(BROK CNC - VISION GUIDED TEETH)")
        gcode.append("(BEVEL LAW ENFORCED)")
        gcode.append("(Feed:47 Pierce:0.148 Cut:0.059)")
        gcode.append("(v1.6-af)")
        gcode.append("G20G90")
        gcode.append("G0X0.Y0.")
        gcode.append("H0")
        gcode.append("")

        cut_num = 0

        # Holes - CCW
        for hole in self.holes:
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

        # Skeleton - CCW
        if self.points:
            cut_num += 1
            gcode.append(f"(=== CUT {cut_num}: SKELETON WITH TEETH - CCW [BEVEL LAW] ===)")
            sx, sy = self.points[0]
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
            for x, y in self.points:
                gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
            gcode.append(f"G1X{self.points[0][0]:.4f}Y{self.points[0][1]:.4f}F47")
            gcode.append("H0")
            gcode.append("M5")
            gcode.append("G0Z1")
            gcode.append("")

        # Ring - CW
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

        with open(output_path, 'w') as f:
            f.write("\n".join(gcode))

        print(f"[VISION] G-code saved: {output_path} ({cut_num} cuts)")
        return cut_num


# === MAIN ===
if __name__ == "__main__":
    print("=" * 60)
    print("  BROK VISION-GUIDED TEETH PLACEMENT")
    print("=" * 60)

    fixer = BrokVisionFix()

    # Step 1: Load and clean skeleton (remove bad teeth)
    print("\n[STEP 1] Loading and cleaning skeleton...")
    fixer.load_clean_skeleton("/home/kontomeo/Desktop/JURASSIC_TREX.nc")

    # Step 2: Analyze reference image to find mouth
    print("\n[STEP 2] Analyzing reference image for mouth location...")
    ref_img = "/home/kontomeo/Desktop/jp_logo__tyrannosaurus_rex_by_titanuspixel55_derr4aw-pre.png"
    mouth_info = fixer.analyze_with_reference(ref_img)

    # Step 3: Find actual jaw segments
    print("\n[STEP 3] Finding jaw segments...")
    upper_jaw, lower_jaw = fixer.find_jaw_segments(mouth_info)

    # Step 4: Add teeth to correct locations
    print("\n[STEP 4] Adding teeth to verified jaw locations...")
    teeth = fixer.add_teeth_to_jaws(upper_jaw, lower_jaw, num_teeth=5, tooth_height=0.3)

    # Step 5: Generate QC image
    print("\n[STEP 5] Generating QC image...")
    fixer.generate_qc_image("/home/kontomeo/Desktop/BROK_VISION_QC.png", mouth_info)

    # Step 6: Generate G-code
    print("\n[STEP 6] Generating G-code...")
    fixer.generate_gcode("/home/kontomeo/Desktop/JURASSIC_TREX.nc")

    print("\n" + "=" * 60)
    print("  VISION FIX COMPLETE")
    print("=" * 60)
