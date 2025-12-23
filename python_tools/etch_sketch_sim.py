#!/usr/bin/env python3
"""Etch-a-sketch style toolpath visualization for BROK CNC using PIL"""
import re
from PIL import Image, ImageDraw, ImageFont
import math

# Parse G-code
gcode_file = "/home/kontomeo/Desktop/JURASSIC_TREX.nc"
with open(gcode_file, 'r') as f:
    lines = f.readlines()

# Extract movements
rapids = []  # G0 moves
cuts = []    # G1 moves by cut number
pierces = [] # Pierce points

x, y = 0.0, 0.0
in_cut = False
cut_num = 0
current_cut = []

for line in lines:
    line = line.strip()

    # New cut section
    if line.startswith('(=== CUT'):
        cut_num += 1
        if current_cut:
            cuts.append((cut_num - 1, current_cut))
        current_cut = []
        in_cut = False

    # M3 = torch on
    if 'M3' in line:
        pierces.append((x, y, cut_num))
        in_cut = True

    # M5 = torch off
    if 'M5' in line:
        in_cut = False
        if current_cut:
            cuts.append((cut_num, current_cut))
            current_cut = []

    # Parse G0 (rapid) - skip Z moves
    g0_match = re.match(r'G0X?([-\d.]+)?Y?([-\d.]+)?', line)
    if g0_match and 'Z' not in line:
        new_x = float(g0_match.group(1)) if g0_match.group(1) else x
        new_y = float(g0_match.group(2)) if g0_match.group(2) else y
        if (new_x, new_y) != (x, y):
            rapids.append(((x, y), (new_x, new_y)))
        x, y = new_x, new_y

    # Parse G1 (cut)
    g1_match = re.match(r'G1X([-\d.]+)Y([-\d.]+)', line)
    if g1_match:
        new_x = float(g1_match.group(1))
        new_y = float(g1_match.group(2))
        if in_cut:
            current_cut.append(((x, y), (new_x, new_y)))
        x, y = new_x, new_y

# Image settings
img_size = 1400
margin = 100
scale = (img_size - 2 * margin) / 14.0  # 14" workspace

def to_pixel(px, py):
    """Convert inches to pixels (flip Y for screen coords)"""
    return (margin + int(px * scale), img_size - margin - int(py * scale))

# Create image - dark background
img = Image.new('RGB', (img_size, img_size), '#1a1a1a')
draw = ImageDraw.Draw(img)

# Draw frame (etch-a-sketch border)
frame_color = '#8b4513'  # Brown like real etch-a-sketch
draw.rectangle([20, 20, img_size-20, img_size-20], outline=frame_color, width=8)
draw.rectangle([30, 30, img_size-30, img_size-30], outline='#654321', width=4)

# Draw grid (faint)
grid_color = '#2a2a2a'
for i in range(15):
    x_px = margin + int(i * scale)
    draw.line([(x_px, margin), (x_px, img_size - margin)], fill=grid_color, width=1)
    y_px = img_size - margin - int(i * scale)
    draw.line([(margin, y_px), (img_size - margin, y_px)], fill=grid_color, width=1)

# Color palette
cut_colors = [
    '#4ecdc4',  # Cyan - holes
    '#4ecdc4',
    '#4ecdc4',
    '#ff6b6b',  # Red - skeleton
    '#88ff88',  # Green - inner ring
    '#ffe66d',  # Yellow - outer ring
]

# Draw rapids (dashed grey)
rapid_color = '#444444'
for (x1, y1), (x2, y2) in rapids:
    p1 = to_pixel(x1, y1)
    p2 = to_pixel(x2, y2)
    # Draw dashed line
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    dist = math.sqrt(dx*dx + dy*dy)
    if dist > 0:
        dash_len = 8
        num_dashes = int(dist / (dash_len * 2))
        for i in range(num_dashes):
            t1 = (i * 2 * dash_len) / dist
            t2 = ((i * 2 + 1) * dash_len) / dist
            if t2 > 1: t2 = 1
            dp1 = (int(p1[0] + dx * t1), int(p1[1] + dy * t1))
            dp2 = (int(p1[0] + dx * t2), int(p1[1] + dy * t2))
            draw.line([dp1, dp2], fill=rapid_color, width=1)

