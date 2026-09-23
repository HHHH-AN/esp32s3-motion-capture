# Third-party notices

- Espressif Arduino Core for ESP32 is supplied by the pinned PlatformIO platform
  `espressif32@6.10.0` (Arduino-ESP32 2.0.17); consult its packages for licenses.
- NimBLE-Arduino `1.4.3` is used by the BLE build environments and
  retains its upstream Apache-2.0 license.
- XPowersLib `0.3.3` was evaluated but is not linked in M2: its AXP2101
  `begin()` performs `disableTSPinMeasure()`. That violates the required
  read-only PMIC bring-up gate. The local AXP wrapper only reads chip/status
  registers; adopt the pinned library after PMIC writes are approved on hardware.
- No vendor LIS2MDL source is copied yet. The current driver is a small
  project-owned register wrapper. Before vendoring ST's `lis2mdl_reg.c/.h`, the
  team must select an exact upstream revision and record its license here.
