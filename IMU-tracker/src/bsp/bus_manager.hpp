#pragma once

#include <SPI.h>
#include <Wire.h>

namespace mocap::bsp {

struct BusStatus {
  bool sensor_spi{false};
  bool pmic_i2c{false};
  bool magnetometer_i2c{false};
};

class BusManager final {
 public:
  static BusManager& instance();

  bool begin();
  BusStatus status() const { return status_; }
  SPIClass& sensorSpi() { return SPI; }
  TwoWire& pmicWire() { return pmic_wire_; }
  TwoWire& magWire() { return mag_wire_; }

 private:
  BusManager();
  TwoWire pmic_wire_;
  TwoWire mag_wire_;
  bool started_{false};
  BusStatus status_{};
};

}  // namespace mocap::bsp
