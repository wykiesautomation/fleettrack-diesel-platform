# Part 10: OPC Classic Windows Bridge
- Built cumulatively on Part 9.
- Adds a Windows-only OPC DA bridge for local server enumeration, tag browsing, bounded read tests, polling and tag-to-signal mappings.
- Adds 32/64-bit process readiness, COM/OpenOPC availability and local DCOM commissioning guidance.
- The cloud never connects to DCOM. The Windows Edge Gateway performs all OPC Classic access and uploads outbound telemetry.
- Permanently read-only: no OPC Write, control, setpoint, method, alarm acknowledgement or remote DCOM exposure path exists.
