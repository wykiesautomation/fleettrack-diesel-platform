# Android Road-Trip Contract Alignment 1.3

- Android batch uploads now include the required `device_id` on every point.
- Android local accuracy rejection is aligned with the web operational route threshold of 150 m.
- Batch responses expose accepted, duplicate and rejected sequences plus device identity and server time.
- Valid raw observations are stored; operational route analysis excludes poor accuracy, out-of-order points, impossible jumps and stationary drift.
