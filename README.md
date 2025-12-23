# BROK CNC - Autonomous AI Image-to-CNC System

AI-powered CNC plasma cutting toolchain for Langmuir Crossfire Pro with FireControl v1.6.

## Project Structure

```
BROK_CNC_PROJECT/
├── python_tools/      # Core Python scripts
│   ├── brok_autonomous.py   # Main autonomous pipeline (v2 tuned)
│   ├── brok_cnc.py          # BROK CNC with GPS grid + bevel law
│   ├── brok_tracer.py       # Grid trace system
│   └── ...                  # Other development scripts
├── qc_images/         # Quality control visualization images
├── gcode/             # Generated G-code files (.nc)
├── backups/           # Versioned backups of work
└── source_images/     # Input images for tracing
```

## Key Features

### BROK Autonomous (v2 Tuned)
- **Image-to-CNC Pipeline**: Load image → trace → add features → validate → G-code
- **Tuned Jaw Detection**: Precise coordinate bounds for teeth placement
- **Even Spacing Algorithm**: Calculates ideal positions, finds closest skeleton points
- **Self-Validation**: Checks count, positions, spacing with 70% tolerance
- **Bevel Law Enforcement**: Inside cuts CCW, outside cuts CW

### Tuned Parameters
```python
jaw_params = {
    'upper_x_min': 9.5,    'upper_x_max': 11.5,
    'upper_y_min': 8.5,    'upper_y_max': 9.5,
    'lower_x_min': 9.5,    'lower_x_max': 11.3,
    'lower_y_min': 7.0,    'lower_y_max': 7.6,
    'skip_back': 0.20,     'skip_front': 0.10,
    'tooth_w': 0.40,       'tooth_h': 0.52
}
```

## CNC Specifications (FireControl v1.6)

- **Feed Rate**: 47 IPM
- **Pierce Height**: 0.148"
- **Cut Height**: 0.059"
- **IHS Sequence**: G38.2Z-5F50 → G38.4Z0.5F25 → G92Z0
- **Dwell**: 0.70s after pierce

## Bevel Law

```
Travel Direction → Bevel on LEFT, Square on RIGHT
Inside holes:    CCW = square edge on workpiece
Outside cuts:    CW  = square edge on workpiece
```

## Usage

```bash
# Run autonomous pipeline
python3 python_tools/brok_autonomous.py

# Output:
# - BROK_FINAL.png (QC image)
# - JURASSIC_TREX.nc (G-code)
```

## Known Limitations

- Teeth placement uses coordinate-based detection, not semantic understanding
- Future: Integration with VLM for visual reasoning
- Future: Integration with Flux for QC reference generation

## Development Date
December 22, 2024
