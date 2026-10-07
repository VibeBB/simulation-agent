---
name: lifetime
description: Check electrolytic-capacitor and other wear-out life with the Arrhenius law.
---
Run `python3 plugins/sim/scripts/sim_launcher.py run <brief> --only lifetime`. Each part needs the datasheet rated life and rated temperature, an explicit activation energy (eV), the mission profile (hot-spot temperature and time fraction per step, summing to 1), the required life, and the `source` that states where those facts came from. Life per step is `L_rated·exp(Ea/k·(1/T_use − 1/T_rated))` and steps combine by Miner's rule. Never assume an activation energy or the 10 °C doubling rule; a missing value must be supplied, not guessed.
