#!/usr/bin/env python3
"""
BROK CNC - GPS Grid Placement System + BEVEL LAW
=================================================
Uses coordinate grid overlay for precise feature placement.
BEVEL LAW: Workpiece always gets SQUARE edge (torch RIGHT side).

BEVEL LAW (CW Swirl Plasma):
============================
- Travel direction → BEVEL on LEFT, SQUARE on RIGHT
- Inside holes: Cut CCW → workpiece on RIGHT → SQUARE
- Outside perimeter: Cut CW → workpiece on RIGHT → SQUARE
- Short lines/artwork: Both sides retained = acceptable (no choice)
- User can override, but this is STRICT DEFAULT
"""
import re
import math
from PIL import Image, ImageDraw, ImageFont

class BrokCNC:
    """BROK CNC with GPS grid + BEVEL LAW"""

    # BEVEL LAW CONSTANTS
    BEVEL_LAW = """
    ╔═══════════════════════════════════════════════════════╗
    ║              BROK CNC BEVEL LAW                       ║
    ╠═══════════════════════════════════════════════════════╣
    ║  Travel → BEVEL on LEFT, SQUARE on RIGHT              ║
    ║  Inside holes:    CCW = square on workpiece           ║
    ║  Outside cuts:    CW  = square on workpiece           ║
    ║  Short lines:     Both sides = acceptable             ║
    ╚═══════════════════════════════════════════════════════╝
    """

    def __init__(self):
        self.grid_size = 0.5  # Half-inch grid squares
        self.workpiece_size = 14.0  # 14" workspace
        self.scale = 100  # pixels per inch for visualization
        self.points = []
        self.holes = []
        self.features = {}
        self.bevel_override = False  # User can override bevel law

    def print_bevel_law(self):
        """Display the bevel law"""
        print(self.BEVEL_LAW)

    def load_gcode(self, filepath):
        """Load G-code and extract skeleton + holes"""
        with open(filepath, 'r') as f:
            lines = f.readlines()

        self.points = []
        self.holes = []
        current_hole = []
        in_skeleton = False
        in_hole = False

        for line in lines:
            line = line.strip()

            if 'HOLE' in line and 'CUT' in line:
                if current_hole:
                    self.holes.append(current_hole)
                current_hole = []
                in_hole = True
                in_skeleton = False
            elif 'SKELETON' in line:
                if current_hole:
                    self.holes.append(current_hole)
                    current_hole = []
                in_skeleton = True
                in_hole = False
            elif 'RING' in line:
                in_skeleton = False
                in_hole = False

            m = re.match(r'G1X([-\d.]+)Y([-\d.]+)', line)
            if m:
                x, y = float(m.group(1)), float(m.group(2))
                if in_hole:
                    current_hole.append((x, y))
                elif in_skeleton:
                    self.points.append((x, y))

        if current_hole:
            self.holes.append(current_hole)

        print(f"[BROK] Loaded {len(self.points)} skeleton points, {len(self.holes)} holes")
        return self

    def grid_coord(self, x, y):
        """Convert inches to grid coordinates (A1, B2, etc.)"""
        col = chr(65 + int(x / self.grid_size))
        row = int(y / self.grid_size) + 1
        return f"{col}{row}"

    def analyze_skeleton(self):
        """Analyze skeleton to identify jaw regions for teeth"""
        if not self.points:
            return {}

        min_x = min(p[0] for p in self.points)
        max_x = max(p[0] for p in self.points)
        min_y = min(p[1] for p in self.points)
        max_y = max(p[1] for p in self.points)
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2

        self.features = {
            'snout_tip': None,
            'upper_jaw': [],
            'lower_jaw': [],
            'back_spines': [],
            'body': []
        }

        snout_tip = max(self.points, key=lambda p: p[0])
        self.features['snout_tip'] = snout_tip
        snout_y = snout_tip[1]

        for i, (x, y) in enumerate(self.points):
            if x > center_x + 2 and y > snout_y - 1 and y < snout_y + 3:
                self.features['upper_jaw'].append((i, x, y))
            elif x > center_x + 1 and y < snout_y - 1 and y > snout_y - 4:
                self.features['lower_jaw'].append((i, x, y))
            elif x < center_x - 1:
                self.features['back_spines'].append((i, x, y))
            else:
                self.features['body'].append((i, x, y))

        print(f"[BROK GPS] Snout tip at {self.grid_coord(*snout_tip)}")
        print(f"[BROK GPS] Upper jaw: {len(self.features['upper_jaw'])} points")
        print(f"[BROK GPS] Lower jaw: {len(self.features['lower_jaw'])} points")
        return self.features

    def add_teeth(self, jaw='both', tooth_height=0.3, num_teeth=6):
        """Add teeth to jaw edges using GPS coordinates"""
        if not self.features:
            self.analyze_skeleton()

        teeth_added = 0
        insertions = []

        if jaw in ['both', 'upper'] and self.features['upper_jaw']:
            upper_pts = sorted(self.features['upper_jaw'], key=lambda p: p[1])
            step = max(1, len(upper_pts) // num_teeth)
            for j in range(0, len(upper_pts), step):
                if j < len(upper_pts) and teeth_added < num_teeth:
                    idx, x, y = upper_pts[j]
                    tooth = [(x - 0.12, y), (x, y - tooth_height), (x + 0.12, y)]
                    insertions.append((idx, tooth))
                    teeth_added += 1
                    print(f"[BROK] Upper tooth at {self.grid_coord(x, y)}")

        if jaw in ['both', 'lower'] and self.features['lower_jaw']:
            lower_pts = sorted(self.features['lower_jaw'], key=lambda p: p[1])
            step = max(1, len(lower_pts) // num_teeth)
            lower_added = 0
            for j in range(0, len(lower_pts), step):
                if j < len(lower_pts) and lower_added < num_teeth:
                    idx, x, y = lower_pts[j]
                    tooth = [(x - 0.12, y), (x, y + tooth_height), (x + 0.12, y)]
                    insertions.append((idx, tooth))
                    lower_added += 1
                    teeth_added += 1
                    print(f"[BROK] Lower tooth at {self.grid_coord(x, y)}")

        insertions.sort(key=lambda x: x[0], reverse=True)
        new_points = list(self.points)
        for idx, tooth in insertions:
            new_points = new_points[:idx] + tooth + new_points[idx+1:]

        self.points = new_points
        print(f"[BROK] Added {teeth_added} teeth, skeleton now {len(self.points)} points")
        return self

    def ensure_ccw(self, points):
        """
        BEVEL LAW: Ensure contour is CCW for inside cuts.
        CCW = workpiece on RIGHT = SQUARE edge on workpiece.
        """
        if len(points) < 3:
            return points

        # Calculate signed area (shoelace formula)
        area = 0
        n = len(points)
        for i in range(n):
            j = (i + 1) % n
            area += points[i][0] * points[j][1]
            area -= points[j][0] * points[i][1]

        # Negative area = CW, need to reverse for CCW
        if area > 0:  # Currently CW
            print("[BEVEL LAW] Reversing to CCW for inside cut")
            return list(reversed(points))
        return points

    def ensure_cw(self, points):
        """
        BEVEL LAW: Ensure contour is CW for outside cuts.
        CW = workpiece on RIGHT = SQUARE edge on workpiece.
        """
        if len(points) < 3:
            return points

        area = 0
        n = len(points)
        for i in range(n):
            j = (i + 1) % n
            area += points[i][0] * points[j][1]
            area -= points[j][0] * points[i][1]

        if area < 0:  # Currently CCW
            print("[BEVEL LAW] Reversing to CW for outside cut")
            return list(reversed(points))
        return points

    def generate_circle_cw(self, cx, cy, radius, num_points=120):
        """
        BEVEL LAW: Generate CW circle for outside cuts.
        Start at right (3 o'clock), go DOWN first (clockwise).
        """
        points = []
        for i in range(num_points + 1):
            angle = -2 * math.pi * i / num_points  # Negative = CW
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            points.append((x, y))
        return points

    def generate_circle_ccw(self, cx, cy, radius, num_points=120):
        """
        BEVEL LAW: Generate CCW circle for inside cuts.
        Start at right (3 o'clock), go UP first (counter-clockwise).
        """
        points = []
        for i in range(num_points + 1):
            angle = 2 * math.pi * i / num_points  # Positive = CCW
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            points.append((x, y))
        return points

    def generate_gps_grid_image(self, output_path, title="BROK CNC GPS VIEW"):
        """Generate image with GPS grid overlay"""
        img_size = int(self.workpiece_size * self.scale)
        margin = 50
        total_size = img_size + 2 * margin

        img = Image.new('RGB', (total_size, total_size), '#0a0a0a')
        draw = ImageDraw.Draw(img)

        def to_px(x, y):
            return (margin + int(x * self.scale),
                    total_size - margin - int(y * self.scale))

        # Draw GPS grid
        for i in range(int(self.workpiece_size / self.grid_size) + 1):
            x = i * self.grid_size
            px = margin + int(x * self.scale)
            draw.line([(px, margin), (px, total_size - margin)], fill='#1a3a1a', width=1)
            if i < 26:
                draw.text((px, margin - 15), chr(65 + i), fill='#3a5a3a', anchor='mm')
            y = i * self.grid_size
            py = total_size - margin - int(y * self.scale)
            draw.line([(margin, py), (total_size - margin, py)], fill='#1a3a1a', width=1)
            draw.text((margin - 20, py), str(i+1), fill='#3a5a3a', anchor='mm')

        # Draw holes (cyan) - CCW per BEVEL LAW
        for hole in self.holes:
            if len(hole) > 2:
                pts = [to_px(x, y) for x, y in hole]
                draw.polygon(pts, outline='#4ecdc4', width=2)

        # Draw skeleton (red)
        if len(self.points) > 1:
            pts = [to_px(x, y) for x, y in self.points]
            for i in range(len(pts) - 1):
                draw.line([pts[i], pts[i+1]], fill='#ff6b6b', width=2)

        # Draw 12" ring (yellow) - CW per BEVEL LAW
        center = to_px(6.75, 6.75)
        radius = int(6.0 * self.scale)
        draw.ellipse([center[0]-radius, center[1]-radius,
                      center[0]+radius, center[1]+radius],
                     outline='#ffe66d', width=2)

        # Mark features
        if self.features.get('snout_tip'):
            st = to_px(*self.features['snout_tip'])
            draw.ellipse([st[0]-8, st[1]-8, st[0]+8, st[1]+8], outline='#00ff00', width=2)
            draw.text((st[0]+12, st[1]), "SNOUT", fill='#00ff00')

        # Title and BEVEL LAW indicator
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 11)
        except:
            font = small = ImageFont.load_default()

        draw.text((total_size//2, 25), title, fill='#00ff00', font=font, anchor='mm')

        # BEVEL LAW box
        draw.rectangle([total_size-220, 50, total_size-10, 130], fill='#1a1a2a', outline='#4a4a6a')
        draw.text((total_size-115, 60), "BEVEL LAW", fill='#ff0', font=small, anchor='mm')
        draw.text((total_size-210, 75), "Inside: CCW → SQUARE", fill='#4ecdc4', font=small)
        draw.text((total_size-210, 90), "Outside: CW → SQUARE", fill='#ffe66d', font=small)
        draw.text((total_size-210, 105), "Workpiece = NO BEVEL", fill='#8f8', font=small)

        # Legend
        draw.rectangle([10, total_size-90, 180, total_size-10], fill='#111', outline='#333')
        draw.text((20, total_size-80), f"Points: {len(self.points)}", fill='#888', font=small)
        draw.text((20, total_size-65), f"Holes: {len(self.holes)} (CCW)", fill='#4ecdc4', font=small)
        draw.text((20, total_size-50), "Ring: 12\" (CW)", fill='#ffe66d', font=small)
        draw.text((20, total_size-35), "Skeleton: CCW", fill='#ff6b6b', font=small)

        img.save(output_path)
        print(f"[BROK] GPS image saved: {output_path}")
        return self

    def generate_gcode(self, output_path, ring_diameter=12.0):
        """
        Generate G-code with BEVEL LAW enforced.
        - Inside holes: CCW
        - Skeleton (inside workpiece): CCW
        - Outside ring: CW
        """
        self.print_bevel_law()

        gcode = []
        gcode.append("(BROK CNC - BEVEL LAW ENFORCED)")
        gcode.append("(Inside cuts: CCW = square on workpiece)")
        gcode.append("(Outside cuts: CW = square on workpiece)")
        gcode.append("(Feed:47 Pierce:0.148 Cut:0.059)")
        gcode.append("(v1.6-af)")
        gcode.append("G20G90")
        gcode.append("G0X0.Y0.")
        gcode.append("H0")
        gcode.append("")

        cut_num = 0

        # HOLES - INSIDE CUTS - CCW (BEVEL LAW)
        for hi, hole in enumerate(self.holes):
            if len(hole) < 10:
                continue
            cut_num += 1

            # Enforce CCW for inside cut
            hole_ccw = self.ensure_ccw(hole)

            gcode.append(f"(=== CUT {cut_num}: HOLE - CCW [BEVEL LAW] ===)")
            sx, sy = hole_ccw[0]
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
            for x, y in hole_ccw:
                gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
            gcode.append("H0")
            gcode.append("M5")
            gcode.append("G0Z1")
            gcode.append("")

        # SKELETON - INSIDE CUT - CCW (BEVEL LAW)
        if self.points:
            cut_num += 1
            skeleton_ccw = self.ensure_ccw(self.points)

            gcode.append(f"(=== CUT {cut_num}: SKELETON - CCW [BEVEL LAW] ===)")
            sx, sy = skeleton_ccw[0]
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
            for x, y in skeleton_ccw:
                gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
            # Close contour
            gcode.append(f"G1X{skeleton_ccw[0][0]:.4f}Y{skeleton_ccw[0][1]:.4f}F47")
            gcode.append("H0")
            gcode.append("M5")
            gcode.append("G0Z1")
            gcode.append("")

        # OUTSIDE RING - CW (BEVEL LAW)
        cut_num += 1
        cx, cy = 6.75, 6.75
        radius = ring_diameter / 2.0
        ring_cw = self.generate_circle_cw(cx, cy, radius)

        gcode.append(f"(=== CUT {cut_num}: {ring_diameter}\" RING - CW [BEVEL LAW] ===)")
        sx, sy = ring_cw[0]
        gcode.append(f"G0X{sx+0.2:.4f}Y{sy:.4f}")
        gcode.append("G92Z0")
        gcode.append("G38.2Z-5F50")
        gcode.append("G38.4Z0.5F25")
        gcode.append("G92Z0")
        gcode.append("G0Z0.148")
        gcode.append("M3")
        gcode.append("G4P0.70")
        gcode.append("G0Z0.059")
        gcode.append("H1")
        for x, y in ring_cw:
            gcode.append(f"G1X{x:.4f}Y{y:.4f}F47")
        gcode.append("H0")
        gcode.append("M5")
        gcode.append("G0Z1")
        gcode.append("")

        gcode.append("G0X0Y0")
        gcode.append("M30")

        with open(output_path, 'w') as f:
            f.write("\n".join(gcode))

        print(f"[BROK] G-code saved: {output_path}")
        print(f"[BROK] Total cuts: {cut_num}")
        print("[BROK] BEVEL LAW: All cuts optimized for square edges on workpiece")
        return self


# === MAIN EXECUTION ===
if __name__ == "__main__":
    print("=" * 60)
    print("  BROK CNC - GPS GRID + BEVEL LAW SYSTEM")
    print("=" * 60)

    brok = BrokCNC()
    brok.print_bevel_law()

    # Load clean skeleton
    print("\n[BROK] Loading skeleton...")
    brok.load_gcode("/home/kontomeo/Desktop/JURASSIC_TREX.nc")

    # Analyze for jaw regions
    print("\n[BROK] GPS Analysis...")
    brok.analyze_skeleton()

    # Add teeth to jaws
    print("\n[BROK] Adding teeth to jaws...")
    brok.add_teeth(jaw='both', tooth_height=0.35, num_teeth=6)

    # Generate GPS view
    print("\n[BROK] Generating GPS view...")
    brok.generate_gps_grid_image(
        "/home/kontomeo/Desktop/BROK_TREX.png",
        "BROK CNC - T-REX WITH TEETH"
    )

    # Generate G-code with BEVEL LAW
    print("\n[BROK] Generating G-code (BEVEL LAW enforced)...")
    brok.generate_gcode("/home/kontomeo/Desktop/JURASSIC_TREX.nc", ring_diameter=12.0)

    print("\n" + "=" * 60)
    print("  BROK CNC COMPLETE - BEVEL LAW ENFORCED")
    print("=" * 60)
