# Fleet Tracking GPS Device Selector Fix

Fleet Tracking no longer opens the first TRACKER asset by name. It now builds a tenant-scoped list of active devices with verified GPS, GNSS, LOCATION or mobile-tracker capability.

The Fleet Safety Live header provides a selector showing asset name, device UID, connectivity state and contact age. Selecting a device opens that exact device and asset. SIM808, LILYGO T-SIM7000G, Android, iPhone and mobile web trackers are included only when their real profile or device type supports location.

The selected device ID is preserved in links to Live, Tracking History and Evidence Centre. No non-GPS device is presented as trackable.
