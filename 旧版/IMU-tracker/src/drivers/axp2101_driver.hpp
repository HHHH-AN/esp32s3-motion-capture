#pragma once

#include <Wire.h>

#include <cstdint>

namespace mocap::drivers {

struct Axp2101Status {
  std::uint8_t chip_id{0};
  std::uint8_t status0{0};
  std::uint8_t status1{0};
  bool reachable{false};
};

// Read-only until each rail and charger setting has been verified on hardware.
class Axp2101Driver final {
 public:
  explicit Axp2101Driver(TwoWire& wire, std::uint8_t address = 0x34)
      : wire_(wire), address_(address) {}

  bool begin();
  bool readStatus(Axp2101Status& status);
  bool readRegister(std::uint8_t reg, std::uint8_t& value);

 private:
  TwoWire& wire_;
  std::uint8_t address_;
};

}  // namespace mocap::drivers