# Draw cuts by cut number
for cut_idx, segments in cuts:
    color = cut_colors[min(cut_idx - 1, len(cut_colors) - 1)]
    for (x1, y1), (x2, y2) in segments:
        p1 = to_pixel(x1, y1)
        p2 = to_pixel(x2, y2)
        draw.line([p1, p2], fill=color, width=3)

# Draw pierce points (circles with inner dot)
for px, py, cn in pierces:
    color = cut_colors[min(cn - 1, len(cut_colors) - 1)]
    pp = to_pixel(px, py)
    draw.ellipse([pp[0]-8, pp[1]-8, pp[0]+8, pp[1]+8], outline='white', width=2)
    draw.ellipse([pp[0]-3, pp[1]-3, pp[0]+3, pp[1]+3], fill=color)

# Draw start point (green)
start = to_pixel(0, 0)
draw.ellipse([start[0]-12, start[1]-12, start[0]+12, start[1]+12], fill='#00ff00', outline='white', width=2)

# Title
try:
    title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    sub_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    mono_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)
except:
    title_font = ImageFont.load_default()
    sub_font = title_font
    mono_font = title_font

draw.text((img_size//2, 50), "BROK CNC ETCH-A-SKETCH", fill='white', font=title_font, anchor='mm')
draw.text((img_size//2, 80), "Jurassic Park T-Rex Logo - 13.5\" outer × 12\" inner", fill='#888888', font=sub_font, anchor='mm')

# Legend box
legend_x = 60
legend_y = img_size - 200
draw.rectangle([legend_x-10, legend_y-10, legend_x+280, legend_y+160], fill='#222222', outline='#444444', width=2)

legend_items = [
    ('#4ecdc4', 'Holes (CCW) - Cuts 1-3'),
    ('#ff6b6b', 'Skeleton w/teeth - Cut 4'),
    ('#88ff88', 'Inner Ring 12" - Cut 5'),
    ('#ffe66d', 'Outer Ring 13.5" - Cut 6'),
    ('#444444', 'Rapids (pen up)'),
]

for i, (color, label) in enumerate(legend_items):
    y_pos = legend_y + i * 28
    draw.rectangle([legend_x, y_pos, legend_x+20, y_pos+16], fill=color)
    draw.text((legend_x+30, y_pos+8), label, fill='white', font=mono_font, anchor='lm')

# Stats box
stats_x = img_size - 290
draw.rectangle([stats_x-10, legend_y-10, stats_x+250, legend_y+160], fill='#222222', outline='#444444', width=2)

stats = [
    f"Rapids: {len(rapids)} moves",
    f"Cut segments: {sum(len(s) for _, s in cuts)}",
    f"Pierce points: {len(pierces)}",
    f"Feed: 47 IPM",
    f"Pierce: 0.148\"",
    f"Cut height: 0.059\"",
]

for i, stat in enumerate(stats):
    draw.text((stats_x, legend_y + i * 24), stat, fill='#aaaaaa', font=mono_font)

# Cut sequence
seq_x = img_size - 200
seq_y = 120
draw.rectangle([seq_x-10, seq_y-10, seq_x+180, seq_y+160], fill='#222222', outline='#444444', width=2)
draw.text((seq_x, seq_y), "CUT SEQUENCE:", fill='white', font=mono_font)
sequence = [
    "1. Eye socket",
    "2. Jaw opening",
    "3. Nostril",
    "4. T-Rex skeleton",
    "5. Inner ring 12\"",
    "6. Outer ring 13.5\"",
]
for i, item in enumerate(sequence):
    color = cut_colors[min(i, len(cut_colors)-1)]
    draw.text((seq_x, seq_y + 22 + i * 22), item, fill=color, font=mono_font)

# Save
img.save('/home/kontomeo/Desktop/JURASSIC_TREX_ETCH_SKETCH.png', 'PNG')
print("=" * 50)
print("  ETCH-A-SKETCH SIMULATION COMPLETE")
print("=" * 50)
print(f"  Rapids (pen up):  {len(rapids)} moves")
print(f"  Cut segments:     {sum(len(s) for _, s in cuts)}")
print(f"  Pierce points:    {len(pierces)}")
print(f"  Total cuts:       6")
print("=" * 50)
print("  Saved: JURASSIC_TREX_ETCH_SKETCH.png")
