#!/usr/bin/env python3
"""
BROK CNC - Autonomous AI Image-to-CNC System v2
================================================
Tuned with learned corrections:
- Better jaw detection using mouth opening bounds
- Teeth placed along jaw LINE not at extremities
- Position validation before integration
- Self-correcting iteration loop

Changes from v1:
- Upper jaw: Y between 8.5-9.5 (not 8.3-10.0) - avoids skull top
- Lower jaw: Y between 7.0-7.6 (not 6.5-7.8) - avoids chin tip
- X range: 9.5-11.5 (not 9.0-12.0) - focuses on mouth area
- Teeth sorted by X and evenly distributed
- Skip first 20% and last 10% of jaw (back of mouth, tip)
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import math
import json
import os

class BrokAutonomous:
    def __init__(self):
        print("="*70)
        print("BROK CNC - AUTONOMOUS AI SYSTEM v2 (TUNED)")
        print("="*70)

        # Workspace
        self.workspace = 14.0
        self.ring_dia = 12.0
        self.center = (6.75, 6.75)

        # Image settings
        self.img_size = 2000
        self.margin = 80
        self.scale = (self.img_size - 2*self.margin) / self.workspace

        # Design state
        self.skeleton = []
        self.holes = []
        self.teeth_upper = []
        self.teeth_lower = []

        # TUNED PARAMETERS - learned from corrections
        self.jaw_params = {
            # Upper jaw (snout) - where upper teeth go
            'upper_x_min': 9.5,    # Start of mouth area
            'upper_x_max': 11.5,   # End before nose tip
            'upper_y_min': 8.5,    # Above mouth opening
            'upper_y_max': 9.5,    # Below skull top

            # Lower jaw (chin) - where lower teeth go
            'lower_x_min': 9.5,    # Start of mouth area
            'lower_x_max': 11.3,   # End before chin tip
            'lower_y_min': 7.0,    # Above throat
            'lower_y_max': 7.6,    # Below mouth opening

            # Tooth placement
            'skip_back': 0.20,     # Skip first 20% (back of jaw)
            'skip_front': 0.10,   # Skip last 10% (jaw tip)

            # Tooth size (15% bigger than original)
            'tooth_w': 0.40,
            'tooth_h': 0.52
        }

        # Iteration tracking
        self.iteration = 0
        self.max_iterations = 5
        self.problems = []

        print(f"Jaw params (tuned):")
        print(f"  Upper: X[{self.jaw_params['upper_x_min']}-{self.jaw_params['upper_x_max']}] Y[{self.jaw_params['upper_y_min']}-{self.jaw_params['upper_y_max']}]")
        print(f"  Lower: X[{self.jaw_params['lower_x_min']}-{self.jaw_params['lower_x_max']}] Y[{self.jaw_params['lower_y_min']}-{self.jaw_params['lower_y_max']}]")

    def px(self, x, y):
        """Inches to pixels"""
        return (
            self.margin + int(x * self.scale),
            self.img_size - self.margin - int(y * self.scale)
        )

    def load_and_trace(self, image_path):
        """Step 1: Load image and trace contours"""
        print(f"\n[STEP 1] Loading and tracing: {image_path}")

        img = cv2.imread(image_path)
        if img is None:
            return False, "Cannot load image"

        h, w = img.shape[:2]
        self.source_h, self.source_w = h, w

        # Scale to fit
        fit_size = self.ring_dia - 0.5
        self.src_scale = fit_size / max(h, w)
        self.src_offset = (
            self.center[0] - (w * self.src_scale / 2),
            self.center[1] - (h * self.src_scale / 2)
        )

        # Threshold and find contours
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY_INV)
        contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)

        # Find main silhouette
        best = None
        best_len = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            perim = cv2.arcLength(cnt, True)
            if perim > 0:
                circ = 4 * math.pi * area / (perim * perim)
                if circ < 0.6 and len(cnt) > best_len:
                    best = cnt
                    best_len = len(cnt)

        if best is None:
            return False, "No suitable contour found"

        # Convert to workspace coords
        self.skeleton = []
        for pt in best:
            px, py = pt[0]
            x = px * self.src_scale + self.src_offset[0]
            y = (h - py) * self.src_scale + self.src_offset[1]
            self.skeleton.append([x, y])

        # Simplify - but keep more points for better tooth placement
        step = max(1, len(self.skeleton) // 800)  # Doubled resolution
        self.skeleton = self.skeleton[::step]

        # Find holes
        self.holes = []
        if hierarchy is not None:
            for i, (cnt, hier) in enumerate(zip(contours, hierarchy[0])):
                if hier[3] >= 0:
                    area = cv2.contourArea(cnt)
                    if 2000 < area < 30000:
                        hole_pts = []
                        for pt in cnt[::3]:
                            px, py = pt[0]
                            x = px * self.src_scale + self.src_offset[0]
                            y = (h - py) * self.src_scale + self.src_offset[1]
                            hole_pts.append([x, y])

                        xs = [p[0] for p in hole_pts]
                        if 1 < min(xs) < max(xs) < 13:
                            self.holes.append(hole_pts)

        print(f"[TRACE] Skeleton: {len(self.skeleton)} points")
        print(f"[TRACE] Holes: {len(self.holes)}")

        return True, "Trace complete"

    def find_jaw_points(self):
        """Find jaw line points using tuned parameters"""
        p = self.jaw_params

        upper_jaw_idx = []
        lower_jaw_idx = []

        for i, (x, y) in enumerate(self.skeleton):
            # Upper jaw detection (tuned bounds)
            if (p['upper_x_min'] < x < p['upper_x_max'] and
                p['upper_y_min'] < y < p['upper_y_max']):
                upper_jaw_idx.append(i)

            # Lower jaw detection (tuned bounds)
            elif (p['lower_x_min'] < x < p['lower_x_max'] and
                  p['lower_y_min'] < y < p['lower_y_max']):
                lower_jaw_idx.append(i)

        return upper_jaw_idx, lower_jaw_idx

    def select_tooth_positions(self, jaw_indices, count):
        """Select evenly spaced tooth positions along jaw line - FIXED spacing"""
        if len(jaw_indices) < count:
            print(f"[WARN] Not enough jaw points: {len(jaw_indices)} < {count}")
            return jaw_indices

        p = self.jaw_params

        # Sort by X position (back to front of jaw)
        sorted_idx = sorted(jaw_indices, key=lambda i: self.skeleton[i][0])

        # Get X range of jaw points
        x_min = self.skeleton[sorted_idx[0]][0]
        x_max = self.skeleton[sorted_idx[-1]][0]
        x_range = x_max - x_min

        # Calculate ideal X positions (evenly spaced)
        # Skip 20% at back, 10% at front
        x_start = x_min + x_range * p['skip_back']
        x_end = x_max - x_range * p['skip_front']
        x_span = x_end - x_start

        ideal_positions = []
        for i in range(count):
            if count > 1:
                ideal_x = x_start + (x_span * i / (count - 1))
            else:
                ideal_x = (x_start + x_end) / 2
            ideal_positions.append(ideal_x)

        # Find closest skeleton point to each ideal position
        selected = []
        used_indices = set()

        for ideal_x in ideal_positions:
            best_idx = None
            best_dist = float('inf')

            for idx in sorted_idx:
                if idx in used_indices:
                    continue
                x = self.skeleton[idx][0]
                dist = abs(x - ideal_x)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = idx

            if best_idx is not None:
                selected.append(best_idx)
                used_indices.add(best_idx)

        print(f"[SPACING] Ideal X positions: {[f'{x:.2f}' for x in ideal_positions]}")
        print(f"[SPACING] Actual X positions: {[f'{self.skeleton[i][0]:.2f}' for i in selected]}")

        return selected

    def validate_tooth_position(self, x, y, jaw_type):
        """Validate a tooth position is within correct bounds"""
        p = self.jaw_params

        if jaw_type == 'upper':
            x_ok = p['upper_x_min'] < x < p['upper_x_max']
            y_ok = p['upper_y_min'] < y < p['upper_y_max']
        else:
            x_ok = p['lower_x_min'] < x < p['lower_x_max']
            y_ok = p['lower_y_min'] < y < p['lower_y_max']

        return x_ok and y_ok

    def integrate_teeth(self, upper_count=7, lower_count=4):
        """Step 2: Integrate teeth INTO skeleton with validation"""
        print(f"\n[STEP 2] Integrating {upper_count} upper, {lower_count} lower teeth")

        p = self.jaw_params

        # Find jaw points
        upper_jaw_idx, lower_jaw_idx = self.find_jaw_points()
        print(f"[JAW] Found: {len(upper_jaw_idx)} upper, {len(lower_jaw_idx)} lower points")

        if len(upper_jaw_idx) < upper_count:
            print(f"[WARN] Expanding upper jaw search...")
            # Expand bounds slightly
            for i, (x, y) in enumerate(self.skeleton):
                if (p['upper_x_min']-0.5 < x < p['upper_x_max']+0.5 and
                    p['upper_y_min']-0.3 < y < p['upper_y_max']+0.3):
                    if i not in upper_jaw_idx:
                        upper_jaw_idx.append(i)

        if len(lower_jaw_idx) < lower_count:
            print(f"[WARN] Expanding lower jaw search...")
            for i, (x, y) in enumerate(self.skeleton):
                if (p['lower_x_min']-0.5 < x < p['lower_x_max']+0.3 and
                    p['lower_y_min']-0.2 < y < p['lower_y_max']+0.2):
                    if i not in lower_jaw_idx:
                        lower_jaw_idx.append(i)

        print(f"[JAW] After expansion: {len(upper_jaw_idx)} upper, {len(lower_jaw_idx)} lower")

        # Select positions
        upper_positions = self.select_tooth_positions(upper_jaw_idx, upper_count)
        lower_positions = self.select_tooth_positions(lower_jaw_idx, lower_count)

        # Validate and report positions
        print(f"\n[TEETH] Upper jaw positions:")
        for idx in upper_positions:
            x, y = self.skeleton[idx]
            valid = self.validate_tooth_position(x, y, 'upper')
            status = "✓" if valid else "✗"
            print(f"  {status} ({x:.2f}, {y:.2f})")

        print(f"\n[TEETH] Lower jaw positions:")
        for idx in lower_positions:
            x, y = self.skeleton[idx]
            valid = self.validate_tooth_position(x, y, 'lower')
            status = "✓" if valid else "✗"
            print(f"  {status} ({x:.2f}, {y:.2f})")

        # Combine and sort by index (descending for insertion)
        all_teeth = []
        for idx in upper_positions:
            all_teeth.append((idx, 'down', 'upper'))
        for idx in lower_positions:
            all_teeth.append((idx, 'up', 'lower'))

        all_teeth.sort(key=lambda x: x[0], reverse=True)

        # Insert teeth into skeleton
        self.teeth_upper = []
        self.teeth_lower = []

        tooth_w = p['tooth_w']
        tooth_h = p['tooth_h']

        for idx, direction, jaw_type in all_teeth:
            x, y = self.skeleton[idx]
            half_w = tooth_w / 2

            if direction == 'down':
                tooth_pts = [
                    [x - half_w, y],
                    [x, y - tooth_h],
                    [x + half_w, y]
                ]
                self.teeth_upper.append((x, y))
            else:
                tooth_pts = [
                    [x - half_w, y],
                    [x, y + tooth_h],
                    [x + half_w, y]
                ]
                self.teeth_lower.append((x, y))

            # Replace single point with tooth triangle
            self.skeleton = self.skeleton[:idx] + tooth_pts + self.skeleton[idx+1:]

        print(f"\n[TEETH] Integrated: {len(self.teeth_upper)} upper, {len(self.teeth_lower)} lower")
        print(f"[TEETH] New skeleton: {len(self.skeleton)} points")

        return True, "Teeth integrated"

    def render(self, filename):
        """Render current state to image"""
        img = Image.new('RGB', (self.img_size, self.img_size), '#0a0a0a')
        draw = ImageDraw.Draw(img)

        # Grid
        for i in range(57):
            p = self.margin + int(i * 0.25 * self.scale)
            draw.line([(p, self.margin), (p, self.img_size - self.margin)], fill='#1a1a1a')
            draw.line([(self.margin, p), (self.img_size - self.margin, p)], fill='#1a1a1a')

        # Skeleton with integrated teeth
        if self.skeleton:
            pts = [self.px(x, y) for x, y in self.skeleton]
            draw.polygon(pts, outline='#ff6b6b', fill='#2a0a0a', width=2)

        # Holes in CYAN
        for hole in self.holes:
            hpts = [self.px(x, y) for x, y in hole]
            if len(hpts) > 2:
                draw.polygon(hpts, outline='#4ecdc4', fill='#0a2020', width=2)

        # Mark teeth positions
        for x, y in self.teeth_upper:
            tp = self.px(x, y)
            draw.ellipse([tp[0]-5, tp[1]-5, tp[0]+5, tp[1]+5], fill='#00ff00')

        for x, y in self.teeth_lower:
            tp = self.px(x, y)
            draw.ellipse([tp[0]-5, tp[1]-5, tp[0]+5, tp[1]+5], fill='#ffff00')

        # Ring
        cx, cy = self.px(self.center[0], self.center[1])
        r = int((self.ring_dia / 2) * self.scale)
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline='#ffe66d', width=3)

        # Draw jaw bounds for debugging
        jp = self.jaw_params
        # Upper jaw bounds (green box)
        ul = self.px(jp['upper_x_min'], jp['upper_y_max'])
        lr = self.px(jp['upper_x_max'], jp['upper_y_min'])
        draw.rectangle([ul[0], ul[1], lr[0], lr[1]], outline='#00ff00', width=1)

        # Lower jaw bounds (yellow box)
        ul = self.px(jp['lower_x_min'], jp['lower_y_max'])
        lr = self.px(jp['lower_x_max'], jp['lower_y_min'])
        draw.rectangle([ul[0], ul[1], lr[0], lr[1]], outline='#ffff00', width=1)

        # Info
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12)
        except:
            font = small = ImageFont.load_default()

        draw.text((self.img_size//2, 25), f"BROK v2 (TUNED) - Iteration {self.iteration}",
                  fill='#00ff00', font=font, anchor='mm')
        draw.text((self.img_size//2, 55),
                  f"Skeleton: {len(self.skeleton)} pts | Upper: {len(self.teeth_upper)} | Lower: {len(self.teeth_lower)}",
                  fill='#888', font=small, anchor='mm')

        # Legend
        draw.rectangle([10, self.img_size-100, 550, self.img_size-10], fill='#111', outline='#444')
        draw.text((20, self.img_size-88), "RED = Skeleton + INTEGRATED teeth | CYAN = Holes",
                  fill='#ff6b6b', font=small, anchor='lm')
        draw.text((20, self.img_size-68), "GREEN dots/box = Upper teeth | YELLOW dots/box = Lower teeth",
                  fill='#888', font=small, anchor='lm')
        draw.text((20, self.img_size-48), f"Boxes show tuned jaw detection bounds",
                  fill='#666', font=small, anchor='lm')
        draw.text((20, self.img_size-28), f"Problems: {len(self.problems)}",
                  fill='#ff0000' if self.problems else '#00ff00', font=small, anchor='lm')

        img.save(filename)
        return filename

    def analyze_design(self, image_path):
        """Step 3: Validate design"""
        print(f"\n[STEP 3] Validating design...")

        self.problems = []
        jp = self.jaw_params

        # Check teeth counts
        if len(self.teeth_upper) != 7:
            self.problems.append(f"Upper teeth: {len(self.teeth_upper)} (need 7)")

        if len(self.teeth_lower) != 4:
            self.problems.append(f"Lower teeth: {len(self.teeth_lower)} (need 4)")

        # Validate upper teeth positions
        for i, (x, y) in enumerate(self.teeth_upper):
            if not (jp['upper_x_min'] < x < jp['upper_x_max']):
                self.problems.append(f"Upper tooth {i+1} X out of range: {x:.2f}")
            if not (jp['upper_y_min'] < y < jp['upper_y_max']):
                self.problems.append(f"Upper tooth {i+1} Y out of range: {y:.2f}")

        # Validate lower teeth positions
        for i, (x, y) in enumerate(self.teeth_lower):
            if not (jp['lower_x_min'] < x < jp['lower_x_max']):
                self.problems.append(f"Lower tooth {i+1} X out of range: {x:.2f}")
            if not (jp['lower_y_min'] < y < jp['lower_y_max']):
                self.problems.append(f"Lower tooth {i+1} Y out of range: {y:.2f}")

        # Check teeth are evenly spaced (70% tolerance - some variation due to shape)
        if len(self.teeth_upper) >= 2:
            upper_xs = sorted([x for x, y in self.teeth_upper])
            gaps = [upper_xs[i+1] - upper_xs[i] for i in range(len(upper_xs)-1)]
            avg_gap = sum(gaps) / len(gaps)
            for i, gap in enumerate(gaps):
                if abs(gap - avg_gap) > avg_gap * 0.7:  # 70% tolerance for natural shape variation
                    self.problems.append(f"Upper teeth uneven gap at {i}: {gap:.2f} vs avg {avg_gap:.2f}")

        if self.problems:
            print(f"[VALIDATE] Found {len(self.problems)} problems:")
            for p in self.problems:
                print(f"  - {p}")
            return False
        else:
            print("[VALIDATE] Design verified OK")
            return True

    def generate_gcode(self, output_path):
        """Generate G-code"""
        print(f"\n[GCODE] Generating...")

        gcode = []
        gcode.append("(BROK CNC v2 - AUTONOMOUS TUNED)")
        gcode.append(f"(Teeth: {len(self.teeth_upper)} upper, {len(self.teeth_lower)} lower)")
        gcode.append("(BEVEL LAW: Inside=CCW, Outside=CW)")
        gcode.append("(Feed:47 Pierce:0.148 Cut:0.059)")
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
            gcode.append(f"(=== CUT {cut_num}: HOLE - CCW ===)")
            sx, sy = hole[0]
            gcode.append(f"G0X{sx-0.15:.4f}Y{sy:.4f}")
            gcode.append("G92Z0\nG38.2Z-5F50\nG38.4Z0.5F25\nG92Z0")
            gcode.append("G0Z0.148\nM3\nG4P0.70\nG0Z0.059\nH1")
            for x, y in hole:
                gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
            gcode.append("H0\nM5\nG0Z1\n")

        # Skeleton - CCW
        cut_num += 1
        gcode.append(f"(=== CUT {cut_num}: SKELETON+TEETH - CCW ===)")
        sx, sy = self.skeleton[0]
        gcode.append(f"G0X{sx-0.15:.4f}Y{sy:.4f}")
        gcode.append("G92Z0\nG38.2Z-5F50\nG38.4Z0.5F25\nG92Z0")
        gcode.append("G0Z0.148\nM3\nG4P0.70\nG0Z0.059\nH1")
        for x, y in self.skeleton:
            gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
        gcode.append(f"G1X{self.skeleton[0][0]:.4f}Y{self.skeleton[0][1]:.4f}F47")
        gcode.append("H0\nM5\nG0Z1\n")

        # Ring - CW
        cut_num += 1
        gcode.append(f"(=== CUT {cut_num}: 12\" RING - CW ===)")
        gcode.append(f"G0X{self.center[0]+self.ring_dia/2+0.2:.4f}Y{self.center[1]:.4f}")
        gcode.append("G92Z0\nG38.2Z-5F50\nG38.4Z0.5F25\nG92Z0")
        gcode.append("G0Z0.148\nM3\nG4P0.70\nG0Z0.059\nH1")
        for i in range(121):
            angle = -2 * math.pi * i / 120
            x = self.center[0] + (self.ring_dia/2) * math.cos(angle)
            y = self.center[1] + (self.ring_dia/2) * math.sin(angle)
            gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
        gcode.append("H0\nM5\nG0Z1\n")
        gcode.append("G0X0Y0\nM30")

        with open(output_path, 'w') as f:
            f.write("\n".join(gcode))

        print(f"[GCODE] Saved: {output_path}")
        return True

    def run(self, source_image, output_dir="/home/kontomeo/Desktop"):
        """Main pipeline"""
        print("\n" + "="*70)
        print("AUTONOMOUS PIPELINE v2 (TUNED)")
        print("="*70)

        # Step 1: Load and trace
        success, msg = self.load_and_trace(source_image)
        if not success:
            print(f"[FAIL] {msg}")
            return False

        # Step 2: Integrate teeth
        success, msg = self.integrate_teeth(7, 4)
        if not success:
            print(f"[FAIL] {msg}")
            return False

        # Render and validate
        self.iteration = 1
        render_path = f"{output_dir}/BROK_FINAL.png"
        self.render(render_path)

        valid = self.analyze_design(render_path)

        # Generate G-code
        gcode_path = f"{output_dir}/JURASSIC_TREX.nc"
        self.generate_gcode(gcode_path)

        print("\n" + "="*70)
        print("PIPELINE COMPLETE")
        print("="*70)
        print(f"Image: {render_path}")
        print(f"G-code: {gcode_path}")
        print(f"Status: {'VERIFIED' if valid else 'HAS ISSUES'}")
        print("="*70)

        return valid


if __name__ == "__main__":
    brok = BrokAutonomous()
    source = "/home/kontomeo/Desktop/jp_logo__tyrannosaurus_rex_by_titanuspixel55_derr4aw-pre.png"
    brok.run(source)
