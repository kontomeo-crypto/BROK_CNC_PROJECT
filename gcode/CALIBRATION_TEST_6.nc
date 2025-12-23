(BROK CNC - Calibration Test v6)
(Generated: 2025-12-22)
(Machine: Crossfire Pro)
(Plasma: Everlast 102i @ 70A, 55 PSI)
()
(*** FIXED: Pierce height 0.12" (was 0.15") ***)
(Pierce should be 150-200% of cut height)
(0.06" cut x 2 = 0.12" pierce)
()
(Feed Rate: 50 IPM)
(Pierce Delay: 0.7 sec)
(Pierce Height: 0.12")
(Cut Height: 0.06")
()
(v1.6-af)
G90 G94
G17
G20
F50
H0

(Test circle 1" diameter - pierce at 0.12")
G0 X6.0000 Y6.0000
G92 Z0.
G38.2 Z-5.0 F100.0
G38.4 Z0.5 F20.0
G92 Z0.0
G0 Z0.02
G92 Z0.0
G0 Z0.12
M3
G4 P0.7
G1 Z0.06 F50
H1
G3 X6.5000 Y6.0000 I0.2500 J0.0000 F50
G3 X5.5000 Y6.0000 I-0.5000 J0.0000 F50
G3 X6.5000 Y6.0000 I0.5000 J0.0000 F50
(Overcut 0.375")
G3 X6.4045 Y6.2939 I-0.5000 J0.0000 F50
M5
H0
G0 Z1.0

(Program End)
G0 X0 Y0
M30
(PS50)
