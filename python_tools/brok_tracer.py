#!/usr/bin/env python3
"""
BROK CNC - Grid Trace System
============================
1. Load source image as background
2. Overlay precision grid (inches/mm)
3. Trace contours onto grid layer
4. Edit traces (add teeth, modify)
5. Remove source = clean traced design
6. Export to G-code

Usage:
  python3 brok_tracer.py [command] [options]

Commands:
  load <image>     - Load source image as background
  grid             - Show grid overlay on source
  trace            - Auto-trace source contours to grid
  teeth <7,4>      - Add teeth (upper,lower count)
  show             - Show current state
  export           - Remove source, export clean trace
  gcode            - Generate G-code from trace
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import math
import json
import sys
import os

class BrokTracer:
    def __init__(self):
        # Workspace settings (inches)
        self.workspace_size = 14.0  # 14" x 14" workspace
        self.ring_diameter = 12.0   # 12" ring
        self.center = (6.75, 6.75)  # Center point

        # Grid settings
        self.grid_major = 1.0       # Major grid every 1"
        self.grid_minor = 0.25      # Minor grid every 0.25" (6.35mm)
        self.grid_mm = 25.4         # mm per inch

        # Image size
        self.img_size = 2000
        self.margin = 80
        self.scale = (self.img_size - 2*self.margin) / self.workspace_size

        # Layers
        self.source_image = None    # Original image (background)
        self.source_visible = True  # Show/hide source
        self.traces = {
            'skeleton': [],         # Main outline points [(x,y), ...]
            'holes': [],            # List of hole contours
            'teeth_upper': [],      # Upper teeth [(x,y,w,h), ...]
            'teeth_lower': [],      # Lower teeth
            'ring': True            # Include ring
        }

        # State file
        self.state_file = "/home/kontomeo/Desktop/BROK_STATE.json"

        print("="*60)
        print("BROK CNC - Grid Trace System")
        print("="*60)
        print(f"Workspace: {self.workspace_size}\" x {self.workspace_size}\"")
        print(f"Grid: Major={self.grid_major}\", Minor={self.grid_minor}\" ({self.grid_minor*self.grid_mm:.1f}mm)")
        print(f"Ring: {self.ring_diameter}\" diameter")
        print("="*60)

    def px(self, x, y):
        """Convert inches to pixels"""
        return (
            self.margin + int(x * self.scale),
            self.img_size - self.margin - int(y * self.scale)
        )

    def inches(self, px_x, px_y):
        """Convert pixels to inches"""
        x = (px_x - self.margin) / self.scale
        y = (self.img_size - self.margin - px_y) / self.scale
        return (x, y)

    def load_source(self, image_path):
        """Load source image as background"""
        print(f"\n[LOAD] Loading source: {image_path}")

        img = cv2.imread(image_path)
        if img is None:
            print(f"[ERROR] Cannot load image: {image_path}")
            return False

        h, w = img.shape[:2]
        print(f"[LOAD] Image size: {w}x{h}")

        # Store original
        self.source_image = img
        self.source_path = image_path

        # Calculate scale to fit in ring
        fit_size = self.ring_diameter - 0.5  # Leave margin
        img_scale = fit_size / max(h, w)

        self.source_scale = img_scale
        self.source_offset = (
            self.center[0] - (w * img_scale / 2),
            self.center[1] - (h * img_scale / 2)
        )

        print(f"[LOAD] Fit scale: {img_scale:.4f} ({fit_size}\" target)")
        print(f"[LOAD] Offset: ({self.source_offset[0]:.2f}\", {self.source_offset[1]:.2f}\")")

        return True

    def auto_trace(self):
        """Auto-trace source image contours"""
        if self.source_image is None:
            print("[ERROR] No source image loaded")
            return False

        print("\n[TRACE] Auto-tracing source image...")

        img = self.source_image
        h, w = img.shape[:2]

        # Convert to grayscale and threshold
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY_INV)

        # Find contours with full detail
        contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)

        print(f"[TRACE] Found {len(contours)} contours")

        # Find main silhouette (largest non-circular)
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
            print("[ERROR] No suitable contour found")
            return False

        # Convert to workspace coordinates
        skeleton = []
        for pt in best:
            px, py = pt[0]
            x = px * self.source_scale + self.source_offset[0]
            y = (h - py) * self.source_scale + self.source_offset[1]
            skeleton.append((x, y))

        # Simplify (keep every Nth point for manageable size)
        step = max(1, len(skeleton) // 500)
        self.traces['skeleton'] = skeleton[::step]

        print(f"[TRACE] Skeleton: {len(self.traces['skeleton'])} points")

        # Find interior holes
        self.traces['holes'] = []
        if hierarchy is not None:
            for i, (cnt, hier) in enumerate(zip(contours, hierarchy[0])):
                parent_idx = hier[3]
                if parent_idx >= 0:
                    area = cv2.contourArea(cnt)
                    if 500 < area < 30000:
                        hole_pts = []
                        for pt in cnt[::3]:  # Simplify
                            px, py = pt[0]
                            x = px * self.source_scale + self.source_offset[0]
                            y = (h - py) * self.source_scale + self.source_offset[1]
                            hole_pts.append((x, y))

                        # Check if in workspace
                        xs = [p[0] for p in hole_pts]
                        ys = [p[1] for p in hole_pts]
                        cx, cy = sum(xs)/len(xs), sum(ys)/len(ys)

                        # Keep only real holes (eye, skull) not tooth gaps
                        if area > 2000 and 1 < min(xs) and max(xs) < 13:
                            self.traces['holes'].append(hole_pts)
                            print(f"[TRACE] Hole: {len(hole_pts)} pts at ({cx:.2f}, {cy:.2f})")

        print(f"[TRACE] Total holes: {len(self.traces['holes'])}")
        return True

    def add_teeth(self, upper_count=7, lower_count=4):
        """Add teeth to traced skeleton"""
        if not self.traces['skeleton']:
            print("[ERROR] No skeleton traced yet")
            return False

        print(f"\n[TEETH] Adding {upper_count} upper, {lower_count} lower teeth...")

        skeleton = self.traces['skeleton']

        # Find jaw regions
        upper_jaw = [(i, x, y) for i, (x, y) in enumerate(skeleton)
                     if x > 9.0 and 8.3 < y < 10.0]
        lower_jaw = [(i, x, y) for i, (x, y) in enumerate(skeleton)
                     if x > 9.0 and 6.5 < y < 7.8]

        print(f"[TEETH] Upper jaw points: {len(upper_jaw)}")
        print(f"[TEETH] Lower jaw points: {len(lower_jaw)}")

        # Select evenly spaced positions
        def select_positions(jaw_pts, count):
            if len(jaw_pts) < count:
                return jaw_pts
            sorted_pts = sorted(jaw_pts, key=lambda p: p[1])
            start = int(len(sorted_pts) * 0.15)
            end = len(sorted_pts) - 2
            step = (end - start) / max(1, count - 1)
            return [sorted_pts[int(start + i * step)] for i in range(count)]

        # Tooth size (15% bigger)
        tooth_w = 0.40
        tooth_h = 0.52

        # Store teeth positions
        self.traces['teeth_upper'] = []
        for idx, x, y in select_positions(upper_jaw, upper_count):
            self.traces['teeth_upper'].append((x, y, tooth_w, tooth_h, 'down'))
            print(f"[TEETH] Upper: ({x:.2f}, {y:.2f}) -> down")

        self.traces['teeth_lower'] = []
        for idx, x, y in select_positions(lower_jaw, lower_count):
            self.traces['teeth_lower'].append((x, y, tooth_w, tooth_h, 'up'))
            print(f"[TEETH] Lower: ({x:.2f}, {y:.2f}) -> up")

        return True

    def render(self, show_source=True, show_grid=True, output_path=None):
        """Render current state to image"""
        print(f"\n[RENDER] Creating image...")

        img = Image.new('RGB', (self.img_size, self.img_size), '#0a0a0a')
        draw = ImageDraw.Draw(img)

        # Draw source image as background (if visible)
        if show_source and self.source_image is not None:
            src = self.source_image
            h, w = src.shape[:2]

            # Convert BGR to RGB
            src_rgb = cv2.cvtColor(src, cv2.COLOR_BGR2RGB)
            src_pil = Image.fromarray(src_rgb)

            # Scale and position
            new_w = int(w * self.source_scale * self.scale)
            new_h = int(h * self.source_scale * self.scale)
            src_resized = src_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Calculate position
            pos_x = self.margin + int(self.source_offset[0] * self.scale)
            pos_y = self.img_size - self.margin - int((self.source_offset[1] + h * self.source_scale) * self.scale)

            # Paste with transparency effect
            src_dark = Image.blend(Image.new('RGB', src_resized.size, '#0a0a0a'), src_resized, 0.4)
            img.paste(src_dark, (pos_x, pos_y))

        # Draw grid
        if show_grid:
            # Minor grid
            for i in range(int(self.workspace_size / self.grid_minor) + 1):
                val = i * self.grid_minor
                p = self.margin + int(val * self.scale)
                draw.line([(p, self.margin), (p, self.img_size - self.margin)], fill='#1a1a1a')
                draw.line([(self.margin, p), (self.img_size - self.margin, p)], fill='#1a1a1a')

            # Major grid
            for i in range(int(self.workspace_size / self.grid_major) + 1):
                val = i * self.grid_major
                p = self.margin + int(val * self.scale)
                draw.line([(p, self.margin), (p, self.img_size - self.margin)], fill='#2a2a2a', width=2)
                draw.line([(self.margin, p), (self.img_size - self.margin, p)], fill='#2a2a2a', width=2)

        # Draw skeleton trace in RED
        if self.traces['skeleton']:
            pts = [self.px(x, y) for x, y in self.traces['skeleton']]
            if len(pts) > 2:
                draw.polygon(pts, outline='#ff6b6b', fill='#2a0a0a', width=2)

        # Draw holes in CYAN
        for hole in self.traces['holes']:
            if len(hole) > 2:
                pts = [self.px(x, y) for x, y in hole]
                draw.polygon(pts, outline='#4ecdc4', fill='#0a2020', width=2)

        # Draw teeth in GREEN (upper) and YELLOW (lower)
        for x, y, tw, th, direction in self.traces['teeth_upper']:
            half_w = tw / 2
            if direction == 'down':
                tooth = [self.px(x - half_w, y), self.px(x, y - th), self.px(x + half_w, y)]
            else:
                tooth = [self.px(x - half_w, y), self.px(x, y + th), self.px(x + half_w, y)]
            draw.polygon(tooth, outline='#00ff00', fill='#0a3a0a', width=2)

        for x, y, tw, th, direction in self.traces['teeth_lower']:
            half_w = tw / 2
            if direction == 'up':
                tooth = [self.px(x - half_w, y), self.px(x, y + th), self.px(x + half_w, y)]
            else:
                tooth = [self.px(x - half_w, y), self.px(x, y - th), self.px(x + half_w, y)]
            draw.polygon(tooth, outline='#ffff00', fill='#3a3a0a', width=2)

        # Draw ring
        if self.traces['ring']:
            cx, cy = self.px(self.center[0], self.center[1])
            r = int((self.ring_diameter / 2) * self.scale)
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline='#ffe66d', width=3)

        # Title and info
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12)
        except:
            font = small = ImageFont.load_default()

        mode = "TRACE MODE" if show_source else "EXPORT MODE"
        draw.text((self.img_size//2, 25), f"BROK TRACER - {mode}", fill='#00ff00', font=font, anchor='mm')

        info = f"Grid: {self.grid_minor}\" ({self.grid_minor*self.grid_mm:.1f}mm) | "
        info += f"Skeleton: {len(self.traces['skeleton'])} pts | "
        info += f"Teeth: {len(self.traces['teeth_upper'])}U + {len(self.traces['teeth_lower'])}L"
        draw.text((self.img_size//2, 55), info, fill='#888', font=small, anchor='mm')

        # Legend
        draw.rectangle([10, self.img_size-100, 400, self.img_size-10], fill='#111', outline='#444')
        draw.text((20, self.img_size-88), "RED = Traced skeleton", fill='#ff6b6b', font=small, anchor='lm')
        draw.text((20, self.img_size-70), "CYAN = Holes | GREEN = Upper teeth | YELLOW = Lower teeth", fill='#888', font=small, anchor='lm')
        draw.text((20, self.img_size-52), f"Source: {'VISIBLE' if show_source else 'HIDDEN'}", fill='#ffff00' if show_source else '#666', font=small, anchor='lm')

        # Scale reference
        ref_len = 1.0  # 1 inch reference
        ref_px = int(ref_len * self.scale)
        ref_y = self.img_size - 130
        draw.line([(self.img_size - 150, ref_y), (self.img_size - 150 + ref_px, ref_y)], fill='#ffffff', width=2)
        draw.text((self.img_size - 150 + ref_px//2, ref_y - 15), f'{ref_len}" = {ref_len * self.grid_mm:.1f}mm', fill='#fff', font=small, anchor='mm')

        # Save
        if output_path is None:
            output_path = '/home/kontomeo/Desktop/BROK_TRACE.png'

        img.save(output_path)
        print(f"[RENDER] Saved: {output_path}")

        return output_path

    def save_state(self):
        """Save current state to file"""
        state = {
            'source_path': getattr(self, 'source_path', None),
            'source_scale': getattr(self, 'source_scale', None),
            'source_offset': getattr(self, 'source_offset', None),
            'traces': self.traces
        }

        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)

        print(f"[SAVE] State saved to {self.state_file}")

    def load_state(self):
        """Load state from file"""
        if not os.path.exists(self.state_file):
            print(f"[LOAD] No state file found")
            return False

        with open(self.state_file, 'r') as f:
            state = json.load(f)

        if state.get('source_path'):
            self.load_source(state['source_path'])

        self.traces = state.get('traces', self.traces)
        print(f"[LOAD] State loaded from {self.state_file}")
        return True


# Main execution
if __name__ == "__main__":
    tracer = BrokTracer()

    # Load JP logo
    source = "/home/kontomeo/Desktop/jp_logo__tyrannosaurus_rex_by_titanuspixel55_derr4aw-pre.png"
    tracer.load_source(source)

    # Auto-trace
    tracer.auto_trace()

    # Add teeth (7 upper, 4 lower)
    tracer.add_teeth(7, 4)

    # Render with source visible (trace mode)
    tracer.render(show_source=True, output_path='/home/kontomeo/Desktop/BROK_TRACE_SOURCE.png')

    # Render without source (export mode)
    tracer.render(show_source=False, output_path='/home/kontomeo/Desktop/BROK_TRACE_CLEAN.png')

    # Save state
    tracer.save_state()

    print("\n" + "="*60)
    print("BROK TRACER COMPLETE")
    print("="*60)
    print("BROK_TRACE_SOURCE.png = With source image (for tracing)")
    print("BROK_TRACE_CLEAN.png  = Clean trace (for export)")
    print("="*60)
