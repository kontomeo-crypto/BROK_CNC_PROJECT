(BROK CNC - Calibration Test v5 - NO THC)
(Generated: 2025-12-22)
(Machine: Crossfire Pro)
(Plasma: Everlast 102i @ 70A, 55 PSI)
()
(*** THC DISABLED FOR TESTING ***)
(If this works, THC timing is the issue)
()
(Feed Rate: 50 IPM)
(Pierce Delay: 0.7 sec)
(Pierce Height: 0.15")
(Cut Height: 0.06")
()
(v1.6-af)
G90 G94
G17
G20
F50

(Simple test - one 1" circle, NO THC)
G0 X6.0000 Y6.0000
G92 Z0.
G38.2 Z-5.0 F100.0
G38.4 Z0.5 F20.0
G92 Z0.0
G0 Z0.02
G92 Z0.0
G0 Z0.15
M3
G4 P0.7
G1 Z0.06 F50
(NO H1 - THC stays off)
G3 X6.5000 Y6.0000 I0.2500 J0.0000 F50
G3 X5.5000 Y6.0000 I-0.5000 J0.0000 F50
G3 X6.5000 Y6.0000 I0.5000 J0.0000 F50
M5
G0 Z1.0

(Program End)
G0 X0 Y0
M30
(PS50)
