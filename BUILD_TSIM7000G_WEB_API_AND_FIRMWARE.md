# LILYGO T-SIM7000G Web API and Firmware Baseline

- Adds `AT360_LILYGO_T_SIM7000G` as a separate public board profile.
- Adds claim UID prefix `AT360-TSIM7000G-`.
- Adds cellular, GNSS, battery, solar, Wi-Fi, offline queue, optional microSD and simulation points.
- Locks customer GPIO until the physical PCB revision is verified.
- Adds a revision-safe Arduino firmware baseline with permanent setup AP, local web registration, APN/Wi-Fi setup, claim flow, telemetry and bounded offline queue.
- microSD is optional and disabled by default.
