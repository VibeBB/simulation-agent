---
name: ruggedness
description: Check board vibration fatigue, drop shock, and IP opening limits.
---
Run `python3 plugins/sim/scripts/sim_launcher.py run <brief> --only ruggedness`. Vibration uses a simply supported plate natural frequency, Miles' equation, and Steinberg's allowable board displacement; drop uses a half-sine pulse peak acceleration; ingress checks only the IEC 60529 first-digit opening sizes. Dust (5/6) and water digits stay unknown until a physical test exists. Take `steinberg_c` from the part package (1.0 is a standard DIP baseline); never guess a missing value.
